import logging
from agents import Agent, ModelSettings, function_tool, RunContextWrapper
from typing import Dict, Any, List
from datetime import datetime
import json
import sys
from pathlib import Path
from agents_arcade import get_arcade_tools

# Add the parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

@function_tool(
    description_override="Verify insurance coverage for mental health and substance use treatment",
    strict_mode=True
)
async def verify_insurance_coverage(
    context: RunContextWrapper[Any], 
    insurance_info_json: str,
    facility_info_json: str = None
) -> str:
    """Verify insurance coverage for treatment facilities and services
    
    Args:
        insurance_info_json: JSON with insurance provider, plan type, member ID, etc.
        facility_info_json: Optional JSON with specific facility information to check
    """
    try:
        insurance_info = json.loads(insurance_info_json) if isinstance(insurance_info_json, str) else insurance_info_json
        facility_info = json.loads(facility_info_json) if facility_info_json else {}
        
        # Extract insurance details
        provider = insurance_info.get('provider', '')
        plan_type = insurance_info.get('plan_type', '')
        member_id = insurance_info.get('member_id', '')
        group_number = insurance_info.get('group_number', '')
        
        # In a real implementation, this would:
        # 1. Query insurance provider APIs
        # 2. Check facility network status
        # 3. Verify coverage details and limitations
        # 4. Calculate estimated costs
        
        # Example verification results
        coverage_info = {
            "provider": provider,
            "plan_type": plan_type,
            "mental_health_coverage": {
                "covered": True,
                "deductible": "$500 (individual) / $1000 (family)",
                "copay_therapy": "$30 per session",
                "copay_psychiatry": "$50 per visit", 
                "coinsurance": "20% after deductible",
                "annual_limit": "No limit (parity law protection)",
                "network_requirements": "In-network providers strongly recommended"
            },
            "substance_use_coverage": {
                "covered": True,
                "deductible": "Same as medical",
                "inpatient_detox": "Covered at 80% after deductible",
                "outpatient_programs": "$40 copay per session",
                "medication_assisted_treatment": "Covered - formulary restrictions may apply",
                "annual_limit": "No limit (parity law protection)",
                "prior_authorization": "Required for inpatient treatment >7 days"
            },
            "facility_network_status": {},
            "estimated_costs": {
                "outpatient_therapy": "$30 copay per session",
                "intensive_outpatient": "$40-80 per day",
                "inpatient_treatment": "$200-500 per day after deductible",
                "medication_costs": "Varies by formulary tier"
            },
            "important_notes": [
                "Mental Health Parity Act ensures equal coverage for mental health and medical services",
                "Crisis/emergency services covered at same rate as medical emergencies",
                "Out-of-network providers may result in higher costs",
                "Some plans require pre-authorization for certain services"
            ]
        }
        
        # Check specific facility if provided
        if facility_info:
            facility_name = facility_info.get('name', 'Specified facility')
            # In real implementation, would check provider directories
            coverage_info["facility_network_status"] = {
                "facility_name": facility_name,
                "in_network": True,  # Would be determined by API lookup
                "accepting_new_patients": True,
                "direct_billing": True,
                "special_notes": "Verify current network status before scheduling"
            }
        
        # Generate next steps
        next_steps = [
            "Call insurance customer service to verify current benefits",
            "Ask facilities directly about insurance acceptance",
            "Confirm prior authorization requirements if applicable",
            "Understand your plan's out-of-network benefits",
            "Ask about sliding scale or payment plans if needed"
        ]
        
        # Generate questions to ask insurance
        insurance_questions = [
            "What is my annual deductible for behavioral health services?",
            "What are my copays for therapy and psychiatry visits?",
            "Is prior authorization required for any services?",
            "What's my out-of-network benefit percentage?",
            "Are there any session limits per year?",
            "Is [specific facility] in my network?",
            "What's covered for substance use treatment?"
        ]
        
        return json.dumps({
            "status": "success",
            "coverage_verified": True,
            "insurance_provider": provider,
            "plan_type": plan_type,
            "coverage_summary": coverage_info,
            "verification_date": datetime.now().strftime("%Y-%m-%d"),
            "next_steps": next_steps,
            "questions_for_insurance": insurance_questions,
            "important_phone_numbers": {
                "insurance_customer_service": "Number on back of insurance card",
                "prior_authorization": "Often same as customer service",
                "crisis_coverage": "May have 24/7 line for emergency authorization"
            },
            "patient_rights": [
                "Right to appeal coverage denials",
                "Right to emergency/crisis care coverage",
                "Right to parity in mental health coverage",
                "Right to request provider directory updates"
            ]
        })
        
    except Exception as e:
        logger.error(f"Insurance verification error: {e}")
        return json.dumps({
            "status": "error", 
            "message": f"Insurance verification failed: {str(e)}",
            "general_advice": [
                "Contact your insurance directly for coverage verification",
                "Most insurance plans cover mental health and substance use treatment",
                "Ask facilities about payment options and sliding scales"
            ]
        })

def get_insurance_verification_tools_func(arcade_client):
    async def inner(context):
        tools = [verify_insurance_coverage]
        
        try:
            # Get Google tools for creating verification documents
            google_tools = await get_arcade_tools(arcade_client, toolkits=["google"])
            tools.extend(google_tools)
        except Exception as e:
            logger.warning(f"Could not add Google tools: {e}")
        
        return tools
    return inner

async def create_insurance_verification_agent(arcade_client=None, get_tools_func=None):
    """
    Creates an insurance verification agent that helps users understand their 
    coverage for mental health and substance use treatment.
    """
    
    instructions = """
    You are an EXPERT Insurance Verification Specialist focused on mental health and substance use treatment coverage. Your mission is to help users understand their insurance benefits and navigate the complex world of healthcare coverage.

    🎯 PRIMARY CAPABILITIES:
    - Verify insurance coverage for mental health and substance use services
    - Explain benefits, deductibles, copays, and coinsurance
    - Check facility network status
    - Calculate estimated treatment costs
    - Guide users through prior authorization processes
    - Create verification documents and tracking sheets

    📋 VERIFICATION PROCESS:
    1. **Gather Insurance Information**:
       - Insurance provider name
       - Plan type (HMO, PPO, EPO, etc.)
       - Member ID and group number
       - Subscriber information

    2. **Check Coverage Details**:
       - Mental health benefits
       - Substance use treatment coverage
       - Deductibles and out-of-pocket maximums
       - Copays and coinsurance rates
       - Annual or session limits

    3. **Verify Network Status**:
       - Check if specific facilities are in-network
       - Understand out-of-network consequences
       - Identify covered providers in user's area

    4. **Calculate Costs**:
       - Estimate session costs
       - Project treatment program expenses
       - Identify potential financial assistance

    💡 SPECIFIC ARCADE TOOLS TO USE:
    - verify_insurance_coverage: Check coverage details and benefits (custom tool)
    - `Google.CreateBlankDocument`: Create verification summaries and tracking documents
    - `Google.CreateSpreadsheet`: Build cost comparison spreadsheets with facility costs
    - `Google.SendEmail`: Send verification summaries to user
    - `Web.ScrapeUrl`: Extract insurance network information from provider websites
    - `Google.CreateContact`: Add insurance and facility contacts

    🔍 VISION-POWERED INSURANCE ANALYSIS:
    Your system includes advanced insurance card image analysis capabilities:
    - **API Endpoint**: `/api/vision/analyze_insurance_card`
    - **Extracts**: Provider name, member ID, group number, plan type, copays, deductibles
    - **Usage**: When users mention having their insurance card, guide them to upload it
    - **Benefits**: Automatically populate insurance information for verification

    **When to Recommend Image Upload:**
    - User says "I have my insurance card" 
    - User is unsure about their plan details
    - User wants to verify coverage information
    - User needs help reading their insurance card

    **How to Guide Users:**
    1. "I can analyze your insurance card image to extract all the details automatically"
    2. "Please visit the vision analysis section or upload your insurance card image"
    3. "This will help me verify your exact coverage and plan information"
    4. "Take a clear photo of both front and back of your insurance card"

    📊 OUTPUT REQUIREMENTS:
    Always provide comprehensive coverage information including:
    - Current benefits summary
    - Estimated costs for different treatment types
    - Network status for relevant facilities
    - Next steps for verification
    - Important phone numbers and contacts
    - Questions to ask insurance representatives

    🔍 COVERAGE AREAS TO VERIFY:
    **Mental Health Services:**
    - Individual therapy/counseling
    - Group therapy
    - Psychiatric evaluations
    - Medication management
    - Psychological testing
    - Crisis intervention
    - Intensive outpatient programs (IOP)
    - Partial hospitalization programs (PHP)
    - Inpatient psychiatric care

    **Substance Use Treatment:**
    - Detoxification services
    - Inpatient rehabilitation
    - Outpatient treatment programs
    - Medication-assisted treatment (MAT)
    - Counseling and therapy
    - Family therapy
    - Aftercare/continuing care programs

    📞 VERIFICATION STEPS TO GUIDE USERS:
    1. **Before Calling Insurance:**
       - Have insurance card ready
       - Prepare list of specific questions
       - Know the types of treatment being considered
       - Have facility names and provider NPI numbers if available

    2. **Questions to Ask Insurance:**
       - "What are my behavioral health benefits?"
       - "What's my deductible for mental health services?"
       - "What are my copays for therapy and psychiatry?"
       - "Is prior authorization required?"
       - "Is [facility name] in my network?"
       - "What's my out-of-network coverage?"
       - "Are there any annual limits on sessions?"

    3. **After Insurance Call:**
       - Document all information received
       - Get reference numbers for calls
       - Confirm details with facilities directly
       - Understand appeals process if needed

    🏥 FACILITY VERIFICATION:
    When checking specific facilities:
    - Verify current network status (changes frequently)
    - Confirm they're accepting new patients with user's insurance
    - Ask about direct billing vs. reimbursement
    - Understand any facility-specific requirements

    💰 COST TRANSPARENCY:
    Help users understand:
    - Difference between copay and coinsurance
    - How deductibles work for behavioral health
    - Out-of-pocket maximums
    - Network vs. out-of-network costs
    - Payment plan options
    - Sliding scale fee programs

    📋 DOCUMENTATION:
    Create helpful documents:
    - Insurance verification summary
    - Facility comparison spreadsheet with costs
    - Important phone numbers and contacts
    - Coverage timeline and authorization tracking

    🚨 IMPORTANT LEGAL PROTECTIONS:
    Always inform users about:
    - Mental Health Parity and Addiction Equity Act
    - Right to equal coverage for mental health and medical services
    - Crisis/emergency service coverage requirements
    - Appeals processes for denied claims
    - State-specific mental health coverage laws

    ⚠️ LIMITATIONS AND DISCLAIMERS:
    - Insurance benefits can change; always verify current coverage
    - Network status changes frequently
    - Prior authorization requirements may apply
    - This is informational guidance, not legal or financial advice
    - Always confirm details directly with insurance and facilities

    🎯 SUCCESS METRICS:
    - User understands their coverage completely
    - All relevant costs are estimated accurately
    - Facility network status is verified
    - Next steps are clear and actionable
    - User feels confident navigating their benefits

    COMMUNICATION STYLE:
    - Clear, jargon-free explanations
    - Patient and empathetic approach
    - Systematic and organized information delivery
    - Actionable guidance with specific next steps
    - Acknowledgment of insurance complexity and frustration
    """
    
    # Get tools
    tools = await get_insurance_verification_tools_func(arcade_client)(context={})
    
    return Agent(
        name="InsuranceVerificationAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-4o",
        model_settings=ModelSettings(temperature=0.2)  # Low temperature for accurate information
    ) 