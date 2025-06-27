#!/usr/bin/env python3
"""
Debug connection issues with Arcade API
"""

import asyncio
import os
from dotenv import load_dotenv

async def main():
    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv("ARCADE_API_KEY")
    print(f"API Key present: {bool(api_key)}")
    print(f"API Key length: {len(api_key) if api_key else 0}")
    
    try:
        print("1. Testing basic import...")
        from arcadepy import AsyncArcade
        print("   ✅ Import successful")
        
        print("2. Creating client...")
        client = AsyncArcade()
        print("   ✅ Client created")
        
        print("3. Testing agents-arcade import...")
        from agents_arcade import get_arcade_tools
        print("   ✅ agents-arcade import successful")
        
        print("4. Testing simple API call...")
        # Let's try a simple call to see what happens
        tools = await get_arcade_tools(client, toolkits=["google"])
        print(f"   ✅ Success! Got {len(tools)} tools")
        
        await client.close()
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        print(f"   Error type: {type(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(main()) 