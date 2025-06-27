#!/usr/bin/env python3
"""
Simple test following the exact arcade_doc.txt examples
"""

import asyncio
import os
from dotenv import load_dotenv
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools
from agents_arcade.errors import AuthorizationError

async def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize the Arcade client (following the doc exactly)
    client = AsyncArcade()
    
    print("Testing simple toolkit loading...")
    
    try:
        # Test 1: Single toolkit (from doc example)
        print("1. Testing 'google' toolkit...")
        tools = await get_arcade_tools(client, toolkits=["google"])
        print(f"   ✅ Success! Got {len(tools)} tools")
        for tool in tools[:3]:  # Show first 3 tools
            print(f"     - {getattr(tool, 'name', 'Unknown')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    try:
        # Test 2: Multiple toolkits (from doc example)
        print("2. Testing multiple toolkits...")
        tools = await get_arcade_tools(client, toolkits=["google", "github", "linkedin"])
        print(f"   ✅ Success! Got {len(tools)} tools")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    try:
        # Test 3: GitHub only (from doc example)
        print("3. Testing 'github' toolkit...")
        tools = await get_arcade_tools(client, toolkits=["github"])
        print(f"   ✅ Success! Got {len(tools)} tools")
        for tool in tools[:3]:  # Show first 3 tools
            print(f"     - {getattr(tool, 'name', 'Unknown')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Close the client
    await client.close()

if __name__ == "__main__":
    asyncio.run(main()) 