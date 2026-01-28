import asyncio
import time
import re
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import The Squads
from agents.orchestrator import orchestrator_agent
# Cluster A: Discovery
from agents.scout import navigator_agent, link_extractor_agent, deduplicator_agent, queue_manager_agent
# Cluster B: Extraction
from agents.scout import html_parser_agent, downloader_agent
# Cluster C: Vision
from agents.vision import visual_analyst_agent
# Cluster D: History
from agents.historian import context_searcher_agent, synthesizer_agent
# Cluster E: Archival
from agents.archivist import draft_reviewer_agent, hf_uploader_agent, cleaner_agent

# Utilities
from modules.db import init_db, get_system_status, get_connection, log_thought

USER_ID = "admin"
APP_NAME = "IgboCurator"

async def run_adk(agent, prompt, session_key):
    """Helper to run a single ADK agent."""
    session_service = InMemorySessionService()
    sid = f"{session_key}_{int(time.time())}"
    if hasattr(session_service, "create_session"):
        await session_service.create_session(session_id=sid, user_id=USER_ID, app_name=APP_NAME)
    elif hasattr(session_service, "async_create_session"):
        await session_service.async_create_session(session_id=sid, user_id=USER_ID, app_name=APP_NAME)
        
    runner = Runner(agent=agent, session_service=session_service, app_name=APP_NAME)
    resp = []
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    
    try:
        async for event in runner.run_async(user_id=USER_ID, session_id=sid, new_message=msg):
            if event.content and event.content.role == "model":
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            resp.append(part.text)
    except Exception as e:
        print(f"[{agent.name}] ⚠️ Error: {e}")
        return None
    return "".join(resp)

async def fetch_job(status):
    """Fetches the oldest item in a specific state."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, url, title, location FROM artifact_queue JOIN archives USING(id) WHERE artifact_queue.status = %s LIMIT 1", (status,))
            return cur.fetchone() # Returns dict or None
    except:
        # Fallback for PENDING which might not have archive entry yet
        with conn.cursor() as cur:
            cur.execute("SELECT id, url FROM artifact_queue WHERE status = %s LIMIT 1", (status,))
            return cur.fetchone()
    finally:
        conn.close()

async def main():
    print("[System] 🏛️ Museum Curator Agent Starting...")
    init_db()

    while True:
        try:
            # 1. Master Switch
            if get_system_status() != "RUNNING":
                await asyncio.sleep(5)
                continue

            # 2. Orchestrator Decision
            decision = await run_adk(orchestrator_agent, "Decide next task.", "orch")
            print(f"[Orchestrator] {decision}")

            # --- ROUTING LOGIC ---

            if "TASK: DISCOVER" in decision:
                target = "https://www.prm.ox.ac.uk/search/all?search_api_fulltext=Igbo"
                # 1. Navigate
                await run_adk(navigator_agent, f"Visit {target}", "nav")
                # 2. Extract
                links_json = await run_adk(link_extractor_agent, f"Extract links from {target}", "extract")
                # 3. Deduplicate & Queue (Loop handled by QueueManager internally or loop here)
                # For simplicity, we assume QueueManager handles the list in one go or we loop here
                # We'll let the model parse the JSON
                await run_adk(queue_manager_agent, f"Queue these links: {links_json}. Museum: Pitt Rivers.", "queue")

            elif "TASK: EXTRACT" in decision:
                item = await fetch_job("PENDING")
                if item:
                    uid, url = item['id'], item['url']
                    print(f"[Extraction] Processing {uid}...")
                    # 1. Parse Metadata
                    await run_adk(html_parser_agent, f"Scrape metadata from {url}", "parser")
                    # 2. Download Image
                    await run_adk(downloader_agent, f"Download image from {url} for ID {uid}", "down")
                    
                    # Manually advance state to EXTRACTED if agents succeeded
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute("UPDATE artifact_queue SET status='EXTRACTED' WHERE id=%s", (uid,))
                    conn.commit()
                    conn.close()

            elif "TASK: ANALYZE" in decision:
                item = await fetch_job("EXTRACTED")
                if item:
                    uid = item['id']
                    print(f"[Vision] Analyzing {uid}...")
                    # 1. Visual Analysis
                    visual_facts = await run_adk(visual_analyst_agent, f"Analyze artifact {uid}", "vis")
                    
                    # 2. Historical Research
                    # Need title/loc from archives table
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute("SELECT title, location FROM archives WHERE id=%s", (uid,))
                        row = cur.fetchone()
                    conn.close()
                    
                    context = await run_adk(context_searcher_agent, f"Research '{row['title']}' in '{row['location']}'", "res")
                    
                    # 3. Synthesis (Deep Description)
                    prompt = f"Synthesize Description.\nVisuals: {visual_facts}\nContext: {context}\nMetadata: {row['title']}"
                    await run_adk(synthesizer_agent, prompt, "syn")

            elif "TASK: REVIEW" in decision:
                item = await fetch_job("RESEARCHED")
                if item:
                    print(f"[Review] Sending {item['id']} to Telegram...")
                    await run_adk(draft_reviewer_agent, f"Send review for {item['id']}", "rev")
                    # Update status to avoid spamming
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute("UPDATE artifact_queue SET status='REVIEW_PENDING' WHERE id=%s", (item['id'],))
                    conn.commit()
                    conn.close()

            elif "TASK: ARCHIVE" in decision:
                item = await fetch_job("APPROVED")
                if item:
                    print(f"[Archive] Uploading {item['id']}...")
                    await run_adk(hf_uploader_agent, f"Upload {item['id']}", "up")
                    await run_adk(cleaner_agent, f"Clean {item['id']}", "clean")

            await asyncio.sleep(5)

        except Exception as e:
            print(f"[System] 💥 Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())