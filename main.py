import asyncio
import json
import time
import re
from google.genai import types

# Imports
from modules.sessions import get_agent_runner
from modules.db import (
    init_db, get_system_status, get_connection, 
    lock_artifact_state, handle_artifact_failure # NEW IMPORT
)

# Agents
from agents.orchestrator import coordinator_agent
from agents.scout import (
    navigator_agent, link_extractor_agent, deduplicator_agent, 
    queue_manager_agent, html_parser_agent, downloader_agent
)
from agents.vision import visual_analyst_agent
from agents.historian import context_searcher_agent, synthesizer_agent, fact_extractor_agent
from agents.archivist import draft_reviewer_agent, hf_uploader_agent, cleaner_agent

# --- CONFIGURATION ---
USER_ID = "admin"
MAX_CONCURRENT_TASKS = 5  # Semaphore limit
background_tasks = set()  # Track active tasks to prevent garbage collection

# Global Discovery Context
DISCOVERY_CONTEXT = {
    "active": False,
    "current_url": ""
}

async def run_agent_task(agent, prompt, session_id, system_update=None):
    """
    Standard Runner (Persistent Memory).
    """
    runner = get_agent_runner(agent, session_id=session_id)
    full_prompt = prompt
    if system_update:
        full_prompt = f"[SYSTEM UPDATE: {system_update}]\n\nTASK: {prompt}"

    resp_text = ""
    msg = types.Content(role="user", parts=[types.Part(text=full_prompt)])
    
    try:
        async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=msg):
            if event.content and event.content.role == "model":
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        resp_text += part.text
    except Exception as e:
        print(f"[{agent.name}] ⚠️ Error: {e}")
        return f"ERROR: {e}"
    return resp_text

# --- WORKER FUNCTIONS ---

async def job_archive(target_id, session_id):
    print(f"📦 [Archivist] Starting upload for {target_id}")
    await run_agent_task(hf_uploader_agent, f"Upload artifacts for ID: {target_id}", session_id)
    await run_agent_task(cleaner_agent, f"Clean local files for ID: {target_id}", session_id)
    print(f"✅ [Archivist] Finished {target_id}")

async def job_analyze_pipeline(target_id, session_id):
    print(f"🧠 [Cognitive] Starting Analysis Loop for {target_id}")
    
    # A. Visual Analysis
    await run_agent_task(visual_analyst_agent, f"Analyze all images for {target_id}", session_id)
    
    # B. Fetch Metadata
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT title, spatial_coverage, rights_holder FROM artifact_queue JOIN archives USING(id) WHERE id=%s", (target_id,))
        row = cur.fetchone()
    conn.close()
    
    museum = row['rights_holder'] if row['rights_holder'] else "the museum"
    search_prompt = f"Find context for '{row['title']}' from '{museum}' in '{row['spatial_coverage']}'."
    
    # C. Research & D. Extraction & E. Synthesis (Chained)
    await run_agent_task(context_searcher_agent, search_prompt, session_id, system_update="You are Context Searcher.")
    await run_agent_task(fact_extractor_agent, "Extract verified facts.", session_id)
    
    synth_prompt = f"Synthesize deep description for {target_id} using history."
    await run_agent_task(synthesizer_agent, synth_prompt, session_id, system_update="You are Synthesizer.")
    print(f"✅ [Cognitive] Finished {target_id}")

async def job_extract(target_id, url, session_id):
    print(f"⛏️ [Extractor] Scraping {target_id}")
    parser_output = await run_agent_task(html_parser_agent, f"Scrape metadata from {url} for ID {target_id}", session_id)
    
    # Download Logic
    try:
        json_match = re.search(r'\{.*\}', parser_output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            media_urls = data.get("media_urls", [])
            for img_url in media_urls:
                await run_agent_task(downloader_agent, f"Download {img_url} for {target_id}", session_id)
            
            # Finalize State
            lock_artifact_state(target_id, "EXTRACTED")
    except Exception as e:
        print(f"⚠️ [Extractor] Failed: {e}")
        handle_artifact_failure(target_id, str(e)) # Use new error handler

async def job_discovery(session_id):
    # Wrapped Discovery logic would go here
    pass 

# --- BACKGROUND WRAPPER ---

async def task_wrapper(coro, artifact_id=None):
    """
    Wraps the job to handle errors and release the semaphore.
    """
    try:
        await coro
    except Exception as e:
        print(f"💥 Background Task Failed: {e}")
        if artifact_id:
            handle_artifact_failure(artifact_id, str(e))

# --- MAIN LOOP ---

async def main():
    print("[System] 🏛️ Museum Curator Agent v2.5 (Self-Healing) Starting...")
    init_db()
    
    # The Semaphore limits us to 5 active workers
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    coord_session_id = "session_coordinator_main"
    
    while True:
        try:
            # 1. Check System Status
            if get_system_status() != "RUNNING":
                await asyncio.sleep(5)
                continue

            # 2. Coordinator Decision
            if semaphore.locked():
                print("[System] 🚦 Max capacity reached. Waiting for a slot...")
                await asyncio.sleep(2)
                continue

            decision_raw = await run_agent_task(
                coordinator_agent, 
                "Assess metrics. Assign ONE job. Return JSON.", 
                coord_session_id
            )
            
            try:
                clean_json = decision_raw.replace("```json", "").replace("```", "").strip()
                decision = json.loads(clean_json)
                action = decision.get("action")
                target_id = decision.get("target_id")
                ctx = decision.get("context", {})
            except:
                continue

            if action == "SLEEP":
                await asyncio.sleep(5)
                continue

            # 3. DISPATCHER LOGIC
            job_coro = None
            job_session_id = f"artifact_{target_id}" if target_id else "general"

            if action == "ARCHIVE_JOB":
                lock_artifact_state(target_id, "ARCHIVING_IN_PROGRESS")
                job_coro = job_archive(target_id, job_session_id)

            elif action == "ANALYZE_JOB":
                lock_artifact_state(target_id, "ANALYZING_IN_PROGRESS")
                job_coro = job_analyze_pipeline(target_id, job_session_id)

            elif action == "EXTRACT_JOB":
                lock_artifact_state(target_id, "EXTRACTING_IN_PROGRESS")
                job_coro = job_extract(target_id, ctx.get("url"), job_session_id)
            
            elif action == "REVIEW_JOB":
                await run_agent_task(draft_reviewer_agent, f"Send {target_id}", job_session_id)
                continue

            # 4. SPAWN
            if job_coro:
                await semaphore.acquire()
                task = asyncio.create_task(task_wrapper(job_coro, target_id))
                task.add_done_callback(lambda t: semaphore.release())
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
                
                print(f"🚀 Dispatched {action} for {target_id}. Active Tasks: {len(background_tasks)}")

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"[System] 💥 Critical Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())