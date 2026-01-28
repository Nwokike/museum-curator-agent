import os
from dotenv import load_dotenv
from google.adk.agents import Agent

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Since the ADK models are Pydantic-based, we'll use a simpler 
# instantiation pattern to avoid the __pydantic_private__ error.

class GroqFallbackClient:
    """
    A simplified wrapper to provide the Groq model name 
    and key to the agents without inheritance conflicts.
    """
    def __init__(self):
        self.model = "groq/llama-3.3-70b-versatile"
        self.api_key = GROQ_API_KEY

class GeminiFallbackClient:
    """
    A simplified wrapper for Gemini-specific tasks.
    """
    def __init__(self):
        self.model = "gemini-2.0-flash-exp"
        self.api_key = GEMINI_API_KEY

# Helper function to create an agent with the right config
def create_curator_agent(name, instructions, tools=None):
    """
    Factory to create agents using the ADK standard while 
    ensuring keys are passed correctly.
    """
    # We use Gemini as the default for most agents for better reasoning
    return Agent(
        name=name,
        instructions=instructions,
        tools=tools or [],
        model="gemini-2.0-flash-exp", # Direct string is safer in 2026 ADK
        api_key=GEMINI_API_KEY
    )