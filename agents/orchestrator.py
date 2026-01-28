from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from modules.db import get_connection

# Initialize Model
orch_model = GroqFallbackClient()

def get_queue_metrics():
    """
    Returns the count of artifacts in each stage of the pipeline.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*) 
                FROM artifact_queue 
                GROUP BY status
            """)
            rows = dict(cur.fetchall())
            
            return {
                "PENDING": rows.get("PENDING", 0),       # Needs Extraction
                "EXTRACTED": rows.get("EXTRACTED", 0),   # Needs Vision/Research
                "RESEARCHED": rows.get("RESEARCHED", 0), # Needs Review
                "APPROVED": rows.get("APPROVED", 0),     # Needs Upload
                "ARCHIVED": rows.get("ARCHIVED", 0)
            }
    finally:
        conn.close()

orchestrator_agent = Agent(
    name="CuratorCore",
    model=orch_model,
    description="Pipeline Manager. Decides the next system task.",
    instruction="""
    You are the Curator Core.
    1. Call `get_queue_metrics` to see the backlog.
    2. PRIORITIZE tasks in this order:
       - IF "APPROVED" > 0  -> Return "TASK: ARCHIVE".
       - IF "RESEARCHED" > 0 -> Return "TASK: REVIEW".
       - IF "EXTRACTED" > 0 -> Return "TASK: ANALYZE".
       - IF "PENDING" > 0   -> Return "TASK: EXTRACT".
       - ELSE               -> Return "TASK: DISCOVER".
    
    Return ONLY the Task String.
    """,
    tools=[get_queue_metrics]
)