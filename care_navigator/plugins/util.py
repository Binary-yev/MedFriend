"""Utility functions for plugins."""

from google.adk import runners
from google.genai import types

Runner = runners.Runner

# Author returned by `run_prompt` when the agent could not be reached or
# produced no response. Callers use this to tell a genuine verdict apart from a
# failure, rather than trying to parse the returned text.
ERROR_AUTHOR = "SYSTEM"

_NO_RESPONSE_MESSAGE = "No response from the agent."


async def run_prompt(
    user_id: str,
    app_name: str,
    runner: Runner,
    message: types.Content,
    session_id: str | None = None,
) -> tuple[str, str]:
    """Runs a prompt using the provided runner and returns the response.

    Returns:
        A `(author, text)` pair. `author` is `ERROR_AUTHOR` when the run failed
        or yielded nothing, in which case `text` is the error detail rather than
        an agent response.
    """
    try:
        if session_id is not None:
            session = await runner.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
        else:
            session = await runner.session_service.create_session(
                user_id=user_id,
                app_name=app_name,
            )
        if not session:
            raise ValueError("Session is None")

        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                return (
                    event.author,
                    (event.content.parts[0].text or ""),
                )

    except Exception as e:
        return ERROR_AUTHOR, str(e)

    return ERROR_AUTHOR, _NO_RESPONSE_MESSAGE
