from google.adk.agents import Agent
from modules.llm_bridge import GroqFallbackClient, GeminiFallbackClient
from agents.tools import google_search_tool, save_deep_desc_tool

# Models
research_model = GeminiFallbackClient() # Good context window for reading search results
synthesis_model = GroqFallbackClient()  # Good instruction following for writing

# --- RAG STEP 1: RETRIEVAL ---

context_searcher_agent = Agent(
    name="ContextSearcherAgent",
    model=research_model.model,
    description="Researcher. Finds external information.",
    instruction="""
    ROLE: Context Researcher
    GOAL: Find historical context for the specific artifact.
    
    PROTOCOL:
    1. Analyze the input (Title, Location, Museum).
    2. Formulate a targeted search query.
       - BAD: "Igbo masks history" (Too generic)
       - GOOD: "Maiden Spirit Mask 'Agbogho Mmuo' provenance Pitt Rivers Museum"
    3. Call `Google Search_tool(query)`.
    4. Return the raw search results.
    """,
    tools=[google_search_tool]
)

# --- RAG STEP 2: EXTRACTION (The Guardrail) ---

fact_extractor_agent = Agent(
    name="FactExtractorAgent",
    model=research_model.model,
    description="Fact Checker. Extracts verifiable quotes from noise.",
    instruction="""
    ROLE: Fact Extractor
    GOAL: Filter search results to prevent hallucination.
    
    INPUT: Raw Search Results.
    
    PROTOCOL:
    1. Read the search results.
    2. Extract VERBATIM QUOTES that confirm:
       - The object's specific usage (Ritual, utility, etc).
       - The materials used.
       - The specific village/region of origin.
    3. DISCARD generalities (e.g., "Africa is a continent...").
    4. If the search results are irrelevant or empty, return "NO_CONTEXT_FOUND".
    
    OUTPUT FORMAT:
    - Fact: [Quote] (Source: [Domain])
    - Fact: [Quote] (Source: [Domain])
    """,
    # No external tools, just processing text
    tools=[]
)

# --- RAG STEP 3: SYNTHESIS (Grounding) ---

synthesizer_agent = Agent(
    name="SynthesizerAgent",
    model=synthesis_model.model,
    description="Writer. Combines visual facts and history into a cited abstract.",
    instruction="""
    ROLE: Synthesizer
    GOAL: Write a 'Deep Description' (100 words) using strict citations.
    
    INPUT: 
    1. Visual Analysis (from Gemini Vision)
    2. Verified Facts (from Fact Extractor)
    3. Museum Metadata (Title/Date)
    
    STRICT RULES:
    1. NO GUESSING. If a fact isn't in the Input, do not write it.
    2. CITE EVERYTHING. 
       - If you describe the shape/color, append `[Visual]`.
       - If you describe the history/usage, append `[Source]`.
    3. If `Verified Facts` is "NO_CONTEXT_FOUND", write ONLY about the Visuals.
    
    EXAMPLE:
    "This mask features a white kaolin face with indigo markings [Visual]. It is identified as an 'Agbogho Mmuo' maiden spirit mask [Source], traditionally used during the dry season festivals [Source]. The superstructure is composed of sewn fabric and mirrors [Visual]."
    
    ACTION: Call `save_deep_desc_tool(artifact_id, text)`.
    """,
    tools=[save_deep_desc_tool]
)