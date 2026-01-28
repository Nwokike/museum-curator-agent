import asyncio
import time
import re
import json
import random
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import The Squads
from agents.orchestrator import get_queue_metrics # Only extracting the metric function
# Cluster A: Discovery (Replaced by Logic)
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
from modules.db import init_db, get_system_status, get_connection, get_discovery_state, update_discovery_state

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
            return cur.fetchone() 
    except:
        with conn.cursor() as cur:
            cur.execute("SELECT id, url FROM artifact_queue WHERE status = %s LIMIT 1", (status,))
            return cur.fetchone()
    finally:
        conn.close()

async def main():
    print("[System] 🏛️ Museum Curator Agent Starting...")
    init_db()

    SOURCE_NAME = "PRM_Igbo" # Hardcoded for this run, could be config
    
    while True:
        try:
            # 1. Master Switch
            if get_system_status() != "RUNNING":
                await asyncio.sleep(5)
                continue

            # 2. Deterministic Orchestration (No LLM Cost)
            metrics = get_queue_metrics()
            print(f"[Orchestrator] Status: {metrics}")

            # --- PRIORITY 1: ARCHIVE (Finish the Job) ---
            if metrics["APPROVED"] > 0:
                item = await fetch_job("APPROVED")
                if item:
                    print(f"[Archive] Uploading {item['id']}...")
                    await run_adk(hf_uploader_agent, f"Upload {item['id']}", "up")
                    await run_adk(cleaner_agent, f"Clean {item['id']}", "clean")

            # --- PRIORITY 2: REVIEW (Human in the Loop) ---
            elif metrics["RESEARCHED"] > 0:
                item = await fetch_job("RESEARCHED")
                if item:
                    print(f"[Review] Sending {item['id']} to Telegram...")
                    await run_adk(draft_reviewer_agent, f"Send review for {item['id']}", "rev")
                    # Update status manually to prevent loop
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute("UPDATE artifact_queue SET status='REVIEW_PENDING' WHERE id=%s", (item['id'],))
                    conn.commit()
                    conn.close()

            # --- PRIORITY 3: ANALYZE (The "Smart" Agents) ---
            elif metrics["EXTRACTED"] > 0:
                item = await fetch_job("EXTRACTED")
                if item:
                    uid = item['id']
                    print(f"[Vision] Analyzing {uid}...")
                    
                    # 1. Visual Analysis (Gemini)
                    visual_facts = await run_adk(visual_analyst_agent, f"Analyze artifact {uid}", "vis")
                    
                    # 2. Historical Research (Gemini)
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute("SELECT title, location FROM archives WHERE id=%s", (uid,))
                        row = cur.fetchone()
                    conn.close()
                    
                    context = await run_adk(context_searcher_agent, f"Research '{row['title']}' in '{row['location']}'", "res")
                    
                    # 3. Synthesis (Llama/Gemini)
                    prompt = f"Synthesize Description.\nVisuals: {visual_facts}\nContext: {context}\nMetadata: {row['title']}"
                    await run_adk(synthesizer_agent, prompt, "syn")

            # --- PRIORITY 4: EXTRACT (The Scraper) ---
            elif metrics["PENDING"] > 0:
                item = await fetch_job("PENDING")
                if item:
                    uid, url = item['id'], item['url']
                    print(f"[Extraction] Processing {uid}...")
                    
                    # 1. Parse Metadata
                    metadata_response = await run_adk(html_parser_agent, f"Scrape metadata from {url}", "parser")
                    
                    # 2. Find Image URL
                    img_url = None
                    try:
                        json_match = re.search(r'\{.*\}', metadata_response, re.DOTALL)
                        if json_match:
                            meta_data = json.loads(json_match.group(0))
                            img_url = meta_data.get("found_image_url")
                    except Exception as e:
                        print(f"[System] Metadata parse warning: {e}")

                    # 3. Download
                    if img_url:
                        await run_adk(downloader_agent, f"Download image from {img_url} for ID {uid}", "down")
                        
                        conn = get_connection()
                        with conn.cursor() as cur:
                            cur.execute("UPDATE artifact_queue SET status='EXTRACTED' WHERE id=%s", (uid,))
                        conn.commit()
                        conn.close()
                    else:
                        print(f"[System] ⚠️ No image URL found for {uid}. Marking as REJECTED.")
                        conn = get_connection()
                        with conn.cursor() as cur:
                            cur.execute("UPDATE artifact_queue SET status='REJECTED' WHERE id=%s", (uid,))
                        conn.commit()
                        conn.close()

            # --- PRIORITY 5: DISCOVER (The Crawler) ---
            else:
                # Deterministic Pagination
                last_page = get_discovery_state(SOURCE_NAME)
                next_page = last_page + 1
                
                print(f"[Discovery] No tasks in queue. Scraping Page {next_page}...")
                
                # PRM Specific URL Construction
                target = f"https://www.prm.ox.ac.uk/search/all?search_api_fulltext=Igbo&page={next_page}"
                
                # 1. Navigate
                await run_adk(navigator_agent, f"Visit {target}", "nav")
                
                # 2. Extract Links
                links_json_str = await run_adk(link_extractor_agent, f"Extract links from {target}", "extract")
                
                # 3. Queue Logic
                try:
                    links = json.loads(links_json_str)
                    if links:
                        print(f"[Discovery] Found {len(links)} items on page {next_page}.")
                        await run_adk(queue_manager_agent, f"Queue these links: {links_json_str}. Museum: Pitt Rivers.", "queue")
                        update_discovery_state(SOURCE_NAME, next_page)
                    else:
                        print(f"[Discovery] Page {next_page} returned no links. End of Archive?")
                        await asyncio.sleep(60) # Backoff if empty
                except Exception as e:
                    print(f"[Discovery] Failed to parse links: {e}")

            await asyncio.sleep(5)

        except Exception as e:
            print(f"[System] 💥 Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())