from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from modules.db import get_connection

# Initialize Model
orch_model = GroqFallbackClient()

def get_queue_metrics(check_updates: bool = True):
    """
    Returns the count of artifacts in each stage of the pipeline
    and the next high-priority artifact ID for each stage.
    
    Args:
        check_updates: Ignored dummy argument to ensure tool call robustness.
    """
    conn = get_connection()
    metrics = {}
    next_tasks = {}
    
    try:
        with conn.cursor() as cur:
            # Get Counts
            cur.execute("SELECT status, COUNT(*) FROM artifact_queue GROUP BY status")
            rows = dict(cur.fetchall())
            metrics = {
                "PENDING": rows.get("PENDING", 0),       # Needs Extraction
                "EXTRACTED": rows.get("EXTRACTED", 0),   # Needs Vision/Research
                "RESEARCHED": rows.get("RESEARCHED", 0), # Needs Review
                "APPROVED": rows.get("APPROVED", 0),     # Needs Upload
                "ARCHIVED": rows.get("ARCHIVED", 0)
            }
            
            # Get Next Priorities
            for status in ["APPROVED", "RESEARCHED", "EXTRACTED", "PENDING"]:
                cur.execute("SELECT id, url, museum_name FROM artifact_queue WHERE status = %s ORDER BY created_at ASC LIMIT 1", (status,))
                item = cur.fetchone()
                if item:
                    next_tasks[status] = item
                    
            return {"metrics": metrics, "next_task": next_tasks}
    finally:
        conn.close()

coordinator_agent = Agent(
    name="CoordinatorAgent",
    model=orch_model.model,
    description="The Chief Curator. Manages the global state and assigns tasks to specialized squads.",
    instruction="""
    You are the Chief Curator (Coordinator).
    
    YOUR GOAL: 
    Maintain a smooth flow of artifacts from 'Discovery' to 'Archival'.
    
    PROTOCOL:
    1. Call `get_queue_metrics(check_updates=True)` to assess metrics.
    2. PRIORITIZE tasks strictly in this order (Downstream > Upstream):
       - PRIORITY 1 [ARCHIVAL]: If 'APPROVED' > 0, assign 'ARCHIVE_JOB' for that ID.
       - PRIORITY 2 [REVIEW]: If 'RESEARCHED' > 0, assign 'REVIEW_JOB' for that ID.
       - PRIORITY 3 [ANALYSIS]: If 'EXTRACTED' > 0, assign 'ANALYZE_JOB' for that ID.
       - PRIORITY 4 [EXTRACTION]: If 'PENDING' > 0, assign 'EXTRACT_JOB' for that ID (and its URL).
       - PRIORITY 5 [DISCOVERY]: If queues are empty, assign 'DISCOVER_JOB'.
       
    OUTPUT FORMAT (JSON):
    Return a valid JSON object defining the assignment:
    {
        "action": "ARCHIVE_JOB" | "REVIEW_JOB" | "ANALYZE_JOB" | "EXTRACT_JOB" | "DISCOVER_JOB" | "SLEEP",
        "target_id": "PRM_12345" or null,
        "context": { "url": "..." } or null,
        "reasoning": "Brief explanation of why this task was chosen."
    }
    """,
    tools=[get_queue_metrics]
)