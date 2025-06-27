#!/usr/bin/env python3
"""
View all tools available in Arcade toolkits
"""

import subprocess
import json
import os
from dotenv import load_dotenv

def get_tools_for_toolkit(toolkit_name):
    """Get all tools for a specific toolkit using curl"""
    load_dotenv()
    api_key = os.getenv("ARCADE_API_KEY")
    
    if not api_key:
        print("❌ ARCADE_API_KEY not found")
        return []
    
    # Curl command to get all tools
    cmd = [
        "curl", "-s", "-H", f"Authorization: Bearer {api_key}",
        "https://api.arcade-ai.com/v1/tools?limit=250"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error running curl: {result.stderr}")
            return []
        
        data = json.loads(result.stdout)
        toolkit_tools = []
        
        for tool in data.get("items", []):
            if tool["fully_qualified_name"].startswith(f"{toolkit_name}."):
                toolkit_tools.append({
                    "name": tool["name"],
                    "qualified_name": tool["qualified_name"],
                    "description": tool["description"][:100] + "..." if len(tool["description"]) > 100 else tool["description"],
                    "requirements_met": tool["requirements"]["met"]
                })
        
        return toolkit_tools
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def main():
    print("🔧 Available Arcade Toolkit Tools\n")
    
    # Google Toolkit
    print("📧 Google Toolkit:")
    google_tools = get_tools_for_toolkit("Google")
    if google_tools:
        for i, tool in enumerate(google_tools[:10], 1):  # Show first 10
            status = "✅" if tool["requirements_met"] else "⚠️"
            print(f"  {i:2}. {status} {tool['name']}")
            print(f"      {tool['description']}")
        if len(google_tools) > 10:
            print(f"      ... and {len(google_tools) - 10} more tools")
        print(f"\nTotal Google tools: {len(google_tools)}")
    else:
        print("  No Google tools found")
    
    print("\n" + "="*50 + "\n")
    
    # Web Toolkit  
    print("🌐 Web Toolkit:")
    web_tools = get_tools_for_toolkit("Web")
    if web_tools:
        for i, tool in enumerate(web_tools, 1):
            status = "✅" if tool["requirements_met"] else "⚠️"
            print(f"  {i:2}. {status} {tool['name']}")
            print(f"      {tool['description']}")
        print(f"\nTotal Web tools: {len(web_tools)}")
    else:
        print("  No Web tools found")
    
    print("\n" + "="*50 + "\n")
    
    # Other popular toolkits
    other_toolkits = ["Search", "Slack", "Asana", "NotionToolkit", "Microsoft"]
    for toolkit in other_toolkits:
        tools = get_tools_for_toolkit(toolkit)
        if tools:
            print(f"🔧 {toolkit} Toolkit: {len(tools)} tools available")

if __name__ == "__main__":
    main() 