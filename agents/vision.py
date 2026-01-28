from google.adk.agents import Agent
from modules.llm_bridge import GeminiFallbackClient
from agents.tools import analyze_image_tool, save_visual_analysis_tool

# Cluster C: The Vision Squad (Gemini 3 Flash)
vision_model = GeminiFallbackClient()

visual_analyst_agent = Agent(
    name="VisualAnalystAgent",
    model=vision_model,
    description="Visual Expert. Analyzes the physical reality of the artifact.",
    instruction="""
    You are the Visual Analyst.
    1. Call `analyze_image_tool(artifact_id)` to retrieve the image file.
    2. ANALYZE the image. Focus on:
       - Medium (e.g., Sepia print, Wood carving).
       - Condition (e.g., Faded, cracked).
       - Visible Objects (e.g., Machetes, beads).
    3. Do NOT interpret history. Just describe what you see.
    4. Call `save_visual_analysis_tool(artifact_id, description)` to save the report.
    """,
    tools=[analyze_image_tool, save_visual_analysis_tool]
)