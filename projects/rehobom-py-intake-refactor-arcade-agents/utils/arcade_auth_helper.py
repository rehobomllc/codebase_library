# utils/arcade_auth_helper.py

import asyncio
import logging
from typing import Callable, Awaitable, Any, Optional, Dict, TypeVar, Tuple

from arcadepy import AsyncArcade
from arcadepy import AuthenticationError as ArcadeAuthenticationError
from agents_arcade.errors import AuthorizationError as ArcadeAuthorizationError
from agents import Agent, Runner # For type hinting the callable
from agents.result import RunResult # Specific result type for Runner.run

logger = logging.getLogger(__name__)

# Generic TypeVar for the result of the agent operation, accommodating Runner.run or Runner.run_streamed
T_AgentResult = TypeVar('T_AgentResult')

class AuthHelperError(Exception):
    """Custom exception for auth helper specific issues."""
    def __init__(self, message: str, auth_url: Optional[str] = None, auth_id_for_wait: Optional[str] = None, requires_user_action: bool = False, is_api_key_invalid: bool = False):
        super().__init__(message)
        self.auth_url = auth_url
        self.auth_id_for_wait = auth_id_for_wait
        self.requires_user_action = requires_user_action # True if user needs to visit auth_url
        self.is_api_key_invalid = is_api_key_invalid # True if the API key itself is invalid

async def handle_auth_flow_explicitly(
    arcade_client: AsyncArcade,
    auth_id_for_wait: str,
    timeout_seconds: int = 300 # 5 minutes default timeout
) -> bool:
    """
    Handles the explicit waiting part of the authorization flow.
    This function is called after an AuthorizationError has provided an auth_id.

    Args:
        arcade_client: The AsyncArcade client instance.
        auth_id_for_wait: The ID obtained from AuthorizationError.result.id, used to wait for completion.
        timeout_seconds: How long to wait for user to complete authorization.

    Returns:
        True if authorization was completed successfully within the timeout, False otherwise.
    """
    logger.info(f"Waiting for user to complete authorization for auth_id: {auth_id_for_wait}. Timeout: {timeout_seconds}s.")
    try:
        await arcade_client.auth.wait_for_completion(auth_id_for_wait, timeout=timeout_seconds)
        logger.info(f"Authorization completed successfully for auth_id: {auth_id_for_wait}.")
        return True
    except asyncio.TimeoutError:
        logger.warning(f"Authorization timed out for auth_id: {auth_id_for_wait} after {timeout_seconds} seconds.")
        return False
    except Exception as e:
        logger.error(f"Error during wait_for_completion for auth_id {auth_id_for_wait}: {e}", exc_info=True)
        return False

AgentOperationCallable = Callable[..., Awaitable[T_AgentResult]]

async def run_agent_with_auth_handling(
    runner_callable: AgentOperationCallable[T_AgentResult],
    starting_agent: Agent,
    input_data: Any, # str or list of TResponseInputItem
    user_id: str,
    arcade_client: AsyncArcade,
    run_config_kwargs: Optional[Dict[str, Any]] = None, # For Runner.run context if needed beyond user_id
    max_operation_retries: int = 1, # How many times to retry the operation *after* a successful auth flow
    auth_timeout_seconds: int = 300,
    initial_attempt: bool = True # Internal flag to differentiate initial call from retries
) -> T_AgentResult:
    """
    Runs an agent operation, handling Arcade authorization errors by immediately
    returning authorization URLs without blocking, following Arcade best practices.

    Args:
        runner_callable: The async function to call to run the agent (e.g., Runner.run or Runner.run_streamed).
        starting_agent: The agent to start the run with.
        input_data: The input for the agent.
        user_id: The unique ID for the user, passed in context for Arcade auth.
        arcade_client: The AsyncArcade client instance.
        run_config_kwargs: Optional additional keyword arguments for the runner_callable (e.g., max_turns for Runner.run).
        max_operation_retries: Number of times to retry the operation after a successful auth.
        auth_timeout_seconds: NOT USED - included for API compatibility.
        initial_attempt: Tracks if this is the first attempt to run the operation.

    Returns:
        The result of the agent operation if successful.

    Raises:
        AuthHelperError: If authorization is required with URL for user to visit.
        Exception: Any other exception from the agent operation if not an ArcadeAuthorizationError.
    """
    if run_config_kwargs is None:
        run_config_kwargs = {}

    # Context for Runner.run must include user_id for Arcade tool authentication
    current_context = run_config_kwargs.pop("context", {})
    current_context["user_id"] = user_id
    
    try:
        logger.info(f"Attempting agent operation for user {user_id}. Agent: {starting_agent.name}. Initial attempt: {initial_attempt}")
        
        # For all calls, we need to handle them properly
        # Streaming calls return RunResultStreaming immediately, non-streaming are awaitable
        if hasattr(runner_callable, '__name__') and 'streamed' in runner_callable.__name__:
            # For streaming calls, call directly (no await) as they return RunResultStreaming immediately
            result = runner_callable(
                starting_agent=starting_agent,
                input=input_data,
                context=current_context,
                **run_config_kwargs
            )
            return result
        else:
            # For non-streaming calls, await the result
            return await runner_callable(
                starting_agent=starting_agent,
                input=input_data,
                context=current_context,
                **run_config_kwargs
            )
    except ArcadeAuthenticationError as e:
        # Invalid API key - this is a configuration issue, not a user authorization issue
        logger.error(f"ArcadeAuthenticationError for user {user_id}, agent {starting_agent.name}. Invalid API key: {e}")
        raise AuthHelperError(
            message=f"Arcade API key is invalid or expired. Please contact support to update the API credentials.",
            requires_user_action=False,
            is_api_key_invalid=True
        )
    except ArcadeAuthorizationError as e:
        tool_name = getattr(e, 'tool_name', 'Unknown Tool')
        toolkit_name = getattr(e, 'toolkit_name', 'Unknown Toolkit')
        auth_url = str(e) # The URL for the user to visit
        
        # Extract auth_id for wait_for_completion (from e.result.id as per doc example)
        auth_id_for_wait: Optional[str] = None
        if hasattr(e, 'result') and e.result and hasattr(e.result, 'id'):
            auth_id_for_wait = e.result.id
        elif hasattr(e, 'auth_id') and e.auth_id: # Fallback, though e.result.id is preferred by example
            auth_id_for_wait = e.auth_id
        
        logger.warning(
            f"ArcadeAuthorizationError for user {user_id}, agent {starting_agent.name}, "
            f"Tool: '{tool_name}', Toolkit: '{toolkit_name}'. Auth URL: {auth_url}, Auth ID for wait: {auth_id_for_wait}"
        )

        # Following Arcade best practices: immediately return authorization URL
        # Don't block the request - let the user authorize and retry
        logger.info(f"User {user_id} needs to authorize toolkit '{toolkit_name}'. URL: {auth_url}. "
                   f"Returning authorization URL immediately without blocking.")
        
        raise AuthHelperError(
            message=f"Please authorize access to {toolkit_name} tools and try again.",
            auth_url=auth_url,
            auth_id_for_wait=auth_id_for_wait,
            requires_user_action=True
        )
    except Exception as ex: # Catch any other non-ArcadeAuthorizationError exceptions
        logger.error(f"An unexpected error occurred during agent operation for user {user_id} (Agent: {starting_agent.name}): {ex}", exc_info=True)
        raise ex

async def check_toolkit_authorization_status(
    arcade_client: AsyncArcade,
    user_id: str,
    toolkit_name: str,
    test_agent: Agent, # A simple agent configured with one tool from the toolkit
    test_input: str = "Perform a quick test action." # Input to trigger the test tool
) -> Tuple[bool, Optional[str]]:
    """
    Proactively checks if a user is likely authorized for a specific Arcade toolkit
    by attempting a benign test call with a provided test agent.

    Args:
        arcade_client: The AsyncArcade client.
        user_id: The user's unique ID.
        toolkit_name: The name of the toolkit (e.g., "google", "github").
        test_agent: A simple agent configured with at least one tool from the target toolkit.
                    This agent will be used to make a test call.
        test_input: Input to the test_agent designed to invoke a simple tool from the toolkit.

    Returns:
        A tuple: (is_authorized: bool, message_or_auth_url: Optional[str])
                 If not authorized, message_or_auth_url will contain the auth_url.
    """
    logger.info(f"Proactively checking authorization status for user {user_id}, toolkit '{toolkit_name}'.")
    
    try:
        logger.debug(f"Probing authorization for toolkit '{toolkit_name}' using agent '{test_agent.name}' for user '{user_id}'.")
        await Runner.run(
            starting_agent=test_agent,
            input=test_input,
            context={"user_id": user_id},
            # Consider adding max_turns=1 or similar if Runner.run supports it directly in params
            # or via RunConfig passed in run_config_kwargs if this helper is extended.
        )
        logger.info(f"User {user_id} appears to be authorized for toolkit '{toolkit_name}' (proactive test call succeeded).")
        return True, f"User is authorized for '{toolkit_name}'."
    except ArcadeAuthorizationError as e:
        auth_url = str(e)
        logger.info(f"User {user_id} is NOT authorized for toolkit '{toolkit_name}'. Proactive check indicates auth needed. URL: {auth_url}")
        return False, auth_url # Return the auth URL
    except Exception as e:
        logger.error(f"Error during proactive auth check for toolkit '{toolkit_name}' with user '{user_id}': {e}", exc_info=True)
        return False, f"Could not determine authorization status for '{toolkit_name}' due to an error during the test call: {str(e)}"

