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

async def create_session_if_needed(session_id: str, user_id: str = "admin", app_name: str = "IgboCurator"):
    """
    Ensures a session exists in the global memory service.
    """
    exists = await _global_session_service.get_session(session_id=session_id, user_id=user_id, app_name=app_name)
    if not exists:
        await _global_session_service.create_session(
            session_id=session_id,
            user_id=user_id,
            app_name=app_name
        )