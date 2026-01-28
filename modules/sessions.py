from google.adk.sessions import InMemorySessionService
from google.adk import Runner

_global_session_service = InMemorySessionService()

def get_agent_runner(agent, session_id: str, user_id: str = "admin", app_name: str = "IgboCurator") -> Runner:
    """
    Factory function that returns a Runner connected to the GLOBAL memory.
    
    Args:
        agent: The ADK Agent instance (e.g., visual_analyst_agent)
        session_id: The unique ID for the conversation (e.g., "artifact_PRM_12345")
    """
    return Runner(
        agent=agent,
        session_service=_global_session_service,
        app_name=app_name
    )