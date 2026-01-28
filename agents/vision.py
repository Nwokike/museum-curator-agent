from google.adk.agents import Agent
from modules.llm_bridge import GeminiFallbackClient
from agents.tools import save_artifact_data
from modules.browser import browser_instance

# Initialize Model (Rank 1: Vision Expert)
vision_model = GeminiFallbackClient()

async def analyze_visual_state(url: str, id: str):
    """
    Custom Tool: Takes a screenshot and asks Gemini to extract data.
    """
    if not browser_instance.page:
        await browser_instance.launch()
    
    page = browser_instance.page
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    
    # Take Screenshot (In memory)
    screenshot_bytes = await page.screenshot(format="jpeg")
    
    # We return the screenshot bytes directly. 
    # The ADK Runner handles passing this to Gemini.
    return {
        "image": screenshot_bytes,
        "instruction": f"Extract metadata for ID {id}. Fields: Title, Date, Materials, Dimensions, Description."
    }

vision_agent = Agent(
    name="ArtifactReader",
    model=vision_model,
    description="Extracts strict metadata from artifact images.",
    instruction="""
    You are the Artifact Reader.
    1. Call `analyze_visual_state(url)` to see the object.
    2. Extract the following fields into JSON:
       - Title
       - Date Created
       - Materials
       - Dimensions
       - Museum Description
    3. Call `save_artifact_data(id, title, json_data)` to save it.
    """,
    tools=[analyze_visual_state, save_artifact_data]
)