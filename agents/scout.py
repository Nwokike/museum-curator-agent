from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from agents.tools import (
    visit_page_tool, extract_links_tool, check_db_tool, add_to_queue_tool,
    scrape_metadata_tool, download_image_tool, save_draft_tool
)

# Shared Model (Llama 4 / Groq)
scout_model = GroqFallbackClient()

# --- Cluster A: Discovery Squad ---

navigator_agent = Agent(
    name="NavigatorAgent",
    model=scout_model,
    description="Browser Operator. Navigates to URLs.",
    instruction="""
    You are the Navigator.
    1. Receive a URL.
    2. Call `visit_page_tool(url)`.
    3. Return the tool output.
    """,
    tools=[visit_page_tool]
)

link_extractor_agent = Agent(
    name="LinkExtractorAgent",
    model=scout_model,
    description="HTML Analyst. Finds artifact links.",
    instruction="""
    You are the Link Extractor.
    1. You are on a search result page.
    2. Call `extract_links_tool` with the base URL.
    3. Return the JSON list of links found.
    """,
    tools=[extract_links_tool]
)

deduplicator_agent = Agent(
    name="DeduplicatorAgent",
    model=scout_model,
    description="Database Gatekeeper. Checks for duplicates.",
    instruction="""
    You are the Deduplicator.
    1. Receive a list of URLs.
    2. For each URL, call `check_db_tool`.
    3. If result is 'NEW', return the URL.
    4. Ignore 'EXISTS'.
    """,
    tools=[check_db_tool]
)

queue_manager_agent = Agent(
    name="QueueManagerAgent",
    model=scout_model,
    description="Queue Clerk. Adds items to DB.",
    instruction="""
    You are the Queue Manager.
    1. Receive a new URL and a Museum Name.
    2. Call `add_to_queue_tool`.
    3. Return the new Artifact ID.
    """,
    tools=[add_to_queue_tool]
)

# --- Cluster B: Extraction Squad ---

html_parser_agent = Agent(
    name="HTMLParserAgent",
    model=scout_model,
    description="Metadata Scraper. Reads text from page.",
    instruction="""
    You are the HTML Parser.
    1. Call `scrape_metadata_tool(url)`.
    2. Review the JSON. Identify the Accession Number, Title, and Description.
    3. Call `save_draft_tool` to save it to the DB.
    """,
    tools=[scrape_metadata_tool, save_draft_tool]
)

downloader_agent = Agent(
    name="DownloaderAgent",
    model=scout_model,
    description="Asset Manager. Downloads high-res files.",
    instruction="""
    You are the Downloader.
    1. You need to find the image URL on the page (scrape or regex).
    2. Call `download_image_tool(image_url, artifact_id)`.
    3. Ensure the file is saved successfully.
    """,
    # Note: We rely on the model's logic or an extra tool to FIND the image src from the HTML. 
    # For now, we assume the HTMLParser passes the image URL or we add a specific 'find_image_src' tool later.
    tools=[download_image_tool] 
)