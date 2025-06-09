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

logger = logging.getLogger(__name__)

@function_tool(
    description_override="Search for mental health and substance use treatment facilities with user-specific filtering",
    strict_mode=True
)
async def search_treatment_facilities(
    context: RunContextWrapper[Any], 
    user_profile_json: str, 
    facility_type: str = "all",
    limit: int = 25
) -> str:
    """Search for mental health and substance use treatment facilities
    
    Args:
        user_profile_json: JSON string containing user profile with location, insurance, treatment_type, etc.
        facility_type: Type of facility (mental_health, substance_use, dual_diagnosis, all)
        limit: Maximum number of facilities to return (default: 25)
    """
    try:
        user_profile = json.loads(user_profile_json) if isinstance(user_profile_json, str) else user_profile_json
        
        # Extract key search parameters
        location = user_profile.get('location', '')
        treatment_type = user_profile.get('treatment_type', 'all')
        insurance = user_profile.get('insurance', '')
        urgency = user_profile.get('urgency', 'routine')
        setting_preference = user_profile.get('setting_preference', 'outpatient')
        special_requirements = user_profile.get('special_requirements', [])
        
        # Build search results (this would integrate with real treatment facility databases)
        # For now, returning structured example data that shows the expected format
        facilities = []
        
        # This is where you would integrate with:
        # - SAMHSA Treatment Locator API
        # - Psychology Today directory
        # - Insurance provider directories
        # - State mental health facility databases
        
        logger.info(f"Searching for {facility_type} facilities in {location} for {treatment_type} treatment")
        
        # Example facilities structure
        example_facilities = [
            {
                "name": f"Community Mental Health Center - {location}",
                "address": f"123 Main St, {location}",
                "phone": "(555) 123-4567",
                "website": "https://example-mhc.org",
                "facility_type": "mental_health",
                "services": ["Individual Therapy", "Group Therapy", "Psychiatric Services", "Crisis Intervention"],
                "insurance_accepted": ["Medicaid", "Medicare", "Blue Cross Blue Shield", "Aetna"],
                "specialties": ["Depression", "Anxiety", "PTSD", "Bipolar Disorder"],
                "setting": "outpatient",
                "accepts_new_patients": True,
                "wait_time": "1-2 weeks",
                "accessibility": ["Wheelchair accessible", "Spanish-speaking staff"],
                "rating": 4.2,
                "distance_miles": 2.5,
                "match_score": 0.95
            },
            {
                "name": f"Recovery Center - {location}",
                "address": f"456 Recovery Rd, {location}",
                "phone": "(555) 987-6543",
                "website": "https://example-recovery.org",
                "facility_type": "substance_use",
                "services": ["Detox", "Inpatient Treatment", "Outpatient Programs", "MAT", "Counseling"],
                "insurance_accepted": ["Most major insurance", "Self-pay", "Sliding scale"],
                "specialties": ["Alcohol Use Disorder", "Opioid Use Disorder", "Dual Diagnosis"],
                "setting": "both",
                "accepts_new_patients": True,
                "wait_time": "Same day for crisis",
                "accessibility": ["24/7 crisis line", "Multiple languages"],
                "rating": 4.7,
                "distance_miles": 5.1,
                "match_score": 0.88
            }
        ]
        
        # Filter and rank based on user preferences
        for facility in example_facilities:
            if facility_type != "all" and facility["facility_type"] != facility_type:
                continue
            if insurance and insurance.lower() not in [ins.lower() for ins in facility["insurance_accepted"]]:
                facility["insurance_note"] = f"May not accept {insurance} - verify coverage"
            facilities.append(facility)
        
        return json.dumps({
            "status": "success",
            "facilities_found": len(facilities),
            "facilities": facilities[:limit],
            "search_parameters": {
                "location": location,
                "treatment_type": treatment_type,
                "facility_type": facility_type,
                "insurance": insurance,
                "urgency": urgency,
                "setting_preference": setting_preference
            },
            "search_tips": [
                "Contact facilities directly to verify insurance coverage",
                "Ask about sliding scale fees if cost is a concern", 
                "Inquire about wait times for your urgency level",
                "Confirm they treat your specific condition"
            ]
        })
        
    except Exception as e:
        logger.error(f"Treatment facility search error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Facility search failed: {str(e)}",
            "facilities": []
        })

def get_facility_search_tools_func(arcade_client):
    async def inner(context):
        tools = [
            search_treatment_facilities,
        ]

        try:
            web_search_tool = WebSearchTool(search_context_size="high")
            tools.append(web_search_tool)
        except Exception as e:
            logger.warning(f"Could not add WebSearchTool: {e}")

        return tools
    return inner

async def create_facility_search_agent(arcade_client=None, get_tools_func=None):
    """
    Creates a comprehensive treatment facility search agent that finds mental health
    and substance use treatment facilities based on user needs and preferences.
    """
    
    # Get current date info for search targeting
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Create comprehensive instructions
    instructions = f"""
    You are an EXPERT Treatment Facility Search Agent specializing in finding mental health and substance use treatment facilities. Your mission is to help people find appropriate, accessible, and high-quality treatment options.

    🎯 PRIMARY CAPABILITIES:
    - Search comprehensive treatment facility databases
    - Filter by insurance, location, treatment type, and specialties
    - Verify facility availability and wait times
    - Match users with appropriate level of care
    - Provide accessibility and language preference matching

    📊 SEARCH STRATEGY (EXECUTE IN ORDER):
    1. **Parse User Requirements** - Extract location, insurance, treatment type, urgency, and preferences
    2. **Database Search** - Use search_treatment_facilities tool with user profile
    3. **Web Search Supplement** - Use web search for additional recent facilities/programs
    4. **Verification** - Cross-reference facility information for accuracy
    5. **Ranking** - Score facilities based on user fit and quality metrics

    🏥 FACILITY TYPES TO SEARCH:
    - **Mental Health**: Therapists, psychiatrists, counseling centers, psychiatric hospitals
    - **Substance Use**: Detox centers, rehab facilities, outpatient programs, MAT providers
    - **Dual Diagnosis**: Facilities treating both mental health and substance use
    - **Specialized**: LGBTQ+ friendly, trauma-informed, culturally specific

    💡 AVAILABLE TOOLS:
    - search_treatment_facilities: Search treatment facility database
    - Web search (built-in): Find additional facilities and verify information

    📋 SEARCH PROCESS:
    1. Extract user profile including:
       - Location (city, state, ZIP)
       - Insurance provider and plan type
       - Treatment type needed (mental health, substance use, both)
       - Urgency level (crisis, urgent, routine)
       - Setting preference (inpatient, outpatient, partial hospitalization)
       - Special requirements (language, accessibility, LGBTQ+ affirming, etc.)
    2. Execute facility search with user profile
    3. Supplement with web search for:
       - "[location] mental health treatment centers"
       - "[location] substance abuse treatment"
       - "[insurance] covered treatment facilities [location]"
       - "best rated [treatment type] facilities [location]"
    4. Verify facility information (hours, services, insurance)
    5. Rank results by match score and quality

    📊 OUTPUT FORMAT:
    CRITICAL: Return ONLY a valid JSON object with this EXACT structure:
    
    {{
        "treatment_facilities": [
            {{
                "name": "Facility Name",
                "address": "Full address",
                "phone": "(xxx) xxx-xxxx",
                "website": "https://facility-website.com",
                "facility_type": "mental_health|substance_use|dual_diagnosis",
                "services": ["Service1", "Service2"],
                "insurance_accepted": ["Insurance1", "Insurance2"],
                "specialties": ["Specialty1", "Specialty2"],
                "setting": "inpatient|outpatient|both",
                "accepts_new_patients": true,
                "wait_time": "Time estimate",
                "accessibility": ["Feature1", "Feature2"],
                "rating": 4.5,
                "distance_miles": 2.3,
                "match_score": 0.92,
                "insurance_verified": true,
                "emergency_services": true,
                "languages": ["English", "Spanish"],
                "notes": "Additional important information"
            }}
        ],
        "search_summary": {{
            "total_found": 15,
            "mental_health_facilities": 8,
            "substance_use_facilities": 5,
            "dual_diagnosis_facilities": 2,
            "crisis_resources": 3,
            "insurance_compatible": 12
        }},
        "crisis_resources": [
            {{
                "name": "Crisis Service Name",
                "phone": "Crisis phone number",
                "availability": "24/7",
                "type": "hotline|mobile crisis|emergency room"
            }}
        ],
        "next_steps": [
            "Contact top-rated facilities to verify availability",
            "Confirm insurance coverage details",
            "Ask about specific treatment approaches",
            "Inquire about wait times for your urgency level"
        ],
        "metadata": {{
            "search_date": "{current_date}",
            "user_location": "...",
            "search_radius_miles": 25,
            "insurance_provider": "...",
            "treatment_focus": "..."
        }}
    }}
    
    🚨 CRISIS HANDLING:
    If urgency is "crisis" or "immediate", prioritize:
    - Facilities with crisis intervention services
    - Emergency departments with psychiatric services
    - Crisis stabilization units
    - Mobile crisis teams
    - Include crisis hotlines: 988 Suicide & Crisis Lifeline, local crisis lines

    ✅ QUALITY INDICATORS TO HIGHLIGHT:
    - Joint Commission accreditation
    - CARF (Commission on Accreditation of Rehabilitation Facilities) accreditation
    - State licensing and certifications
    - Evidence-based treatment approaches
    - Cultural competency programs
    - Trauma-informed care
    - Staff credentials and experience

    CRITICAL REQUIREMENTS:
    - Return ONLY valid JSON - no other text before or after
    - All facilities MUST have current contact information
    - Verify insurance acceptance when possible
    - Include crisis resources for urgent cases
    - Respect privacy and maintain confidentiality
    - Never provide medical advice or treatment recommendations
    - Focus on navigation and connection to professional services
    """
    
    # Use facility search tools
    tools = await get_facility_search_tools_func(arcade_client)(context={})

    # Create and return the agent
    agent = Agent(
        name="TreatmentFacilitySearchAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0.3)  # Lower temperature for factual searches
    )
    
    return agent 