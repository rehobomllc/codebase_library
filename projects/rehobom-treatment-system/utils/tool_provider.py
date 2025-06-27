#!/usr/bin/env python3
"""
Enhanced Unified Tool Provider
Optimizes tool loading across all agents with expanded toolkit support,
integrating both OpenAI native tools and comprehensive Arcade tools.
"""

import logging
from typing import List, Dict, Any, Optional, Callable, Awaitable

# Core SDKs for agents and Arcade tools
from agents import WebSearchTool, Tool as OpenAIAgentTool # OpenAI Agents SDK base Tool type
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools
from agents_arcade.errors import AuthorizationError, ToolError # Specific errors from Arcade

logger = logging.getLogger(__name__)

class EnhancedToolProvider:
    """
    Enhanced tool provider with expanded toolkit support and optimized loading
    for treatment-focused applications.
    """

    def __init__(self, arcade_client: Optional[AsyncArcade] = None):
        self.arcade_client: Optional[AsyncArcade] = arcade_client
        self._tool_cache: Dict[str, List[OpenAIAgentTool]] = {}
        
        # Define toolkit groups for different agent types
        self._toolkit_mapping = {
            "web": ["web"],
            "google": ["google"],
            "communication": ["google", "slack"],  # Email, calendar, team communication
            "healthcare": ["google", "web"],       # Healthcare-specific tools
            "documentation": ["google", "notion"], # Document management
            "social_media": ["linkedin", "x"],     # Professional networking
            "development": ["github"],             # For technical integrations
            "financial": ["stripe"],              # Payment processing
            "productivity": ["google", "notion", "slack"],
            "research": ["web", "google", "arxiv"], # Research and literature
            "monitoring": ["web", "google"],       # Site monitoring
        }
        
        logger.info(f"EnhancedToolProvider initialized. Arcade client {'present' if arcade_client else 'not present'}.")

    async def get_tools(self, requested_toolkits: List[str]) -> List[OpenAIAgentTool]:
        """
        Enhanced tool loading with caching and expanded toolkit support.
        
        Args:
            requested_toolkits: List of toolkit names or toolkit groups
            
        Returns:
            List of loaded tools
        """
        cache_key = ",".join(sorted(requested_toolkits))
        
        if cache_key in self._tool_cache:
            logger.debug(f"Returning cached tools for toolkits: {requested_toolkits}")
            return self._tool_cache[cache_key]

        loaded_tools: List[OpenAIAgentTool] = []
        
        # Expand toolkit groups to individual toolkits
        expanded_toolkits = self._expand_toolkit_groups(requested_toolkits)
        
        for toolkit_name in expanded_toolkits:
            try:
                toolkit_tools = await self._load_toolkit_by_name(toolkit_name)
                loaded_tools.extend(toolkit_tools)
                logger.debug(f"Loaded {len(toolkit_tools)} tools from '{toolkit_name}' toolkit")
            except Exception as e:
                logger.warning(f"Failed to load toolkit '{toolkit_name}': {e}", exc_info=True)
                continue

        # Cache the results
        self._tool_cache[cache_key] = loaded_tools
        
        tool_names_loaded = [getattr(tool, 'name', str(tool)) for tool in loaded_tools]
        logger.info(f"Total tools provided: {len(loaded_tools)} for requested toolkits: {requested_toolkits}. Tool names: {tool_names_loaded}")
        
        return loaded_tools

    def _expand_toolkit_groups(self, requested_toolkits: List[str]) -> List[str]:
        """Expand toolkit groups to individual toolkit names."""
        expanded = set()
        
        for toolkit in requested_toolkits:
            if toolkit in self._toolkit_mapping:
                expanded.update(self._toolkit_mapping[toolkit])
            else:
                expanded.add(toolkit)
        
        return list(expanded)

    async def _load_toolkit_by_name(self, toolkit_name: str) -> List[OpenAIAgentTool]:
        """Enhanced toolkit loading with support for more toolkits."""
        toolkit_loaders = {
            "web": self._load_web_tools,
            "google": self._load_google_suite_tools,
            "slack": lambda: self._fetch_arcade_tools_safely(["slack"]),
            "linkedin": lambda: self._fetch_arcade_tools_safely(["linkedin"]),
            "x": lambda: self._fetch_arcade_tools_safely(["x"]),
            "github": lambda: self._fetch_arcade_tools_safely(["github"]),
            "notion": lambda: self._fetch_arcade_tools_safely(["notion"]),
            "stripe": lambda: self._fetch_arcade_tools_safely(["stripe"]),
            "arxiv": lambda: self._fetch_arcade_tools_safely(["arxiv"]),
        }
        
        loader = toolkit_loaders.get(toolkit_name)
        if loader:
            return await loader()
        else:
            logger.warning(f"Unknown toolkit '{toolkit_name}'. Attempting to load via Arcade.")
            return await self._fetch_arcade_tools_safely([toolkit_name])

    async def _load_web_tools(self) -> List[OpenAIAgentTool]:
        """Load enhanced web scraping and search tools."""
        tools: List[OpenAIAgentTool] = []

        # 1. Add OpenAI's native WebSearchTool
        try:
            openai_web_search = WebSearchTool(search_context_size="high")
            tools.append(openai_web_search)
            logger.debug("Loaded OpenAI WebSearchTool with high context size.")
        except Exception as e:
            logger.warning(f"Could not load OpenAI WebSearchTool: {e}", exc_info=True)

        # 2. Add Arcade's comprehensive web toolkit (includes Firecrawl, advanced scraping)
        arcade_web_tools = await self._fetch_arcade_tools_safely(["web"])
        if arcade_web_tools:
            tools.extend(arcade_web_tools)
            logger.debug(f"Loaded {len(arcade_web_tools)} tools from Arcade 'web' toolkit.")
        
        return tools

    async def _load_google_suite_tools(self) -> List[OpenAIAgentTool]:
        """Load Google Suite tools with enhanced capabilities."""
        google_tools = await self._fetch_arcade_tools_safely(["google"])
        if google_tools:
            logger.debug(f"Loaded {len(google_tools)} tools from Arcade 'google' toolkit.")
        return google_tools

    async def _fetch_arcade_tools_safely(self, arcade_toolkit_names: List[str]) -> List[OpenAIAgentTool]:
        """
        Safely fetches tools from Arcade with enhanced error handling.
        """
        if not self.arcade_client:
            logger.warning(f"Arcade client not available. Cannot load Arcade toolkits: {arcade_toolkit_names}.")
            return []

        try:
            fetched_tools: List[OpenAIAgentTool] = await get_arcade_tools(
                self.arcade_client,
                toolkits=arcade_toolkit_names
            )
            logger.info(f"Successfully fetched {len(fetched_tools)} tools for Arcade toolkits: {arcade_toolkit_names}.")
            return fetched_tools
        except AuthorizationError as auth_err:
            logger.error(f"Authorization error while fetching Arcade toolkits {arcade_toolkit_names}: {auth_err}")
            return []
        except ToolError as tool_err:
            logger.error(f"Tool error while fetching Arcade toolkits {arcade_toolkit_names}: {tool_err}")
            return []
        except ImportError as ie:
            logger.critical(f"ImportError related to agents_arcade: {ie}. Check installations.")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Arcade toolkits {arcade_toolkit_names}: {e}")
            return []

    def create_tool_getter(self) -> Callable[[List[str]], Awaitable[List[OpenAIAgentTool]]]:
        """Create a tool getter function for agent creation."""
        async def get_tools_func(requested_toolkits: List[str]) -> List[OpenAIAgentTool]:
            return await self.get_tools(requested_toolkits)
        return get_tools_func

    async def get_specialized_tools_for_agent_type(self, agent_type: str) -> List[OpenAIAgentTool]:
        """Get optimized tool sets for specific agent types."""
        agent_toolkits = {
            "triage": ["web", "google"],
            "facility_search": ["web", "google"],
            "insurance_verification": ["google", "web"],
            "appointment_scheduler": ["google"],
            "intake_form": ["google"],
            "communication": ["google", "slack"],
            "essay_extractor": ["web"],
            "treatment_monitor": ["web", "google"],
            "research": ["web", "google", "arxiv"],
            "social_outreach": ["linkedin", "x"],
        }
        
        toolkits = agent_toolkits.get(agent_type, ["web", "google"])
        return await self.get_tools(toolkits)

# --- Backward Compatibility ---
# Keep the old class name as an alias
UnifiedToolProvider = EnhancedToolProvider

# --- Global Tool Provider Management ---
_global_tool_provider_instance: Optional[EnhancedToolProvider] = None

def initialize_tool_provider(arcade_client: Optional[AsyncArcade] = None) -> EnhancedToolProvider:
    """Initialize the global enhanced tool provider instance."""
    global _global_tool_provider_instance
    _global_tool_provider_instance = EnhancedToolProvider(arcade_client)
    logger.info("Global EnhancedToolProvider has been initialized.")
    return _global_tool_provider_instance

def get_tool_provider() -> Optional[EnhancedToolProvider]:
    """Get the global tool provider instance."""
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
