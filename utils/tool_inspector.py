#!/usr/bin/env python3
"""
Arcade Tool Inspector

Utility to inspect and document available tools from Arcade toolkits.
"""

import asyncio
import logging
import ssl
import certifi
import httpx
from typing import Dict, List, Any, Optional
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools

logger = logging.getLogger(__name__)

async def inspect_toolkit_tools(arcade_client: AsyncArcade, toolkit_name: str) -> Dict[str, Any]:
    """
    Inspect all tools available in a specific Arcade toolkit.
    
    Args:
        arcade_client: AsyncArcade client
        toolkit_name: Name of the toolkit to inspect
        
    Returns:
        Dictionary with toolkit info and tool details
    """
    try:
        print(f"  Attempting to load {toolkit_name} toolkit...")
        tools = await get_arcade_tools(arcade_client, [toolkit_name])
        
        toolkit_info = {
            "toolkit_name": toolkit_name,
            "tool_count": len(tools),
            "tools": []
        }
        
        for tool in tools:
            tool_info = {
                "name": getattr(tool, 'name', 'Unknown'),
                "description": getattr(tool, 'description', 'No description'),
                "type": type(tool).__name__,
            }
            
            # Try to get function signature if available
            if hasattr(tool, 'function'):
                func = tool.function
                tool_info["function_name"] = getattr(func, '__name__', 'Unknown')
                if hasattr(func, '__doc__'):
                    tool_info["function_doc"] = func.__doc__
            
            # Try to get tool schema/parameters if available
            if hasattr(tool, 'model_dump'):
                try:
                    schema = tool.model_dump()
                    if 'function' in schema and 'parameters' in schema['function']:
                        tool_info["parameters"] = schema['function']['parameters']
                except Exception as schema_error:
                    print(f"    Schema extraction error for {tool_info['name']}: {schema_error}")
            
            toolkit_info["tools"].append(tool_info)
        
        return toolkit_info
        
    except Exception as e:
        # More detailed error reporting
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "toolkit_name": toolkit_name
        }
        
        # Check for specific error types
        if "authorization" in str(e).lower():
            error_details["likely_cause"] = "Authorization required - user may need to authenticate"
        elif "connection" in str(e).lower() or "network" in str(e).lower():
            error_details["likely_cause"] = "Network connectivity issue"
        elif "api key" in str(e).lower():
            error_details["likely_cause"] = "Invalid or missing API key"
        else:
            error_details["likely_cause"] = "Unknown error"
        
        print(f"    Detailed error: {error_details}")
        logger.error(f"Error inspecting toolkit '{toolkit_name}': {e}")
        
        return {
            "toolkit_name": toolkit_name,
            "error": str(e),
            "error_details": error_details,
            "tool_count": 0,
            "tools": []
        }

async def inspect_multiple_toolkits(
    arcade_client: AsyncArcade, 
    toolkit_names: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Inspect multiple toolkits and return comprehensive tool information.
    
    Args:
        arcade_client: AsyncArcade client
        toolkit_names: List of toolkit names to inspect
        
    Returns:
        Dictionary mapping toolkit names to their tool information
    """
    results = {}
    
    for toolkit_name in toolkit_names:
        print(f"Inspecting {toolkit_name} toolkit...")
        results[toolkit_name] = await inspect_toolkit_tools(arcade_client, toolkit_name)
        
        # Print summary
        toolkit_info = results[toolkit_name]
        if 'error' in toolkit_info:
            print(f"  ❌ Error: {toolkit_info['error']}")
        else:
            print(f"  ✅ Found {toolkit_info['tool_count']} tools")
            for tool in toolkit_info['tools']:
                print(f"    - {tool['name']}: {tool.get('description', 'No description')}")
        print()
    
    return results

async def main():
    """Main function to run toolkit inspection."""
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    arcade_api_key = os.getenv("ARCADE_API_KEY")
    if not arcade_api_key:
        print("❌ ARCADE_API_KEY not found in environment variables")
        return
    
    # Initialize Arcade client with proper SSL configuration
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        custom_http_client = httpx.AsyncClient(verify=ssl_context, timeout=30.0)
        arcade_client = AsyncArcade(api_key=arcade_api_key, http_client=custom_http_client)
        print(f"✅ Arcade client initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Arcade client: {e}")
        return
    
    # Define toolkits to inspect based on the official documentation
    toolkits_to_inspect = [
        "google",    # Google Suite: Gmail, Calendar, Drive, Docs, Sheets, etc.
        "web",       # Web browsing and interaction
        "github",    # GitHub repositories, issues, pull requests
        "slack",     # Slack messaging 
        "linkedin",  # LinkedIn professional networking
        "notion",    # Notion pages and databases
        "stripe",    # Payment processing
        "x",         # X (Twitter) social media
        "reddit",    # Reddit interaction
        "hubspot",   # HubSpot CRM
        "salesforce", # Salesforce CRM
        "spotify",   # Spotify music control
        "discord",   # Discord servers and channels
        "zoom",      # Zoom meetings
        "dropbox",   # Dropbox file management
        "asana",     # Project management
        "twilio"     # SMS and WhatsApp messaging
    ]
    
    print("🔍 Inspecting Arcade Toolkits...\n")
    
    # Inspect all toolkits
    results = await inspect_multiple_toolkits(arcade_client, toolkits_to_inspect)
    
    # Print detailed summary
    print("\n" + "="*50)
    print("DETAILED TOOLKIT SUMMARY")
    print("="*50)
    
    for toolkit_name, info in results.items():
        if 'error' not in info:
            print(f"\n📦 {toolkit_name.upper()} TOOLKIT ({info['tool_count']} tools):")
            for tool in info['tools']:
                print(f"\n  🔧 {tool['name']}")
                print(f"     Description: {tool.get('description', 'No description')}")
                if 'parameters' in tool:
                    params = tool['parameters'].get('properties', {})
                    if params:
                        print(f"     Parameters: {', '.join(params.keys())}")
    
    # Close the client
    await arcade_client.close()

if __name__ == "__main__":
    asyncio.run(main()) 