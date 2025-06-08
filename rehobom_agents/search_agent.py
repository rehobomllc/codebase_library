import logging
from agents import Agent, ModelSettings, WebSearchTool, function_tool, RunContextWrapper
from typing import Dict, Any, List
from datetime import datetime
import json
import sys
from pathlib import Path
from agents_arcade import get_arcade_tools

# Add the parent directory to Python path to import services
sys.path.append(str(Path(__file__).parent.parent))

from services.database import db_manager, search_master_scholarships, get_master_scholarships_stats

logger = logging.getLogger(__name__)

# Moved search_master_database to module level
@function_tool(
    description_override="Search curated database of 29,000+ scholarships with user-specific filtering",
    strict_mode=True
)
async def search_master_database(
    context: RunContextWrapper[Any], 
    user_profile_json: str, 
    limit: int = 50
) -> str:
    """Search curated database of 29,000+ scholarships with user-specific filtering
    
    Args:
        user_profile_json: JSON string containing user profile with academic_level, major, location, interests, etc.
        limit: Maximum number of scholarships to return (default: 50)
    """
    try:
        user_profile = json.loads(user_profile_json) if isinstance(user_profile_json, str) else user_profile_json
        
        pool = db_manager.get_pool()
        if not pool:
            return json.dumps({
                "status": "error", 
                "message": "Database not available",
                "scholarships": []
            })
        
        results = await search_master_scholarships(
            pool, 
            user_profile, 
            limit=limit, 
            current_only=True  # Only current scholarships
        )
        
        logger.info(f"Found {len(results)} scholarships from master database")
        
        return json.dumps({
            "status": "success",
            "scholarships_found": len(results),
            "scholarships": results,
            "source": "master_database",
            "search_params": {
                "academic_level": user_profile.get('academic_level'),
                "major": user_profile.get('major'),
                "location": user_profile.get('location'),
                "limit": limit
            }
        })
        
    except Exception as e:
        logger.error(f"Master database search error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Database search failed: {str(e)}",
            "scholarships": []
        })

def get_search_tools_func(arcade_client):
    async def inner(context):
        tools = [
            search_master_database,  # Now defined in module scope
        ]

        try:
            web_search_tool = WebSearchTool(search_context_size="high")
            tools.append(web_search_tool)
        except Exception as e:
            logger.warning(f"Could not add WebSearchTool: {e}")

        return tools
    return inner

async def create_search_agent(arcade_client=None, get_tools_func=None):
    """
    Enhanced search agent with master database integration (29k scholarships) 
    plus OpenAI's native web search capabilities.
    """
    
    # Get current date info for search targeting
    current_year = datetime.now().year
    next_year = current_year + 1
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Get database stats for context
    pool = db_manager.get_pool()
    db_stats = {}
    if pool:
        try:
            db_stats = await get_master_scholarships_stats(pool)
        except Exception as e:
            logger.warning(f"Could not get database stats: {e}")
            db_stats = {'total_scholarships': 'unknown', 'current_scholarships': 'unknown'}
    
    # search_master_database is now defined at the module level and will be picked up by get_search_tools_func

    # Create comprehensive instructions
    instructions = f"""
    You are an ADVANCED scholarship search agent with access to:
    
    🎯 PRIMARY SOURCE: Master Database ({db_stats.get('total_scholarships', '29,000+')} scholarships)
    📊 SUPPLEMENTARY: OpenAI native web search capabilities
    
    SEARCH STRATEGY (EXECUTE IN ORDER):
    1. **FIRST: Query Master Database** - Use search_master_database tool to find scholarships from our curated 29k database
    2. **THEN: Use Web Search** - Use the built-in web search to find newer opportunities not in our database
    3. **COMBINE & DEDUPLICATE** - Merge results, prioritizing database matches and removing duplicates
    
    📅 CRITICAL DATE FILTERING:
    - Current date: {current_date}
    - ONLY include scholarships with deadlines on or after {current_date}
    - Prioritize scholarships with deadlines in {current_year} and {next_year}
    - Reject any expired opportunities
    
    💡 AVAILABLE TOOLS:
    - search_master_database: Search our curated database of 29k+ scholarships
    - Web search (built-in): Find additional opportunities via OpenAI's web search
    
    📋 SEARCH PROCESS:
    1. Parse user profile to extract: major, academic level, location, interests, GPA
    2. Execute search_master_database with user profile JSON
    3. If database results < 20, supplement with web search for queries like:
       - "[major] scholarships [academic_level] [current_year]"
       - "[location] student scholarships deadline [current_year]"
       - "[interests] scholarship opportunities {next_year}"
    4. Format results with clear source attribution
    5. Provide relevance scores and match explanations
    
    📊 OUTPUT FORMAT:
    CRITICAL: Return ONLY a valid JSON object with this EXACT structure:
    
    {{
        "scholarship_candidates": [
            {{
                "title": "Scholarship Name",
                "description": "Brief description", 
                "url": "https://scholarship-url.com",
                "deadline": "2025-MM-DD",
                "amount": "$X,XXX",
                "eligibility": "Brief eligibility summary",
                "source": "master_database" or "web_search",
                "discovery_method": "database_query" or "web_search",
                "relevance_score": 0.95,
                "match_reasons": ["reason1", "reason2"],
                "relevance_tags": [{{"type": "academic_level", "value": "Undergraduate", "icon": "🎓"}}]
            }}
        ],
        "search_summary": {{
            "total_found": 15,
            "database_scholarships": 12,
            "web_scholarships": 3,
            "search_strategy": "Brief explanation of approach used"
        }},
        "metadata": {{
            "search_date": "{current_date}",
            "user_profile_matched": {{"academic_level": "...", "location": "...", "major": "..."}},
            "database_stats": {{"queried": true, "results": 12}},
            "web_search_stats": {{"performed": true, "results": 3}}
        }}
    }}
    
    CRITICAL REQUIREMENTS:
    - Return ONLY valid JSON - no other text before or after
    - scholarship_candidates array MUST contain actual scholarship objects
    - Each scholarship MUST have: title, description, url, deadline, amount, eligibility
    - ALL deadlines must be {current_date} or later (no expired scholarships)
    - If no results found, return {{"scholarship_candidates": [], "search_summary": {{"total_found": 0, "message": "No qualifying scholarships found"}}}}
    
    🎯 SUCCESS METRICS:
    - Prioritize current scholarships (deadline >= {current_date})
    - Focus on user's academic level and major
    - Include geographic matches when specified
    - Maintain high data quality standards
    
    Database Statistics:
    - Total scholarships: {db_stats.get('total_scholarships', 'Loading...')}
    - Current (not expired): {db_stats.get('current_scholarships', 'Loading...')}
    - Average amount: ${db_stats.get('average_amount', 0):,.0f}
    """
    
    # Use new get_search_tools_func to obtain tools
    tools = await get_search_tools_func(arcade_client)(context={})

    # Create and return the enhanced agent following SDK pattern
    agent = Agent(
        name="EnhancedScholarshipSearchAgent",
        instructions=instructions,
        model="gpt-4.1",  # Use latest model for best performance
        tools=tools,  # Use tools parameter instead of get_tools_func
        model_settings=ModelSettings(
            temperature=0.1,  # Lower temperature for more deterministic results
            max_tokens=4000
        )
    )

    logger.info(f"Enhanced search agent created with {len(tools)} tools (master database + OpenAI web search)")
    return agent

# Legacy function for backward compatibility
async def create_scholarship_search_agent_with_enhanced_targeting(arcade_client=None, get_tools_func=None):
    """Legacy wrapper for enhanced search agent"""
    return await create_search_agent(arcade_client, get_tools_func)