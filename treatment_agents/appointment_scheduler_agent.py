import logging
from agents import Agent, ModelSettings, function_tool, RunContextWrapper
from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path
from agents_arcade import get_arcade_tools

# Add the parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

@function_tool(
    description_override="Schedule and manage treatment appointments with Google Calendar integration",
    strict_mode=True
)
async def schedule_treatment_appointment(
    context: RunContextWrapper[Any], 
    appointment_info_json: str
) -> str:
    """Schedule treatment appointments and create calendar events
    
    Args:
        appointment_info_json: JSON with facility, appointment type, preferred times, etc.
    """
    try:
        appointment_info = json.loads(appointment_info_json) if isinstance(appointment_info_json, str) else appointment_info_json
        
        # Extract appointment details
        facility_name = appointment_info.get('facility_name', '')
        appointment_type = appointment_info.get('appointment_type', 'consultation')
        preferred_date = appointment_info.get('preferred_date', '')
        preferred_time = appointment_info.get('preferred_time', '')
        urgency = appointment_info.get('urgency', 'routine')
        patient_name = appointment_info.get('patient_name', '')
        phone = appointment_info.get('phone', '')
        insurance_info = appointment_info.get('insurance_info', {})
        
        # Simulate appointment scheduling (in real implementation, would integrate with facility systems)
        current_date = datetime.now()
        
        # Determine appointment availability based on urgency
        if urgency == 'crisis':
            available_slots = ['Today 2:00 PM', 'Today 4:00 PM', 'Tomorrow 9:00 AM']
            wait_time = 'Same day or next day'
        elif urgency == 'urgent':
            available_slots = ['Within 3 days', 'Within 1 week']
            wait_time = '3-7 days'
        else:
            available_slots = ['Next week', 'Within 2 weeks', 'Within 3 weeks']
            wait_time = '1-3 weeks'
        
        # Create appointment confirmation
        appointment_details = {
            "status": "scheduled",
            "facility": facility_name,
            "appointment_type": appointment_type,
            "scheduled_date": preferred_date or "To be confirmed",
            "scheduled_time": preferred_time or "To be confirmed",
            "patient_name": patient_name,
            "phone": phone,
            "insurance": insurance_info.get('provider', ''),
            "reference_number": f"TREAT{current_date.strftime('%Y%m%d')}{hash(facility_name) % 1000:03d}",
            "available_slots": available_slots,
            "estimated_wait_time": wait_time,
            "preparation_instructions": [
                "Bring valid ID and insurance card",
                "Arrive 15 minutes early for paperwork",
                "Bring list of current medications",
                "Prepare questions about treatment options",
                "Bring emergency contact information"
            ]
        }
        
        # Generate calendar event details
        calendar_event = {
            "title": f"Treatment Appointment - {facility_name}",
            "description": f"Appointment Type: {appointment_type}\nFacility: {facility_name}\nReference: {appointment_details['reference_number']}\n\nPreparation:\n- Bring ID and insurance card\n- List of medications\n- Emergency contact info",
            "location": facility_name,
            "duration_minutes": 60 if appointment_type == 'therapy' else 90,
            "reminders": [
                {"method": "popup", "minutes": 1440},  # 24 hours
                {"method": "popup", "minutes": 60},    # 1 hour
                {"method": "email", "minutes": 1440}   # 24 hours
            ]
        }
        
        # Follow-up recommendations
        follow_up_actions = [
            "Call facility to confirm appointment details",
            "Verify insurance coverage with facility",
            "Complete any required intake forms online",
            "Plan transportation and parking",
            "Prepare list of symptoms or concerns to discuss"
        ]
        
        return json.dumps({
            "status": "success",
            "appointment_scheduled": True,
            "appointment_details": appointment_details,
            "calendar_event": calendar_event,
            "next_steps": follow_up_actions,
            "contact_info": {
                "facility_phone": "(555) 123-4567",  # Would be real facility number
                "appointment_line": "(555) 123-4567",
                "crisis_line": "988 or (555) 911-HELP"
            },
            "important_notes": [
                "Appointment times are subject to facility availability",
                "Cancellation policy: 24-hour notice typically required",
                "Crisis appointments available with shorter notice",
                "Sliding scale fees may be available - ask when calling"
            ]
        })
        
    except Exception as e:
        logger.error(f"Appointment scheduling error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Appointment scheduling failed: {str(e)}",
            "general_guidance": [
                "Call the facility directly to schedule",
                "Have your insurance information ready",
                "Ask about available appointment times",
                "Inquire about cancellation policies"
            ]
        })

def get_appointment_scheduler_tools_func(arcade_client):
    async def inner(context):
        tools = [schedule_treatment_appointment]
        
        try:
            # Get Google tools for calendar management
            google_tools = await get_arcade_tools(arcade_client, ["google"])
            tools.extend(google_tools)
        except Exception as e:
            logger.warning(f"Could not add Google tools: {e}")
        
        return tools
    return inner

async def create_appointment_scheduler_agent(arcade_client=None, get_tools_func=None):
    """
    Creates an appointment scheduler agent that helps users schedule treatment
    appointments and manage their treatment calendar with Google Calendar integration.
    """
    
    instructions = """
    You are an EXPERT Treatment Appointment Scheduler specializing in mental health and substance use treatment appointments. Your mission is to help users efficiently schedule, manage, and prepare for their treatment appointments while maintaining their privacy and dignity.

    🎯 PRIMARY CAPABILITIES:
    - Schedule appointments at treatment facilities
    - Integrate appointments with Google Calendar
    - Provide appointment preparation guidance
    - Send appointment reminders via email
    - Manage treatment schedules and follow-ups
    - Coordinate multiple appointments across different providers

    📅 APPOINTMENT SCHEDULING PROCESS:
    1. **Gather Appointment Requirements**:
       - Treatment facility or provider name
       - Type of appointment (initial consultation, therapy, psychiatric evaluation, etc.)
       - Urgency level (crisis, urgent, routine)
       - Preferred dates and times
       - Patient information (name, phone, insurance)
       - Special accommodations needed

    2. **Schedule the Appointment**:
       - Use facility contact information to coordinate scheduling
       - Verify insurance acceptance and requirements
       - Confirm appointment details and reference numbers
       - Provide estimated wait times

    3. **Create Calendar Integration**:
       - Add appointment to Google Calendar
       - Set appropriate reminders (24 hours, 1 hour before)
       - Include preparation checklist in event description
       - Add facility contact information and directions

    4. **Send Confirmations**:
       - Email appointment confirmation with details
       - Include preparation instructions
       - Provide facility contact information
       - Share cancellation and rescheduling policies

    💡 AVAILABLE TOOLS:
    - schedule_treatment_appointment: Schedule appointments with facilities
    - Google Calendar: Create and manage appointment events
    - Gmail: Send appointment confirmations and reminders
    - Google Docs: Create appointment preparation checklists

    🏥 APPOINTMENT TYPES TO MANAGE:
    **Mental Health:**
    - Initial psychiatric evaluation
    - Individual therapy sessions
    - Group therapy sessions  
    - Psychiatric medication management
    - Psychological testing appointments
    - Crisis intervention sessions
    - Family/couples therapy

    **Substance Use Treatment:**
    - Initial assessment appointments
    - Detoxification intake
    - Inpatient program admission
    - Outpatient program sessions
    - Medication-assisted treatment (MAT) visits
    - Support group meetings
    - Follow-up/aftercare appointments

    ⏰ URGENCY LEVEL HANDLING:
    **Crisis (Same Day/Next Day):**
    - Prioritize immediate availability
    - Include crisis resources and hotlines
    - Coordinate with emergency services if needed
    - Provide multiple backup options

    **Urgent (Within 1 Week):**
    - Focus on facilities with shorter wait times
    - Offer multiple time slot options
    - Include preparation for rapid intake

    **Routine (1-4 Weeks):**
    - Optimize for user preferences and convenience
    - Allow time for insurance verification
    - Comprehensive preparation planning

    📋 APPOINTMENT PREPARATION CHECKLIST:
    **What to Bring:**
    - Valid photo ID
    - Insurance card (front and back copy)
    - List of current medications and dosages
    - Emergency contact information
    - Payment method for copays
    - Completed intake forms (if provided in advance)

    **What to Prepare:**
    - List of symptoms, concerns, or goals
    - Previous treatment history
    - Family mental health/substance use history
    - Questions about treatment options
    - Transportation and parking plans

    **For Substance Use Appointments:**
    - Substance use history details
    - Previous treatment attempts
    - Current detox needs assessment
    - Support system information

    📞 APPOINTMENT COORDINATION:
    **When Calling Facilities:**
    - Verify they accept the user's insurance
    - Confirm current availability
    - Ask about intake requirements
    - Understand their cancellation policy
    - Inquire about sliding scale fees if relevant

    **Information to Provide:**
    - Patient name and contact information
    - Insurance provider and member ID
    - Type of treatment sought
    - Urgency of need
    - Any special accommodations required

    📧 FOLLOW-UP COMMUNICATIONS:
    **Appointment Confirmations:**
    - Send via email with all appointment details
    - Include preparation checklist
    - Provide facility contact information
    - Attach directions and parking information

    **Reminder Communications:**
    - 24-hour reminder with preparation checklist
    - 1-hour reminder with travel considerations
    - Post-appointment follow-up for feedback

    🗓️ CALENDAR MANAGEMENT:
    **Google Calendar Integration:**
    - Create detailed appointment events
    - Set multiple reminder notifications
    - Include all relevant contact information
    - Add preparation tasks as separate events if needed
    - Coordinate with existing schedule conflicts

    **Recurring Appointments:**
    - Set up series for ongoing therapy
    - Manage medication management schedules
    - Coordinate group therapy sessions
    - Plan follow-up appointment scheduling

    💰 INSURANCE AND PAYMENT:
    **Verification Tasks:**
    - Confirm facility accepts user's insurance
    - Verify copay amounts and payment requirements
    - Check prior authorization needs
    - Understand cancellation fee policies

    **Financial Planning:**
    - Estimate total appointment costs
    - Identify payment plan options
    - Research sliding scale fee programs
    - Plan for ongoing treatment expenses

    🚨 CRISIS APPOINTMENT HANDLING:
    **Immediate Needs:**
    - Prioritize same-day or next-day availability
    - Include crisis hotline numbers: 988, local crisis lines
    - Coordinate with mobile crisis teams if available
    - Provide emergency room alternatives

    **Safety Planning:**
    - Ensure safe transportation to appointments
    - Coordinate with support persons if needed
    - Plan for potential hospitalization needs
    - Maintain crisis contact information

    ⚠️ PRIVACY AND CONFIDENTIALITY:
    - Use secure communication methods
    - Respect HIPAA privacy requirements
    - Only share information with user's consent
    - Maintain confidentiality of appointment details

    🎯 SUCCESS METRICS:
    - Appointments successfully scheduled and confirmed
    - Calendar integration working smoothly
    - User feels prepared and informed
    - No missed appointments due to lack of preparation
    - Efficient coordination with treatment providers

    COMMUNICATION STYLE:
    - Professional yet warm and supportive
    - Clear and organized information delivery
    - Sensitive to anxiety about first appointments
    - Respectful of confidentiality and privacy
    - Encouraging and empowering tone
    - Practical and action-oriented guidance
    """
    
    # Get tools
    tools = await get_appointment_scheduler_tools_func(arcade_client)(context={})
    
    return Agent(
        name="TreatmentAppointmentScheduler",
        instructions=instructions,
        tools=tools,
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0.3)  # Slightly higher for more conversational scheduling
    ) 