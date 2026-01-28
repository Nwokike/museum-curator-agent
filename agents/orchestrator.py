from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from modules.db import get_connection

# Initialize Model (Rank 1: Logic)
orch_model = GroqFallbackClient()

def check_queue_status():
    """
    Checks what needs to be done next.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Priority 1: Research (Finish what we started)
            cur.execute("SELECT id, title, metadata FROM archives WHERE description_ai IS NULL LIMIT 1")
            row = cur.fetchone()
            if row:
                return f"TASK: RESEARCH. ID: {row['id']}. Title: {row['title']}"
            
            # Priority 2: Scan (Process pending)
            cur.execute("SELECT id, url FROM artifact_queue WHERE status = 'PENDING' LIMIT 1")
            row = cur.fetchone()
            if row:
                return f"TASK: SCAN. ID: {row['id']}. URL: {row['url']}"
            
            return "TASK: IDLE. Queue empty."
    finally:
        conn.close()

orchestrator_agent = Agent(
    name="CuratorCore",
    model=orch_model,
    description="Manages the entire archiving workflow.",
    instruction="""
    You are the Curator Core.
    1. Call `check_queue_status` to see what is pending.
    2. IF "TASK: SCAN": Delegate to Vision Agent.
    3. IF "TASK: RESEARCH": Delegate to Historian Agent.
    4. IF "TASK: IDLE": Delegate to Scout Agent to find new items.
    
    Do not stop until you are told to stop.
    """,
    tools=[check_queue_status]
    # Note: Sub-agents (Scout, Vision, Historian) are called as sub-routines in the Main Loop
)