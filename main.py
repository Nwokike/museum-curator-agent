import asyncio
import time
import re
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import The Squad
from agents.orchestrator import orchestrator_agent
from agents.scout import scout_agent
from agents.vision import vision_agent
from agents.historian import historian_agent

# Import Utilities
from modules.db import init_db, get_system_status, log_thought, get_connection

# Configuration
USER_ID = "admin_user"
APP_NAME = "MuseumCurator"

async def run_agent(agent, prompt: str, session_id_suffix: str):
    """
    Helper to run a specific agent for one turn.
    """
    session_service = InMemorySessionService()
    session_id = f"session_{agent.name}_{session_id_suffix}_{int(time.time())}"
    
    # Initialize ADK Session
    if hasattr(session_service, "create_session"):
        await session_service.create_session(session_id=session_id, user_id=USER_ID, app_name=APP_NAME)
    elif hasattr(session_service, "async_create_session"):
        await session_service.async_create_session(session_id=session_id, user_id=USER_ID, app_name=APP_NAME)

    runner = Runner(agent=agent, session_service=session_service, app_name=APP_NAME)
    
    log_thought(agent.name, f"Starting task: {prompt[:50]}...")
    
    response_text = []
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    try:
        async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=msg):
            if event.content and event.content.role == "model":
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_text.append(part.text)
    except Exception as e:
        print(f"[{agent.name}] ⚠️ Error: {e}")
        return None

    return "".join(response_text)

async def main():
    print("[System] 🏛️ Museum Curator Agent Starting...")
    init_db()

    while True:
        try:
            # 1. The Master Switch
            status = get_system_status()
            if status != "RUNNING":
                print(f"[System] 💤 Status is {status}. Sleeping 10s...")
                await asyncio.sleep(10)
                continue

            # 2. Consult the Orchestrator (CuratorCore)
            # We ask it to check the DB and decide the priority.
            decision = await run_agent(
                orchestrator_agent, 
                "Check queue status and decide the next TASK. Return ONLY the Task String (e.g., 'TASK: SCAN...').", 
                "orch"
            )

            if not decision:
                print("[System] ⚠️ Orchestrator silent. Retrying...")
                await asyncio.sleep(5)
                continue

            print(f"[Orchestrator] Decision: {decision}")

            # 3. Router Logic (The Switchboard)
            if "TASK: IDLE" in decision:
                # No items in queue -> Run Scout
                # We give the Scout a specific Museum Search URL (Configurable or hardcoded for now)
                target_url = "https://www.prm.ox.ac.uk/search/all?search_api_fulltext=Igbo"
                await run_agent(scout_agent, f"Scan this search page: {target_url}", "scout")

            elif "TASK: SCAN" in decision:
                # Extract ID and URL from the decision string using Regex
                # Expected format: "TASK: SCAN. ID: PRM_123. URL: https://..."
                match = re.search(r"ID: (.*)\. URL: (.*)", decision)
                if match:
                    obj_id, url = match.groups()
                    # Trigger Vision Agent
                    await run_agent(vision_agent, f"Analyze ID {obj_id} at {url}", "vision")
                else:
                    print("[System] ⚠️ Could not parse SCAN task.")

            elif "TASK: RESEARCH" in decision:
                # Extract ID
                match = re.search(r"ID: (.*)\. Title: (.*)", decision)
                if match:
                    obj_id, title = match.groups()
                    # Trigger Historian
                    # We need the museum description too, but Historian can fetch it from DB if needed
                    # For now, we pass the title as the context prompt
                    await run_agent(historian_agent, f"Research context for: {title} (ID: {obj_id})", "historian")

            # 4. Rate Limit Protection
            # Pause to respect the 2026 Limits (and be polite to museums)
            print("[System] ⏳ Cooldown (15s)...")
            await asyncio.sleep(15)

        except KeyboardInterrupt:
            print("[System] Manual Shutdown.")
            break
        except Exception as e:
            print(f"[System] 💥 Critical Loop Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())