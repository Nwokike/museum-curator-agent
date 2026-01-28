from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient, GeminiFallbackClient
from agents.tools import google_search_tool, save_deep_desc_tool


research_model = GeminiFallbackClient()
synthesis_model = GroqFallbackClient()

context_searcher_agent = Agent(
    name="ContextSearcherAgent",
    model=research_model,
    description="Researcher. Googles for historical context.",
    instruction="""
    You are the Context Searcher.
    1. Receive a Title and Location.
    2. Formulate a search query (e.g., "History of [Title] in [Location]").
    3. Call `Google Search_tool(query)`.
    4. Return the search summary.
    """,
    tools=[google_search_tool]
)

synthesizer_agent = Agent(
    name="SynthesizerAgent",
    model=synthesis_model,
    description="Writer. Combines visual facts and history into a deep description.",
    instruction="""
    You are the Synthesizer.
    1. Input: Visual Analysis + Search Results + Museum Metadata.
    2. Task: Write a 'Deep Description' (approx 100 words).
       - Start with the visual medium.
       - Describe the content/action.
       - End with the historical significance.
    3. Call `save_deep_desc_tool(artifact_id, text)`.
    """,
    tools=[save_deep_desc_tool]
)