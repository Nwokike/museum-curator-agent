import asyncio
import json
import time
import re
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Agents
from agents.orchestrator import coordinator_agent
from agents.scout import (
    navigator_agent, link_extractor_agent, deduplicator_agent, 
    queue_manager_agent, html_parser_agent, downloader_agent
)
from agents.vision import visual_analyst_agent
from agents.historian import context_searcher_agent, synthesizer_agent, fact_extractor_agent
from agents.archivist import draft_reviewer_agent, hf_uploader_agent, cleaner_agent

from modules.db import init_db, get_system_status, get_connection

USER_ID = "admin"
APP_NAME = "IgboCurator"

# Global Discovery Context (Simple memory for the session)
DISCOVERY_CONTEXT = {
    "active": False,
    "current_url": ""
}

async def run_agent_task(agent, prompt, session_id):
    """Executes a single agent task within a session context."""
    session_service = InMemorySessionService()
    if hasattr(session_service, "async_create_session"):
        await session_service.async_create_session(session_id=session_id, user_id=USER_ID, app_name=APP_NAME)
    
    runner = Runner(agent=agent, session_service=session_service, app_name=APP_NAME)
    resp_text = ""
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    
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

async def main():
    print("[System] 🏛️ Museum Curator Agent v2.2 (Dynamic Discovery) Starting...")
    init_db()
    
    session_id = f"session_{int(time.time())}"
    
    while True:
        try:
            # 1. Master Kill Switch
            if get_system_status() != "RUNNING":
                await asyncio.sleep(5)
                continue

            # 2. Coordinator Decision
            print("\n[Coordinator] Assessing Queue...")
            decision_raw = await run_agent_task(
                coordinator_agent, 
                "Assess metrics and assign the next job. Return JSON.", 
                session_id
            )
            
            try:
                clean_json = decision_raw.replace("```json", "").replace("```", "").strip()
                decision = json.loads(clean_json)
                action = decision.get("action")
                target_id = decision.get("target_id")
                ctx = decision.get("context", {})
                reason = decision.get("reasoning", "No reason provided")
                
                print(f"[Coordinator] Decision: {action} ({target_id}) - {reason}")
                
            except json.JSONDecodeError:
                print(f"[Coordinator] ⚠️ Failed to parse JSON: {decision_raw}")
                await asyncio.sleep(5)
                continue

            # 3. Execution Routing
            
            if action == "ARCHIVE_JOB":
                await run_agent_task(hf_uploader_agent, f"Upload artifacts for ID: {target_id}", session_id)
                await run_agent_task(cleaner_agent, f"Clean local files for ID: {target_id}", session_id)

            elif action == "REVIEW_JOB":
                await run_agent_task(draft_reviewer_agent, f"Send ID {target_id} to Telegram for review.", session_id)
                
            elif action == "ANALYZE_JOB":
                # --- RAG PIPELINE ---
                print(f"[Analysis] Starting Cognitive Loop on {target_id}...")
                
                # A. Visual Analysis
                visual_data = await run_agent_task(visual_analyst_agent, f"Analyze all images for {target_id}", session_id)
                
                # B. Fetch Metadata
                conn = get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT title, spatial_coverage, rights_holder FROM artifact_queue JOIN archives USING(id) WHERE id=%s", (target_id,))
                    row = cur.fetchone()
                conn.close()
                
                museum = row['rights_holder'] if row['rights_holder'] else "the museum"
                search_prompt = f"Find context for '{row['title']}' from '{museum}' in '{row['spatial_coverage']}'."
                
                # C. Research
                raw_search = await run_agent_task(context_searcher_agent, search_prompt, session_id)
                
                # D. Fact Extraction
                verified_facts = await run_agent_task(fact_extractor_agent, f"Extract verified facts from: {raw_search}", session_id)
                
                # E. Synthesis
                synth_prompt = (
                    f"Synthesize description for {target_id}.\n"
                    f"Metadata: {row['title']}\n"
                    f"Visuals: {visual_data}\n"
                    f"Verified Facts: {verified_facts}"
                )
                await run_agent_task(synthesizer_agent, synth_prompt, session_id)

            elif action == "EXTRACT_JOB":
                url = ctx.get("url")
                print(f"[Extraction] Processing {target_id} at {url}...")
                
                # A. Parse
                parser_output = await run_agent_task(html_parser_agent, f"Scrape metadata from {url} for ID {target_id}", session_id)
                
                # B. Multi-Image Download
                try:
                    json_match = re.search(r'\{.*\}', parser_output, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group(0))
                        media_urls = data.get("media_urls", [])
                        
                        if media_urls:
                            print(f"[Extraction] Found {len(media_urls)} images.")
                            for img_url in media_urls:
                                await run_agent_task(downloader_agent, f"Download {img_url} for {target_id}", session_id)
                                
                            conn = get_connection()
                            with conn.cursor() as cur:
                                cur.execute("UPDATE artifact_queue SET status='EXTRACTED' WHERE id=%s", (target_id,))
                            conn.commit()
                            conn.close()
                        else:
                            print(f"[Extraction] ⚠️ No images found in parser output.")
                    else:
                         print(f"[Extraction] ⚠️ Could not parse JSON from agent output.")
                except Exception as e:
                    print(f"[Extraction] Error during download loop: {e}")

            elif action == "DISCOVER_JOB":
                # Squad: Scout (Dynamic Discovery)
                START_URL = "https://www.prm.ox.ac.uk/search/all?search_api_fulltext=Igbo"
                
                print(f"[Discovery] Scouting...")
                
                # 1. Navigation Logic
                if not DISCOVERY_CONTEXT["active"]:
                    # Start Fresh
                    print("[Discovery] Starting new session.")
                    status = await run_agent_task(navigator_agent, f"GOTO {START_URL}", session_id)
                    DISCOVERY_CONTEXT["active"] = True
                    DISCOVERY_CONTEXT["current_url"] = START_URL
                else:
                    # Continue Pagination
                    print("[Discovery] Clicking Next Page.")
                    status = await run_agent_task(navigator_agent, "NEXT PAGE", session_id)
                
                if "ERROR" in status or "END_OF_ARCHIVE" in status:
                    print(f"[Discovery] Navigation stopped: {status}")
                    DISCOVERY_CONTEXT["active"] = False
                    await asyncio.sleep(60) # Backoff
                    continue

                # 2. Extract & Queue
                links_json = await run_agent_task(link_extractor_agent, f"Extract object links", session_id)
                
                try:
                    raw_links = json.loads(links_json)
                    if raw_links:
                        valid_links_str = await run_agent_task(deduplicator_agent, f"Filter these links: {links_json}", session_id)
                        await run_agent_task(queue_manager_agent, f"Queue these links: {valid_links_str}. Museum: Pitt Rivers.", session_id)
                    else:
                        print("[Discovery] No links found on this page.")
                except Exception as e:
                    print(f"[Discovery] Error processing links: {e}")

            elif action == "SLEEP":
                print("[System] No tasks available. Idling...")
                await asyncio.sleep(10)
                
            await asyncio.sleep(2)

        except Exception as e:
            print(f"[System] 💥 Critical Loop Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())