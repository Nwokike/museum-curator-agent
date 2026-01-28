from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from agents.tools import send_telegram_review_tool, upload_to_hf_tool, delete_temp_files_tool

# Initialize Model (Llama 4 - Logic)
ops_model = GroqFallbackClient()

# --- Cluster E: The Archival Squad ---

draft_reviewer_agent = Agent(
    name="DraftReviewerAgent",
    model=ops_model,
    description="Liaison. Sends drafts to Telegram for human review.",
    instruction="""
    You are the Reviewer.
    1. Receive an Artifact ID.
    2. Call `send_telegram_review_tool(artifact_id)`.
    3. If successful, return "REVIEW_SENT".
    """,
    tools=[send_telegram_review_tool]
)

hf_uploader_agent = Agent(
    name="HFUploaderAgent",
    model=ops_model,
    description="Archivist. Uploads approved data to Hugging Face.",
    instruction="""
    You are the Uploader.
    1. Receive an Artifact ID.
    2. Call `upload_to_hf_tool(artifact_id)`.
    3. If successful, return "UPLOAD_COMPLETE".
    """,
    tools=[upload_to_hf_tool]
)

cleaner_agent = Agent(
    name="CleanerAgent",
    model=ops_model,
    description="Janitor. Deletes temp files after upload.",
    instruction="""
    You are the Cleaner.
    1. Receive an Artifact ID.
    2. Call `delete_temp_files_tool(artifact_id)`.
    3. Return "CLEANED".
    """,
    tools=[delete_temp_files_tool]
)