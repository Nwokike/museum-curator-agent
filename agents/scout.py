from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient
from agents.tools import (
    visit_page_tool, click_next_page_tool, extract_links_tool, 
    check_db_tool, add_to_queue_tool, scrape_metadata_tool, 
    download_image_tool, save_draft_tool
)

# Shared Model
scout_model = GroqFallbackClient()

# --- Cluster A: Discovery Squad ---

navigator_agent = Agent(
    name="NavigatorAgent",
    model=scout_model.model,
    description="Browser Operator. Navigates pages.",
    instruction="""
    ROLE: Navigator
    TASK: Manage Browser Location.
    
    COMMANDS:
    1. If instruction is "GOTO [URL]": Call `visit_page_tool(url)`.
    2. If instruction is "NEXT PAGE": Call `click_next_page_tool()`.
    
    OUTPUT: Return the tool result status.
    """,
    tools=[visit_page_tool, click_next_page_tool]
)

link_extractor_agent = Agent(
    name="LinkExtractorAgent",
    model=scout_model.model,
    description="HTML Analyst. Finds artifact links.",
    instruction="""
    ROLE: Link Extractor
    TASK: Scan the current page for object hyperlinks.
    ACTION: Call `extract_links_tool(base_url)`.
    OUTPUT: JSON list of links.
    """,
    tools=[extract_links_tool]
)

deduplicator_agent = Agent(
    name="DeduplicatorAgent",
    model=scout_model.model,
    description="Database Gatekeeper. Checks for duplicates.",
    instruction="""
    ROLE: Deduplicator
    TASK: Filter a list of URLs against the database.
    ACTION: 
    1. For each URL in the list, call `check_db_tool(url)`.
    2. Return ONLY the URLs that return 'NEW'.
    """,
    tools=[check_db_tool]
)

queue_manager_agent = Agent(
    name="QueueManagerAgent",
    model=scout_model.model,
    description="Queue Clerk. Adds items to DB.",
    instruction="""
    ROLE: Queue Manager
    TASK: Register new artifacts.
    ACTION: Call `add_to_queue_tool(url, museum_name)` for every valid URL provided.
    """,
    tools=[add_to_queue_tool]
)

# --- Cluster B: Extraction Squad ---

html_parser_agent = Agent(
    name="HTMLParserAgent",
    model=scout_model.model,
    description="Metadata Scraper. Extracts text and asset URLs.",
    instruction="""
    ROLE: HTML Parser
    TASK: Extract metadata and identify ALL High-Res Image URLs.
    ACTION: 
    1. Call `scrape_metadata_tool(url)`.
    2. ANALYZE the JSON output. 
    3. Call `save_draft_tool(artifact_id, metadata_json)`.
    4. CRITICAL: Output the `media_urls` list explicitly for the next agent.
    """,
    tools=[scrape_metadata_tool, save_draft_tool]
)

downloader_agent = Agent(
    name="DownloaderAgent",
    model=scout_model.model,
    description="Asset Manager. Downloads binary files.",
    instruction="""
    ROLE: Asset Manager
    TASK: Download the image file to local storage.
    INPUT: `image_url` and `artifact_id`.
    ACTION: Call `download_image_tool(image_url, artifact_id)`.
    NOTE: Do not search for the URL. It must be provided to you.
    """,
    tools=[download_image_tool]
)