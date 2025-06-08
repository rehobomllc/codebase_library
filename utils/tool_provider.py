#!/usr/bin/env python3
"""
Unified Tool Provider
Standardizes tool loading across all agents with a consistent interface,
integrating both OpenAI native tools and Arcade tools.
"""

import logging
from typing import List, Dict, Any, Optional, Callable, Awaitable

# Core SDKs for agents and Arcade tools
from agents import WebSearchTool, Tool as OpenAIAgentTool # OpenAI Agents SDK base Tool type
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools
from agents_arcade.errors import AuthorizationError, ToolError # Specific errors from Arcade

logger = logging.getLogger(__name__)

class UnifiedToolProvider:
    """
    Standardized tool provider that handles both Arcade and OpenAI tools
    with a consistent interface across all agents.
    """

    def __init__(self, arcade_client: Optional[AsyncArcade] = None):
        self.arcade_client: Optional[AsyncArcade] = arcade_client
        self._tool_cache: Dict[str, List[OpenAIAgentTool]] = {}
        logger.info(f"UnifiedToolProvider initialized. Arcade client {'present' if arcade_client else 'not present'}.")

    async def get_tools(self, requested_toolkits: List[str]) -> List[OpenAIAgentTool]:
        """
        Unified tool getter that loads tools based on requested toolkit names.

        Args:
            requested_toolkits: List of toolkit names (e.g., ["web", "google"]).
                                "google" toolkit provides Drive, Docs, Calendar, and Gmail tools via Arcade.

        Returns:
            List of configured tool objects compatible with OpenAI Agents SDK.
        """
        if not requested_toolkits:
            logger.debug("No toolkits requested, returning empty list.")
            return []

        loaded_tools: List[OpenAIAgentTool] = []
        # Use a set to avoid loading the same toolkit multiple times if duplicated in input
        unique_toolkits = sorted(list(set(requested_toolkits)))

        for toolkit_name in unique_toolkits:
            cache_key = f"toolkit_{toolkit_name}"

            if cache_key in self._tool_cache:
                logger.debug(f"Using cached tools for toolkit: '{toolkit_name}'")
                loaded_tools.extend(self._tool_cache[cache_key])
                continue

            try:
                logger.info(f"Loading tools for toolkit: '{toolkit_name}'...")
                toolkit_specific_tools = await self._load_toolkit_by_name(toolkit_name)
                self._tool_cache[cache_key] = toolkit_specific_tools
                loaded_tools.extend(toolkit_specific_tools)
                logger.info(f"Successfully loaded {len(toolkit_specific_tools)} tools for toolkit: '{toolkit_name}'. Cache updated.")
            except Exception as e:
                logger.error(f"Failed to load toolkit '{toolkit_name}': {e}", exc_info=True)
                # Continue with other toolkits rather than failing entirely
                continue
        
        tool_names_loaded = [tool.name if hasattr(tool, 'name') else str(type(tool)) for tool in loaded_tools]
        logger.info(f"Total tools provided: {len(loaded_tools)} for requested toolkits: {requested_toolkits}. Tool names: {tool_names_loaded}")
        return loaded_tools

    async def _load_toolkit_by_name(self, toolkit_name: str) -> List[OpenAIAgentTool]:
        """Helper method to load tools for a specific toolkit by its name."""
        if toolkit_name == "web":
            return await self._load_web_tools()
        elif toolkit_name == "google":
            # The "google" toolkit from Arcade includes Drive, Docs, Calendar, and Gmail.
            return await self._load_google_suite_tools()
        # Add other specific toolkit loading logic here if needed in the future
        # e.g., elif toolkit_name == "github":
        #           return await self._fetch_arcade_tools_safely(["github"])
        else:
            logger.warning(f"Unknown or unsupported toolkit requested: '{toolkit_name}'. Attempting to load via Arcade.")
            # Default to trying to load it as an Arcade toolkit
            return await self._fetch_arcade_tools_safely([toolkit_name])


    async def _load_web_tools(self) -> List[OpenAIAgentTool]:
        """Load web scraping and search tools."""
        tools: List[OpenAIAgentTool] = []

        # 1. Add OpenAI's native WebSearchTool
        try:
            # Configure with high context for potentially better, more comprehensive search snippets.
            openai_web_search = WebSearchTool(search_context_size="high")
            tools.append(openai_web_search)
            logger.debug("Loaded OpenAI WebSearchTool with high context size.")
        except Exception as e:
            logger.warning(f"Could not load OpenAI WebSearchTool: {e}", exc_info=True)

        # 2. Add Arcade's "web" toolkit (e.g., for advanced scraping via Firecrawl)
        # These are conditional on the Arcade client being available.
        arcade_web_tools = await self._fetch_arcade_tools_safely(["web"])
        if arcade_web_tools:
            tools.extend(arcade_web_tools)
            logger.debug(f"Loaded {len(arcade_web_tools)} tools from Arcade 'web' toolkit.")
        
        return tools

    async def _load_google_suite_tools(self) -> List[OpenAIAgentTool]:
        """
        Load Google Suite tools (Drive, Docs, Calendar, Gmail) via Arcade's "google" toolkit.
        """
        # These tools require an Arcade client.
        google_tools = await self._fetch_arcade_tools_safely(["google"])
        if google_tools:
            logger.debug(f"Loaded {len(google_tools)} tools from Arcade 'google' toolkit (covers Drive, Docs, Calendar, Gmail).")
        return google_tools

    async def _fetch_arcade_tools_safely(self, arcade_toolkit_names: List[str]) -> List[OpenAIAgentTool]:
        """
        Safely fetches tools from the Arcade client for the given toolkit names.
        Handles cases where the client might not be available or tool fetching fails.
        """
        if not self.arcade_client:
            logger.warning(f"Arcade client not available. Cannot load Arcade toolkits: {arcade_toolkit_names}.")
            return []

        try:
            # `get_arcade_tools` is designed to return tools compatible with openai-agents SDK
            fetched_tools: List[OpenAIAgentTool] = await get_arcade_tools(
                self.arcade_client,
                toolkits=arcade_toolkit_names
            )
            logger.info(f"Successfully fetched {len(fetched_tools)} tools for Arcade toolkits: {arcade_toolkit_names}.")
            return fetched_tools
        except AuthorizationError as auth_err:
            logger.error(f"Authorization error while fetching Arcade toolkits {arcade_toolkit_names}: {auth_err}. User may need to authenticate via URL: {auth_err.auth_url}", exc_info=True)
            # Depending on app flow, this might need to be re-raised or communicated to the user.
            # For now, returning empty list for this toolkit.
            return []
        except ToolError as tool_err:
            logger.error(f"Tool error while fetching Arcade toolkits {arcade_toolkit_names}: {tool_err}", exc_info=True)
            return []
        except ImportError as ie: # Should not happen if dependencies are correct
            logger.critical(f"ImportError related to agents_arcade: {ie}. Check installations.", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching Arcade toolkits {arcade_toolkit_names}: {e}", exc_info=True)
            return []

    def create_tool_getter(self) -> Callable[[List[str]], Awaitable[List[OpenAIAgentTool]]]:
        """
        Creates a standardized asynchronous tool getter function suitable for agent initialization.

        Returns:
            An async function that takes a list of toolkit names and returns a list of tools.
        """
        async def get_tools_for_agent(toolkits: List[str]) -> List[OpenAIAgentTool]:
            return await self.get_tools(toolkits)
        
        logger.debug("Created a new tool getter function for agent initialization.")
        return get_tools_for_agent

# --- Global Tool Provider Management ---
_global_tool_provider_instance: Optional[UnifiedToolProvider] = None

def initialize_tool_provider(arcade_client: Optional[AsyncArcade] = None) -> UnifiedToolProvider:
    """
    Initializes or re-initializes the global tool provider instance.
    This should be called once at application startup.
    """
    global _global_tool_provider_instance
    _global_tool_provider_instance = UnifiedToolProvider(arcade_client)
    logger.info("Global UnifiedToolProvider has been initialized.")
    return _global_tool_provider_instance

def get_tool_provider() -> Optional[UnifiedToolProvider]:
    """
    Retrieves the globally available instance of the UnifiedToolProvider.
    Returns None if `initialize_tool_provider` has not been called.
    """
    if _global_tool_provider_instance is None:
        logger.warning("Attempted to get tool provider before initialization.")
    return _global_tool_provider_instance

async def get_unified_tools_for_agent_creation(toolkits: List[str]) -> List[OpenAIAgentTool]:
    """
    Convenience async function for getting tools using the global provider.
    Primarily intended for direct use in agent creation logic if a direct async call is preferred
    over passing the getter function.

    Args:
        toolkits: List of toolkit names (e.g., ["web", "google"]).

    Returns:
        List of tool objects.
    """
    provider = get_tool_provider()
    if not provider:
        logger.error("Global tool provider is not initialized. Cannot fetch tools.")
        # Potentially raise an error here or ensure initialization logic prevents this state.
        # For now, returning empty to avoid crashing if called prematurely.
        return []
    
    return await provider.get_tools(toolkits)

# Example usage (for testing or direct calls if needed, typically agents get the getter function)
# async def main_test():
#     # This would be set up in your main application (e.g., app.py)
#     # from arcadepy import AsyncArcade
#     # arcade_api_key = "YOUR_ARCADE_API_KEY" # From config
#     # if arcade_api_key:
#     #     client = AsyncArcade(api_key=arcade_api_key)
#     #     initialize_tool_provider(client)
#     # else:
#     #     initialize_tool_provider() # Initialize without Arcade client if no key
# 
#     # Simulate an agent needing tools
#     needed_toolkits = ["web", "google"]
#     tools_for_agent = await get_unified_tools_for_agent_creation(needed_toolkits)
#     print(f"Got {len(tools_for_agent)} tools for {needed_toolkits}:")
#     for tool in tools_for_agent:
#         print(f" - {getattr(tool, 'name', type(tool).__name__)}")

# if __name__ == "__main__":
#     import asyncio
#     logging.basicConfig(level=logging.INFO)
#     # To run this test, you'd need to provide an ARCADE_API_KEY environment variable
#     # or modify the main_test function to instantiate AsyncArcade correctly.
#     # asyncio.run(main_test())
