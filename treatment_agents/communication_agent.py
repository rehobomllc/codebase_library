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
    description_override="Send professional emails to treatment facilities on behalf of users",
    strict_mode=True
)
async def send_treatment_communication(
    context: RunContextWrapper[Any], 
    communication_info_json: str
) -> str:
    """Send professional communications to treatment facilities
    
    Args:
        communication_info_json: JSON with facility info, message type, content, user details
    """
    try:
        comm_info = json.loads(communication_info_json) if isinstance(communication_info_json, str) else communication_info_json
        
        # Extract communication details
        facility_name = comm_info.get('facility_name', '')
        facility_email = comm_info.get('facility_email', '')
        message_type = comm_info.get('message_type', 'inquiry')
        user_name = comm_info.get('user_name', '')
        user_phone = comm_info.get('user_phone', '')
        insurance_info = comm_info.get('insurance_info', {})
        treatment_type = comm_info.get('treatment_type', '')
        urgency = comm_info.get('urgency', 'routine')
        specific_questions = comm_info.get('specific_questions', [])
        
        # Generate professional email content based on message type
        email_templates = {
            "inquiry": {
                "subject": f"Treatment Inquiry - {user_name}",
                "body": f"""Dear {facility_name} Team,

I hope this message finds you well. I am writing to inquire about treatment services at your facility.

**Patient Information:**
- Name: {user_name}
- Phone: {user_phone}
- Insurance: {insurance_info.get('provider', 'Will provide upon request')}
- Treatment Type Sought: {treatment_type}

**Inquiry Details:**
I am interested in learning more about your treatment programs and would appreciate information about:

• Available treatment options for {treatment_type}
• Current availability and wait times
• Insurance coverage and accepted plans
• Intake process and requirements
• Program schedules and duration

{f"**Specific Questions:**" + chr(10) + chr(10).join([f"• {q}" for q in specific_questions]) if specific_questions else ""}

{f"**Urgency:** This is a {urgency} request for treatment services." if urgency != 'routine' else ""}

I would be grateful for any information you can provide about your services. Please let me know the best way to proceed with an initial consultation or assessment.

Thank you for your time and the important work you do in helping people on their recovery journey.

Best regards,
{user_name}
{user_phone}"""
            },
            "appointment_request": {
                "subject": f"Appointment Request - {user_name}",
                "body": f"""Dear {facility_name} Scheduling Team,

I am writing to request an appointment for mental health/substance use treatment services.

**Patient Information:**
- Name: {user_name}
- Phone: {user_phone}
- Insurance: {insurance_info.get('provider', '')} - {insurance_info.get('plan_type', '')}
- Member ID: {insurance_info.get('member_id', 'Available upon request')}

**Appointment Request:**
- Treatment Type: {treatment_type}
- Preferred timeframe: {urgency}
- Scheduling preferences: {comm_info.get('scheduling_preferences', 'Flexible with scheduling')}

{f"**Special Considerations:**" + chr(10) + chr(10).join([f"• {note}" for note in comm_info.get('special_notes', [])]) if comm_info.get('special_notes') else ""}

Please let me know about:
• Available appointment times
• Intake requirements and paperwork
• Insurance verification process
• What to expect during the first appointment

I am committed to beginning treatment and appreciate your assistance in scheduling an appointment at your earliest convenience.

Thank you for your consideration.

Sincerely,
{user_name}
{user_phone}"""
            },
            "insurance_verification": {
                "subject": f"Insurance Verification Request - {user_name}",
                "body": f"""Dear {facility_name} Insurance/Billing Department,

I am writing to verify insurance coverage for treatment services at your facility.

**Insurance Information:**
- Patient Name: {user_name}
- Insurance Provider: {insurance_info.get('provider', '')}
- Plan Type: {insurance_info.get('plan_type', '')}
- Member ID: {insurance_info.get('member_id', '')}
- Group Number: {insurance_info.get('group_number', '')}

**Services to Verify:**
- {treatment_type} treatment services
- Intake/assessment appointments
- Individual and group therapy sessions
- Psychiatric services (if applicable)
- Medication management (if applicable)

**Questions:**
• Do you accept my insurance plan?
• What are my estimated copays and deductibles?
• Is prior authorization required?
• What documentation do you need from me?
• Are there any limitations on covered services?

I would appreciate verification of coverage before scheduling my first appointment. Please let me know if you need any additional information.

Thank you for your assistance.

Best regards,
{user_name}
{user_phone}"""
            },
            "follow_up": {
                "subject": f"Follow-up: Treatment Services Inquiry - {user_name}",
                "body": f"""Dear {facility_name} Team,

I hope this message finds you well. I am following up on my previous inquiry about treatment services.

**Original Inquiry:** {comm_info.get('original_date', 'Recent inquiry')} regarding {treatment_type} treatment

**Patient:** {user_name}
**Phone:** {user_phone}

I wanted to check on the status of my inquiry and see if there are any updates regarding:
• Treatment availability
• Appointment scheduling
• Insurance verification
• Next steps in the process

{f"**Additional Information:**" + chr(10) + chr(10).join([f"• {info}" for info in comm_info.get('additional_info', [])]) if comm_info.get('additional_info') else ""}

I remain very interested in your services and am ready to move forward with treatment. Please let me know how I can best proceed.

Thank you for your time and consideration.

Sincerely,
{user_name}
{user_phone}"""
            }
        }
        
        # Get the appropriate template
        template = email_templates.get(message_type, email_templates["inquiry"])
        
        # Add crisis resources if urgency is high
        crisis_footer = ""
        if urgency in ['crisis', 'urgent']:
            crisis_footer = f"""

**Note:** If you or someone you know is experiencing a mental health or substance use crisis, please contact:
• National Suicide Prevention Lifeline: 988
• Crisis Text Line: Text HOME to 741741
• Emergency Services: 911
• Local Crisis Line: {comm_info.get('local_crisis_line', 'Contact your local crisis center')}"""

        # Compile final email
        final_email = {
            "to": facility_email,
            "subject": template["subject"],
            "body": template["body"] + crisis_footer,
            "priority": "high" if urgency in ['crisis', 'urgent'] else "normal"
        }
        
        # Generate follow-up recommendations
        follow_up_actions = [
            "Call facility directly if no response within 2-3 business days",
            "Have insurance card ready for verification questions",
            "Prepare list of questions for when they respond",
            "Consider visiting facility in person if email doesn't work",
            "Keep records of all communications for your files"
        ]
        
        return json.dumps({
            "status": "success",
            "email_prepared": True,
            "facility": facility_name,
            "message_type": message_type,
            "email_details": final_email,
            "follow_up_timeline": "2-3 business days for response",
            "follow_up_actions": follow_up_actions,
            "backup_options": [
                f"Call {facility_name} directly at their main number",
                "Visit facility website for online contact forms",
                "Contact facility via social media if available",
                "Ask for referral to similar facilities if no response"
            ],
            "communication_tips": [
                "Be honest about your needs and situation",
                "Ask specific questions about their services",
                "Inquire about payment options and sliding scales",
                "Request information about their treatment approach",
                "Ask about family involvement opportunities"
            ],
            "privacy_note": "This email contains confidential health information and should be sent securely"
        })
        
    except Exception as e:
        logger.error(f"Treatment communication error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Communication preparation failed: {str(e)}",
            "general_guidance": [
                "Contact the facility directly by phone",
                "Visit their website for contact information",
                "Ask for help from a trusted person with communication",
                "Contact your insurance for in-network providers"
            ]
        })

def get_treatment_communication_tools_func(arcade_client):
    async def inner(context):
        tools = [send_treatment_communication]
        
        try:
            # Get Google tools for email and document management
            google_tools = await get_arcade_tools(arcade_client, toolkits=["google"])
            tools.extend(google_tools)
        except Exception as e:
            logger.warning(f"Could not add Google tools: {e}")
        
        return tools
    return inner

async def create_treatment_communication_agent(arcade_client=None, get_tools_func=None):
    """
    Creates a treatment communication agent that handles professional email
    communication with treatment facilities on behalf of users.
    """
    
    instructions = """
    You are an EXPERT Treatment Communication Specialist who helps users communicate professionally and effectively with mental health and substance use treatment facilities. Your mission is to facilitate clear, respectful, and productive communication that helps users access the treatment they need.

    🎯 PRIMARY CAPABILITIES:
    - Draft professional emails to treatment facilities
    - Handle various communication types (inquiries, appointments, insurance verification)
    - Maintain appropriate tone and confidentiality
    - Follow up on communications effectively
    - Coordinate multiple facility communications
    - Provide communication guidance and templates

    📧 COMMUNICATION TYPES TO HANDLE:
    **Initial Inquiries:**
    - Treatment service availability
    - Program information requests
    - Facility overview and approach
    - Initial screening questions
    - General information gathering

    **Appointment Requests:**
    - Initial consultation scheduling
    - Intake appointment requests
    - Emergency/crisis appointment needs
    - Rescheduling and changes
    - Follow-up appointment coordination

    **Insurance Verification:**
    - Coverage verification requests
    - Prior authorization inquiries
    - Cost estimation requests
    - Payment plan discussions
    - Financial assistance inquiries

    **Follow-up Communications:**
    - Response to facility communications
    - Progress updates and check-ins
    - Address concerns or questions
    - Coordinate care between providers

    💡 SPECIFIC ARCADE TOOLS TO USE:
    - send_treatment_communication: Draft professional emails (custom tool)
    - `Google.SendEmail`: Send emails directly via Gmail API
    - `Google.CreateDraftEmail`: Create draft emails for user review
    - `Google.CreateBlankDocument`: Create communication templates
    - `Google.CreateContact`: Add facility contacts to user's address book
    - `Google.ListEmails`: Check for facility responses
    - `Google.GetThread`: Follow email conversation threads

    📋 COMMUNICATION PROCESS:
    1. **Gather Communication Requirements**:
       - Purpose of communication (inquiry, appointment, verification)
       - Facility information (name, email, phone)
       - User information (name, phone, insurance)
       - Specific questions or requests
       - Urgency level and timeline

    2. **Draft Professional Communication**:
       - Use appropriate business email format
       - Include all necessary information
       - Maintain professional yet personal tone
       - Respect confidentiality and privacy
       - Include relevant contact information

    3. **Send and Track Communications**:
       - Send emails through secure channels
       - Create copies for user records
       - Set follow-up reminders
       - Track response times and outcomes

    4. **Follow-up Management**:
       - Monitor for responses
       - Send polite follow-up messages when appropriate
       - Coordinate next steps based on responses
       - Provide alternative communication options

    📝 EMAIL STRUCTURE AND TONE:
    **Professional Headers:**
    - Clear, descriptive subject lines
    - Appropriate recipient information
    - Professional greeting and closing

    **Body Content:**
    - Clear statement of purpose
    - Organized information presentation
    - Specific questions or requests
    - Necessary personal/insurance information
    - Appropriate level of detail

    **Tone Guidelines:**
    - Professional yet warm and human
    - Respectful of facility staff time
    - Clear and direct communication
    - Appropriate urgency level
    - Grateful and appreciative

    🔒 PRIVACY AND CONFIDENTIALITY:
    **Information Sharing:**
    - Only share information with user consent
    - Include necessary details for treatment access
    - Respect HIPAA privacy requirements
    - Use secure communication methods

    **Confidentiality Reminders:**
    - Note confidential nature of health information
    - Remind facilities of privacy obligations
    - Use appropriate security measures
    - Maintain communication records securely

    ⏰ COMMUNICATION TIMING:
    **Response Expectations:**
    - Routine inquiries: 2-3 business days
    - Appointment requests: 1-2 business days
    - Crisis communications: Same day or within hours
    - Insurance verification: 3-5 business days

    **Follow-up Schedule:**
    - First follow-up: 3 business days after initial communication
    - Second follow-up: 1 week after first follow-up
    - Alternative options: After 2 weeks of no response

    🚨 CRISIS COMMUNICATION HANDLING:
    **Urgent/Crisis Situations:**
    - Mark emails as high priority
    - Include crisis resources in all communications
    - Suggest immediate phone contact as well
    - Coordinate with emergency services if needed
    - Follow up within hours, not days

    **Crisis Resources to Include:**
    - National Suicide Prevention Lifeline: 988
    - Crisis Text Line: Text HOME to 741741
    - Local crisis resources
    - Facility emergency contact information

    📞 MULTI-CHANNEL APPROACH:
    **Email + Phone Strategy:**
    - Use email for detailed information sharing
    - Recommend phone calls for urgent matters
    - Coordinate in-person visits when appropriate
    - Provide multiple contact options

    **Backup Communication Methods:**
    - Facility websites and online forms
    - Social media messaging (when appropriate)
    - In-person visits to facilities
    - Third-party referral sources

    🏥 FACILITY COORDINATION:
    **Working with Multiple Facilities:**
    - Maintain organized communication records
    - Compare responses and options
    - Coordinate scheduling across providers
    - Track different facility requirements

    **Provider Relationship Building:**
    - Professional and consistent communication
    - Respectful of facility policies and procedures
    - Collaborative approach to treatment planning
    - Appreciation for facility staff efforts

    📊 COMMUNICATION TRACKING:
    **Record Keeping:**
    - Google Docs for communication logs
    - Track dates, recipients, responses
    - Note important information and next steps
    - Maintain organized filing system

    **Response Management:**
    - Prompt acknowledgment of facility responses
    - Clear communication of next steps
    - Coordination with user for decision-making
    - Follow-through on commitments made

    🎯 SUCCESS METRICS:
    - Facilities respond promptly to communications
    - User needs are clearly communicated
    - Appointments and services are successfully coordinated
    - Professional relationships are established
    - Treatment access barriers are reduced

    COMMUNICATION STYLE:
    - Professional yet personal and warm
    - Clear, organized, and comprehensive
    - Respectful of facility staff and policies
    - Advocacy-oriented while maintaining boundaries
    - Grateful and appreciative of facility assistance
    - Confidential and secure in handling sensitive information
    """
    
    # Get tools
    tools = await get_treatment_communication_tools_func(arcade_client)(context={})
    
    return Agent(
        name="TreatmentCommunicationAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-4o",
        model_settings=ModelSettings(temperature=0.3)  # Lower temperature for professional communication
    ) 