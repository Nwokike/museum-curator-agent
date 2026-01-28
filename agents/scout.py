from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from agents.tools import capture_page_content, add_url_to_queue

# Initialize Model (Rank 2: High Speed)
scout_model = GroqFallbackClient() 
# We rely on the bridge to pick the right Llama model, but effectively we want "llama-4-scout"

scout_agent = Agent(
    name="MuseumScout",
    model=scout_model,
    description="Scans museum pages to find artifact URLs.",
    instruction="""
    You are the Museum Scout.
    1. You will be given a URL to a museum search result.
    2. Use `capture_page_content(url)` to read the page.
    3. Analyze the text to identify links to specific objects/artifacts.
    4. For every valid object found, call `add_url_to_queue(url, museum_name)`.
    5. Ignore unrelated links (privacy policy, contact, etc.).
    """,
    tools=[capture_page_content, add_url_to_queue]
)