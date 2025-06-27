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
    description_override="Assist with filling out treatment intake forms and create documentation",
    strict_mode=True
)
async def fill_intake_form(
    context: RunContextWrapper[Any], 
    form_info_json: str,
    user_profile_json: str
) -> str:
    """Assist with filling out treatment intake forms
    
    Args:
        form_info_json: JSON with form type, facility, sections to complete
        user_profile_json: JSON with user information for form completion
    """
    try:
        form_info = json.loads(form_info_json) if isinstance(form_info_json, str) else form_info_json
        user_profile = json.loads(user_profile_json) if isinstance(user_profile_json, str) else user_profile_json
        
        # Extract form and user details
        form_type = form_info.get('form_type', 'general_intake')
        facility_name = form_info.get('facility_name', '')
        sections_needed = form_info.get('sections', [])
        
        # Extract user information
        name = user_profile.get('name', '')
        dob = user_profile.get('date_of_birth', '')
        phone = user_profile.get('phone', '')
        email = user_profile.get('email', '')
        address = user_profile.get('address', '')
        insurance = user_profile.get('insurance', {})
        emergency_contact = user_profile.get('emergency_contact', {})
        
        # Generate comprehensive intake form assistance
        intake_sections = {
            "personal_information": {
                "section_name": "Personal Information",
                "fields": {
                    "full_name": name,
                    "date_of_birth": dob,
                    "phone_number": phone,
                    "email_address": email,
                    "home_address": address,
                    "preferred_contact_method": "phone",
                    "preferred_language": "English"
                },
                "status": "ready_to_complete"
            },
            "insurance_information": {
                "section_name": "Insurance & Payment",
                "fields": {
                    "primary_insurance": insurance.get('provider', ''),
                    "policy_number": insurance.get('member_id', ''),
                    "group_number": insurance.get('group_number', ''),
                    "subscriber_name": name,
                    "subscriber_relationship": "self",
                    "secondary_insurance": insurance.get('secondary', 'None')
                },
                "status": "ready_to_complete"
            },
            "emergency_contact": {
                "section_name": "Emergency Contact Information",
                "fields": {
                    "contact_name": emergency_contact.get('name', ''),
                    "relationship": emergency_contact.get('relationship', ''),
                    "phone_number": emergency_contact.get('phone', ''),
                    "alternative_contact": emergency_contact.get('alternative', '')
                },
                "status": "needs_input" if not emergency_contact.get('name') else "ready_to_complete"
            },
            "medical_history": {
                "section_name": "Medical & Mental Health History",
                "fields": {
                    "current_medications": "List all current medications and dosages",
                    "allergies": "List any drug allergies or adverse reactions", 
                    "previous_mental_health_treatment": "Describe any previous therapy or psychiatric treatment",
                    "previous_substance_use_treatment": "Describe any previous addiction treatment",
                    "family_mental_health_history": "Family history of mental health or substance use issues",
                    "current_symptoms": "Describe current symptoms or concerns"
                },
                "status": "requires_detailed_input",
                "guidance": "This section requires detailed, thoughtful responses about your health history"
            },
            "substance_use_assessment": {
                "section_name": "Substance Use Assessment",
                "fields": {
                    "substances_used": "List substances used (alcohol, drugs, etc.)",
                    "frequency_of_use": "How often do you use substances?",
                    "last_use": "When did you last use substances?",
                    "longest_sobriety": "What's the longest period of sobriety you've had?",
                    "withdrawal_symptoms": "Have you experienced withdrawal symptoms?",
                    "impact_on_life": "How has substance use affected your life?"
                },
                "status": "conditional",
                "note": "Complete only if seeking substance use treatment"
            },
            "mental_health_assessment": {
                "section_name": "Mental Health Assessment",
                "fields": {
                    "current_mood": "Describe your current mood and emotions",
                    "anxiety_levels": "Rate your anxiety level (1-10) and describe triggers",
                    "sleep_patterns": "Describe your sleep quality and patterns",
                    "appetite_changes": "Any changes in appetite or eating habits?",
                    "concentration": "Any difficulties with focus or concentration?",
                    "suicidal_thoughts": "Have you had thoughts of self-harm? (Crisis resources available)"
                },
                "status": "requires_careful_consideration",
                "guidance": "Answer honestly - this helps providers give you the best care"
            },
            "treatment_goals": {
                "section_name": "Treatment Goals & Preferences",
                "fields": {
                    "primary_goals": "What are your main goals for treatment?",
                    "treatment_preferences": "Do you prefer individual or group therapy?",
                    "previous_helpful_treatments": "What treatments have been helpful before?",
                    "concerns_about_treatment": "Any worries or concerns about starting treatment?",
                    "support_system": "Describe your support system (family, friends, etc.)",
                    "barriers_to_treatment": "What might make it difficult to attend treatment?"
                },
                "status": "requires_thoughtful_input"
            }
        }
        
        # Create form completion guide
        completion_guide = {
            "preparation_tips": [
                "Set aside 30-45 minutes to complete thoroughly",
                "Gather insurance cards and medication lists",
                "Have emergency contact information ready",
                "Consider previous treatment experiences",
                "Be honest - providers need accurate information"
            ],
            "difficult_sections": [
                "Medical history may require consulting previous records",
                "Substance use questions should be answered honestly",
                "Mental health symptoms - describe current feelings",
                "Family history - gather information if needed"
            ],
            "privacy_reminders": [
                "All information is confidential and protected by HIPAA",
                "Information is only shared with your treatment team",
                "You can ask questions about any section",
                "Crisis resources are available if you need support"
            ]
        }
        
        # Generate next steps
        next_steps = [
            "Review each section carefully before starting",
            "Complete demographic sections first (easiest)",
            "Take breaks if needed during emotional sections",
            "Save progress frequently if completing online",
            "Contact facility with questions about specific fields",
            "Bring completed forms 15 minutes before appointment"
        ]
        
        return json.dumps({
            "status": "success",
            "form_type": form_type,
            "facility": facility_name,
            "intake_sections": intake_sections,
            "completion_guide": completion_guide,
            "next_steps": next_steps,
            "estimated_time": "30-45 minutes",
            "crisis_resources": {
                "suicide_prevention_lifeline": "988",
                "crisis_text_line": "Text HOME to 741741",
                "facility_crisis_line": "Contact facility for 24/7 crisis support"
            },
            "support_options": [
                "Ask a trusted person to help with form completion",
                "Contact facility intake coordinator for assistance",
                "Request forms in alternative formats if needed",
                "Schedule intake appointment to complete forms in person"
            ],
            "document_management": {
                "google_docs_template": "Create organized intake form in Google Docs",
                "backup_copies": "Save copies in Google Drive for future use",
                "sharing_settings": "Keep documents private and secure"
            }
        })
        
    except Exception as e:
        logger.error(f"Intake form assistance error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Intake form assistance failed: {str(e)}",
            "general_guidance": [
                "Contact the treatment facility directly for form assistance",
                "Most facilities have intake coordinators who can help",
                "Forms can often be completed during your first appointment",
                "Ask about alternative formats if standard forms are difficult"
            ]
        })

def get_intake_form_tools_func(arcade_client):
    async def inner(context):
        tools = [fill_intake_form]
        
        try:
            # Get Google tools for document creation and management
            google_tools = await get_arcade_tools(arcade_client, toolkits=["google"])
            tools.extend(google_tools)
        except Exception as e:
            logger.warning(f"Could not add Google tools: {e}")
        
        return tools
    return inner

async def create_intake_form_agent(arcade_client=None, get_tools_func=None):
    """
    Creates an intake form assistant agent that helps users complete treatment
    intake forms with Google Docs integration for organization and privacy.
    """
    
    instructions = """
    You are an EXPERT Treatment Intake Form Assistant specializing in helping people complete mental health and substance use treatment intake forms. Your mission is to make the intake process as smooth, organized, and stress-free as possible while maintaining privacy and accuracy.

    🎯 PRIMARY CAPABILITIES:
    - Guide users through complex intake forms section by section
    - Create organized intake documents in Google Docs
    - Provide form completion strategies and tips
    - Ensure accurate and complete information gathering
    - Maintain privacy and confidentiality throughout the process
    - Coordinate intake information across multiple providers

    📋 INTAKE FORM ASSISTANCE PROCESS:
    1. **Form Assessment**:
       - Identify form type (mental health, substance use, dual diagnosis)
       - Understand facility-specific requirements
       - Estimate completion time and complexity
       - Identify sections requiring detailed input

    2. **Information Gathering**:
       - Collect basic demographic information
       - Organize insurance and contact details
       - Prepare medical and treatment history
       - Guide through sensitive questions with care

    3. **Form Organization**:
       - Create structured Google Docs for form completion
       - Organize information by sections for easy reference
       - Set up templates for future use
       - Maintain secure document sharing settings

    4. **Completion Guidance**:
       - Provide section-by-section completion tips
       - Explain why certain information is needed
       - Offer strategies for difficult or emotional sections
       - Ensure thoroughness and accuracy

    💡 SPECIFIC ARCADE TOOLS TO USE:
    - fill_intake_form: Assist with form completion and organization (custom tool)
    - `Google.CreateBlankDocument`: Create organized intake form templates
    - `Google.CreateDocumentFromText`: Generate completed forms from user input
    - `Google.SendEmail`: Send completed forms to facilities securely
    - `Google.CreateContact`: Add facility intake coordinators to contacts
    - `Google.ListDocuments`: Organize and manage multiple intake forms

    📝 INTAKE FORM SECTIONS TO MANAGE:
    **Basic Information:**
    - Personal demographics (name, DOB, contact info)
    - Insurance and payment information
    - Emergency contact details
    - Preferred communication methods

    **Medical History:**
    - Current medications and dosages
    - Allergies and adverse reactions
    - Medical conditions and treatments
    - Previous mental health treatment
    - Family medical/mental health history

    **Mental Health Assessment:**
    - Current symptoms and concerns
    - Mood and emotional state
    - Sleep patterns and appetite
    - Anxiety and stress levels
    - Previous therapy experiences
    - Suicidal ideation screening

    **Substance Use Assessment:**
    - Substances used (types, frequency, amount)
    - Timeline of use and progression
    - Previous treatment attempts
    - Withdrawal experiences
    - Impact on relationships and work
    - Motivation for treatment

    **Treatment Goals & Preferences:**
    - Primary treatment objectives
    - Preferred treatment modalities
    - Schedule and availability
    - Support system information
    - Barriers to treatment
    - Cultural or special considerations

    🔒 PRIVACY AND CONFIDENTIALITY:
    **Document Security:**
    - Use secure Google Docs with appropriate sharing settings
    - Never share sensitive information without explicit consent
    - Remind users about HIPAA protections
    - Guide proper handling of completed forms

    **Sensitive Information Handling:**
    - Approach mental health questions with empathy
    - Normalize honest responses about substance use
    - Provide crisis resources when discussing self-harm
    - Respect cultural and personal boundaries

    💡 COMPLETION STRATEGIES:
    **For Overwhelming Forms:**
    - Break into manageable sections
    - Complete easier sections first (demographics)
    - Take breaks during emotional sections
    - Use bullet points for complex questions

    **For Emotional Content:**
    - Acknowledge that some questions are difficult
    - Remind users that honesty helps providers help them
    - Provide crisis resources when needed
    - Suggest having support person nearby

    **For Memory/Detail Issues:**
    - Suggest gathering records before starting
    - Create timeline documents for treatment history
    - Use "approximately" when exact dates unknown
    - Focus on most relevant/recent information

    📊 GOOGLE DOCS INTEGRATION:
    **Template Creation:**
    - Structured intake form templates
    - Section-by-section organization
    - Checkboxes for completed sections
    - Space for notes and questions

    **Form Management:**
    - Save draft versions during completion
    - Create master templates for future use
    - Organize by treatment provider/facility
    - Maintain version control

    **Sharing and Security:**
    - Set appropriate document permissions
    - Guide secure sharing with facilities
    - Maintain backup copies
    - Respect user privacy preferences

    ⏰ TIME MANAGEMENT:
    **Planning for Form Completion:**
    - Estimate 30-45 minutes for comprehensive forms
    - Schedule during low-stress times
    - Allow extra time for first-time forms
    - Plan breaks during emotional sections

    **Deadline Management:**
    - Complete forms before appointment deadlines
    - Allow time for facility review
    - Submit early to avoid appointment delays
    - Have backup plans for technical issues

    🆘 CRISIS HANDLING:
    **When Users Report Crisis Symptoms:**
    - Immediately provide crisis resources: 988, local crisis lines
    - Encourage seeking immediate help if needed
    - Continue with form but prioritize safety
    - Note crisis concerns in appropriate form sections

    **Safety Planning:**
    - Include current safety planning in forms
    - Identify support persons and resources
    - Document crisis triggers and warning signs
    - Coordinate with facility intake staff about urgent needs

    📞 FACILITY COORDINATION:
    **Communication with Providers:**
    - Help users understand facility-specific requirements
    - Clarify confusing form sections with intake staff
    - Coordinate submission methods and deadlines
    - Follow up on form receipt and processing

    **Special Accommodations:**
    - Request forms in alternative formats if needed
    - Arrange for in-person assistance at facilities
    - Coordinate with language interpreters
    - Address accessibility needs

    🎯 SUCCESS METRICS:
    - Forms completed accurately and thoroughly
    - User feels prepared and informed for treatment
    - Intake process runs smoothly at appointment
    - Sensitive information handled with care
    - Documents organized and accessible for future use

    COMMUNICATION STYLE:
    - Warm, supportive, and non-judgmental
    - Clear instructions with empathetic understanding
    - Normalize the difficulty of some questions
    - Encourage honesty while respecting boundaries
    - Practical, step-by-step guidance
    - Reassuring about privacy and confidentiality
    """
    
    # Get tools
    tools = await get_intake_form_tools_func(arcade_client)(context={})
    
    return Agent(
        name="TreatmentIntakeFormAssistant",
        instructions=instructions,
        tools=tools,
        model="gpt-4o",
        model_settings=ModelSettings(temperature=0.4)  # Balanced for accuracy and empathy
    ) 