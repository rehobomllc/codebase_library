#!/usr/bin/env python3
"""
Precision Scholarship Validation Agent
Uses OpenAI Web Search + Arcade Web Tools for accurate scholarship validation
"""

import logging
from agents import Agent, ModelSettings
from typing import Callable, Awaitable, List, Dict, Optional
import json
import re
from datetime import datetime

logger = logging.getLogger(__name__)

async def create_precision_validation_agent(arcade_client=None, get_tools_func=None):
    """Create a precision validation agent that properly handles AcademicWorks portals"""
    
    # Get both OpenAI Web Search and Arcade Web Tools
    all_tools = []
    
    if get_tools_func:
        try:
            # Get Arcade web tools (web scraper, Google search)
            arcade_tools = await get_tools_func(['web', 'google'])
            all_tools.extend(arcade_tools)
            logging.info(f"Loaded {len(arcade_tools)} Arcade tools for validation")
        except Exception as e:
            logging.warning(f"Could not load Arcade tools: {e}")
    
    # Add OpenAI Web Search tool
    try:
        from agents import WebSearchTool
        web_search_tool = WebSearchTool(search_context_size="high")
        all_tools.append(web_search_tool)
        logging.info("Added OpenAI WebSearchTool for validation")
    except Exception as e:
        logging.warning(f"Could not add OpenAI WebSearchTool: {e}")
    
    # Create the validation agent
    validation_agent = Agent(
        name="PrecisionValidationAgent",
        instructions="""You are a PRECISION SCHOLARSHIP VALIDATION AGENT specializing in detecting CLOSED or EXPIRED scholarships.

**CRITICAL MISSION**: Identify scholarships that are "CURRENTLY CLOSED", expired, or no longer accepting applications.

**SPECIAL HANDLING FOR ACADEMICWORKS PORTALS**:
When you encounter URLs containing "academicworks.com":
1. These are scholarship management portals that require authentication
2. Direct URL access often returns JSON data instead of scholarship details
3. Use web search to find current information about specific scholarships
4. Look for terms like "CURRENTLY CLOSED", "Application Closed", "Deadline Passed", etc.
5. Cross-reference with the institution's main scholarship pages

**VALIDATION PROCESS**:

1. **URL Analysis**: 
   - If URL contains "academicworks.com", use web search instead of direct scraping
   - Search for: "[scholarship name] [university] 2025 deadline status"
   - Look for official university scholarship pages with current information

2. **Status Detection Keywords** (HIGH PRIORITY):
   - "CURRENTLY CLOSED"
   - "Application Closed" 
   - "Deadline has passed"
   - "No longer accepting applications"
   - "Applications are closed"
   - "Closed for applications"
   - Past deadline dates (before current date)

3. **Validation Steps**:
   a) Use web search to find current scholarship information
   b) Check the institution's official scholarship pages
   c) Look for deadline dates and current status
   d) Verify if applications are still being accepted

4. **For Each Scholarship, Determine**:
   - Current Status: OPEN/CLOSED/UPCOMING
   - Application deadline (if available)
   - Real application URL (not just portal links)
   - Actual eligibility requirements
   - Award amounts and details

**OUTPUT REQUIREMENTS**:
Return ONLY valid JSON with this structure:
```json
{
  "validation_summary": {
    "total_candidates_processed": number,
    "validated_scholarships": number,
    "rejected_scholarships": number,
    "validation_timestamp": "ISO timestamp",
    "validation_method": "Web search + portal analysis"
  },
  "validated_scholarships": [
    {
      "title": "scholarship name",
      "organization": "organization name",
      "status": "OPEN",
      "application_deadline": "YYYY-MM-DD",
      "award_amount": "amount",
      "application_url": "real application URL",
      "information_url": "information URL",
      "eligibility_requirements": ["requirement1", "requirement2"],
      "essay_requirements": [
        {
          "prompt": "essay question",
          "word_limit": number,
          "required": true/false
        }
      ],
      "application_process": {
        "method": "application method",
        "required_documents": ["doc1", "doc2"],
        "submission_deadline": "deadline with time"
      },
      "validation_confidence": "HIGH/MEDIUM/LOW",
      "last_verified": "ISO timestamp",
      "scraped_status_text": "actual text found indicating status"
    }
  ],
  "rejected_scholarships": [
    {
      "title": "scholarship name",
      "organization": "organization name", 
      "rejection_reason": "CLOSED - specific reason",
      "original_url": "original URL",
      "status_found": "CLOSED/EXPIRED/UNCLEAR",
      "scraped_status_text": "text indicating closure",
      "notes": "additional context"
    }
  ]
}
```

**CRITICAL**: If you find ANY indication that a scholarship is closed, expired, or no longer accepting applications, it MUST go in the rejected_scholarships array with a clear rejection_reason.

**ACCURACY OVER SPEED**: Take time to thoroughly verify each scholarship's current status. False positives (showing closed scholarships as open) are worse than false negatives.""",
        tools=all_tools,
        model="gpt-4.1"
    )
    
    return validation_agent 