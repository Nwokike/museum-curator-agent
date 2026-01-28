from google.adk.agents import Agent
from modules.llm_bridge import GeminiFallbackClient
from agents.tools import google_search_tool, finalize_archive_entry

historian_model = GeminiFallbackClient()

historian_agent = Agent(
    name="CultureBot",
    model=historian_model,
    description="Researches cultural context and writes descriptions.",
    instruction="""
    You are the Historian.
    1. You will receive an Artifact Title and Museum Description.
    2. Use `Google Search_tool` to find the Igbo cultural significance (e.g., 'usage of Agbogho Mmuo').
    3. Synthesize a 50-word abstract that combines the visual facts with the cultural context.
    4. Call `finalize_archive_entry(id, abstract)` to finish the job.
    """,
    tools=[google_search_tool, finalize_archive_entry]
)