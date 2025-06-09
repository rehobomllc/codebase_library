import os
import asyncio
import logging
import json
import sys
from pathlib import Path
import redis.asyncio as aioredis
from celery import Celery
from dotenv import load_dotenv
import httpx
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Form, Query, File, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from arcadepy import AsyncArcade
# OpenAI Agents SDK imports
from agents import Agent, Runner, RunConfig, ItemHelpers, set_default_openai_key, ModelSettings
from agents.result import RunResult, RunResultStreaming
from agents.handoffs import handoff
from agents.tracing import trace, gen_trace_id
from agents.exceptions import InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
# Arcade integration imports
from agents_arcade import get_arcade_tools
from agents_arcade.errors import AuthorizationError as ArcadeAuthorizationError
from agents_arcade.errors import ToolError
from typing import Dict, List, Optional, Any, AsyncGenerator

import contextlib
import uvicorn
import re
from datetime import datetime, timedelta, timezone
import ssl
import certifi

# Project-specific imports
from config import config
from services.database import (
    db_manager, fetch_profile, save_profile, save_treatments, fetch_treatments,
    save_appointments, fetch_appointments, save_treatment_data, get_treatment_data,
    update_treatment_status, get_treatment_status, track_api_usage, get_user_usage_stats
)
from debug_utils import tracker, get_debug_dashboard_data, inject_debug_script, debug_endpoint
from services.billing import verify_subscription, verify_feature_access

# Vision analysis imports
from services.vision_analyzer import (
    analyze_medical_document_file, analyze_prescription_label_file, 
    analyze_insurance_card_file, analyze_treatment_form_file, close_vision_analyzer
)

# Treatment agents imports
from treatment_agents.triage_agent import create_treatment_triage_agent
from treatment_agents.facility_search_agent import create_facility_search_agent
from treatment_agents.insurance_verification_agent import create_insurance_verification_agent
from treatment_agents.appointment_scheduler_agent import create_appointment_scheduler_agent
from treatment_agents.intake_form_agent import create_intake_form_agent
from treatment_agents.reminder_agent import create_treatment_reminder_agent
from treatment_agents.communication_agent import create_treatment_communication_agent

from utils.tool_provider import initialize_tool_provider, get_tool_provider, UnifiedToolProvider
from utils.arcade_auth_helper import run_agent_with_auth_handling, AuthHelperError, check_toolkit_authorization_status

# SSL Certificate Fix for macOS
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['CURL_CA_BUNDLE'] = certifi.where()

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

json_formatter = JSONFormatter()
root_logger = logging.getLogger()
root_logger.setLevel(config.LOG_LEVEL if hasattr(config, 'LOG_LEVEL') else logging.INFO)

file_handler = logging.FileHandler(BASE_DIR / "treatment_navigator.log")
file_handler.setFormatter(json_formatter)
root_logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(json_formatter)
root_logger.addHandler(stream_handler)

logger = logging.getLogger("treatment_navigator")

logging.getLogger("arcadepy").setLevel(logging.WARNING)
logging.getLogger("agents").setLevel(logging.INFO)
logging.getLogger("agents_arcade").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

for _name in ["arcadepy._base_client", "httpcore", "httpcore.connection", "httpcore.http11", "openai._base_client", "asyncio"]:
    logging.getLogger(_name).setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global arcade_client_global
    logger.info("Treatment Navigator startup sequence initiated...")
    
    # Initialize database pool
    if config.DATABASE_URL:
        try:
            await db_manager.initialize_pool(config.DATABASE_URL)
            logger.info("Database pool initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}", exc_info=True)
            raise RuntimeError(f"Database initialization failed: {e}")
    else:
        logger.error("DATABASE_URL not found in configuration")
        raise RuntimeError("DATABASE_URL not configured")
    
    if config.OPENAI_API_KEY: 
        set_default_openai_key(config.OPENAI_API_KEY)
        logger.info("Default OpenAI API key set.")
    else: 
        logger.warning("OPENAI_API_KEY not found.")
    
    if config.ARCADE_API_KEY:
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            custom_http_client = httpx.AsyncClient(verify=ssl_context, timeout=30.0)
            arcade_client_global = AsyncArcade(api_key=config.ARCADE_API_KEY, http_client=custom_http_client)
            initialize_tool_provider(arcade_client_global)
            logger.info("AsyncArcade client and ToolProvider initialized.")
        except Exception as e: 
            logger.error(f"Arcade client/ToolProvider init failed: {e}", exc_info=True)
            initialize_tool_provider(None)
    else: 
        logger.warning("ARCADE_API_KEY not found.")
        initialize_tool_provider(None)
    
    config_errors = config.validate_configuration()
    if config_errors: 
        logger.critical(f"CRITICAL CONFIG ERRORS: {config_errors}")
    else: 
        logger.info("Configuration validated.")
    
    logger.info("Treatment Navigator startup completed.")
    
    yield
    
    # Shutdown
    logger.info("Treatment Navigator shutting down...")
    
    # Close database pool
    try:
        await db_manager.close_pool()
        logger.info("Database pool closed.")
    except Exception as e:
        logger.error(f"Error closing database pool: {e}", exc_info=True)
    
    if arcade_client_global and hasattr(arcade_client_global, 'close'):
        try: 
            await arcade_client_global.close()
            logger.info("AsyncArcade client closed.")
        except Exception as e: 
            logger.error(f"Error closing AsyncArcade client: {e}", exc_info=True)
    
    # Close vision analyzer
    try:
        await close_vision_analyzer()
        logger.info("Vision analyzer client closed.")
    except Exception as e:
        logger.error(f"Error closing vision analyzer: {e}", exc_info=True)
    
    logger.info("Treatment Navigator shutdown complete.")

app = FastAPI(title="Treatment Navigator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

user_agents: Dict[str, Agent] = {}
conversation_histories: Dict[str, List[Dict[str, Any]]] = {}
user_trace_identifiers: Dict[str, Dict[str, Any]] = {}

arcade_client_global: Optional[AsyncArcade] = None
# Global treatment agents
_facility_search_agent_global: Optional[Agent] = None
_insurance_verification_agent_global: Optional[Agent] = None
_appointment_scheduler_agent_global: Optional[Agent] = None
_intake_form_agent_global: Optional[Agent] = None
_treatment_reminder_agent_global: Optional[Agent] = None
_treatment_communication_agent_global: Optional[Agent] = None

# Request/Response models for treatment use case
class ChatRequest(BaseModel): 
    message: str
    user_id: str

class ChatResponse(BaseModel): 
    reply: str
    appointment_id: Optional[str] = None

class ErrorResponse(BaseModel): 
    error: str

class FacilitySearchRequest(BaseModel): 
    user_id: str
    location: str
    treatment_type: str
    insurance_provider: Optional[str] = None
    specialties: Optional[List[str]] = None

class InsuranceVerificationRequest(BaseModel): 
    user_id: str
    insurance_provider: str
    insurance_id: str
    treatment_type: str

class AppointmentRequest(BaseModel): 
    user_id: str
    facility_name: str
    facility_contact: str
    preferred_date: Optional[str] = None
    urgency_level: str = "routine"

class IntakeFormRequest(BaseModel): 
    user_id: str
    facility_name: str
    form_type: str
    patient_info: Dict[str, Any]

class TreatmentReminderRequest(BaseModel): 
    user_id: str
    reminder_type: str  # "appointment", "medication", "milestone"
    title: str
    datetime: str
    details: Optional[str] = None

# Vision analysis request models
class VisionAnalysisResponse(BaseModel):
    success: bool
    analysis_type: str
    results: Dict[str, Any]
    error_message: Optional[str] = None

# Treatment-specific utility functions
def _parse_appointment_datetime(datetime_str: Optional[str]) -> Optional[str]:
    """Parse appointment datetime string into standardized format."""
    if not datetime_str: return None
    common_formats = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M", "%B %d, %Y %H:%M"]
    for fmt in common_formats:
        try: 
            dt_obj = datetime.strptime(datetime_str.split("T")[0] if "T" in datetime_str else datetime_str, fmt.split("T")[0] if "T" in fmt else fmt)
            return dt_obj.strftime("%Y-%m-%d %H:%M")
        except ValueError: continue
    try: 
        dt_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt_obj.strftime("%Y-%m-%d %H:%M")
    except ValueError: 
        logger.warning(f"Could not parse appointment datetime '{datetime_str}'.")
        return None

def _create_treatment_match_indicators(facility_data: Dict[str, Any], user_criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create treatment facility match indicators based on user criteria."""
    indicators = []
    factor_display_map = {
        "location": {"label": "Location", "icon": "📍"}, 
        "insurance": {"label": "Insurance", "icon": "💳"},
        "specialties": {"label": "Specialties", "icon": "🏥"}, 
        "availability": {"label": "Availability", "icon": "📅"},
        "treatment_type": {"label": "Treatment Type", "icon": "🩺"}, 
        "rating": {"label": "Rating", "icon": "⭐"},
    }
    
    # Basic match indicators for treatment facilities
    for factor, display_info in factor_display_map.items():
        if factor in facility_data:
            status = "matched" if facility_data.get(factor) else "neutral"
            indicators.append({
                "factor": display_info["label"], 
                "status": status, 
                "icon": display_info["icon"], 
                "details": f"{factor}: {facility_data.get(factor, 'N/A')}"
            })
    return indicators

async def filter_available_facilities(facilities: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
    """Filter treatment facilities based on availability and operational status."""
    if not facilities: 
        return facilities
    
    available_facilities = []
    unavailable_facilities = []
    
    logger.info(f"Filtering {len(facilities)} facilities for user {user_id}")
    
    for facility in facilities:
        facility_name = facility.get('name', 'Unknown Facility')
        
        try:
            # Check if facility is currently operational
            is_operational = facility.get('operational', True)
            accepting_patients = facility.get('accepting_patients', True)
            has_availability = facility.get('has_availability', True)
            temporary_closure = facility.get('temporary_closure', False)
            is_emergency = facility.get('is_emergency', False)
            
            if is_emergency:
                available_facilities.append(facility)
                logger.debug(f"Including emergency facility '{facility_name}'")
            elif is_operational and accepting_patients and has_availability and not temporary_closure:
                available_facilities.append(facility)
                logger.debug(f"Including available facility '{facility_name}'")
            else:
                unavailable_facilities.append(facility)
                reasons = []
                if not is_operational: reasons.append("not operational")
                if not accepting_patients: reasons.append("not accepting patients")
                if not has_availability: reasons.append("no availability")
                if temporary_closure: reasons.append("temporary closure")
                
                logger.info(f"Excluding facility '{facility_name}': {', '.join(reasons)}")
                
        except Exception as e:
            logger.warning(f"Error processing facility '{facility_name}': {e}")
            # Include facilities with processing errors for manual review
            available_facilities.append(facility)
    
    logger.info(f"Facility filtering results for {user_id}: {len(available_facilities)} available, {len(unavailable_facilities)} unavailable")
    return available_facilities

async def get_or_create_agent(user_id: str) -> Agent:
    global _facility_search_agent_global, _insurance_verification_agent_global, _appointment_scheduler_agent_global, _intake_form_agent_global, _treatment_reminder_agent_global, _treatment_communication_agent_global, arcade_client_global
    
    if user_id in user_agents: 
        return user_agents[user_id]
    
    if not arcade_client_global: 
        raise RuntimeError("Arcade client not initialized.")
    
    tool_provider = get_tool_provider()
    if not tool_provider: 
        raise RuntimeError("UnifiedToolProvider not initialized.")
    
    agent_tool_getter = tool_provider.create_tool_getter()
    
    # Initialize all treatment agents
    if _facility_search_agent_global is None: 
        _facility_search_agent_global = await create_facility_search_agent(arcade_client_global, agent_tool_getter)
    if _insurance_verification_agent_global is None: 
        _insurance_verification_agent_global = await create_insurance_verification_agent(arcade_client_global, agent_tool_getter)
    if _appointment_scheduler_agent_global is None: 
        _appointment_scheduler_agent_global = await create_appointment_scheduler_agent(arcade_client_global, agent_tool_getter)
    if _intake_form_agent_global is None: 
        _intake_form_agent_global = await create_intake_form_agent(arcade_client_global, agent_tool_getter)
    if _treatment_reminder_agent_global is None: 
        _treatment_reminder_agent_global = await create_treatment_reminder_agent(arcade_client_global, agent_tool_getter)
    if _treatment_communication_agent_global is None: 
        _treatment_communication_agent_global = await create_treatment_communication_agent(arcade_client_global, agent_tool_getter)
    
    if not all([_facility_search_agent_global, _insurance_verification_agent_global, _appointment_scheduler_agent_global, _intake_form_agent_global, _treatment_reminder_agent_global, _treatment_communication_agent_global]):
        raise RuntimeError("One or more specialized treatment agents failed to initialize.")
    
    # Create handoffs for the triage agent
    def create_handoff_input_filter(relevant_keywords: List[str]):
        """Create a handoff input filter that preserves relevant conversation context"""
        def filter_func(handoff_input_data):
            from agents.handoffs import HandoffInputData
            
            # Keep the last few messages for context
            filtered_items = []
            
            # Always include the original input that started the conversation
            if handoff_input_data.input_history:
                if isinstance(handoff_input_data.input_history, str):
                    filtered_items.append({"role": "user", "content": handoff_input_data.input_history})
                else:
                    # If it's a tuple/list of input items, take the last 3 for context
                    recent_history = list(handoff_input_data.input_history)[-3:]
                    filtered_items.extend(recent_history)
            
            # Include relevant pre-handoff items (agent analysis, user profile building)
            for item in handoff_input_data.pre_handoff_items:
                if hasattr(item, 'content') and any(keyword.lower() in str(item.content).lower() for keyword in relevant_keywords):
                    filtered_items.append(item)
            
            # Always include the handoff trigger and response
            filtered_items.extend(handoff_input_data.new_items)
            
            return HandoffInputData(
                input_history=tuple(filtered_items[-5:]),  # Limit to last 5 items for efficiency
                pre_handoff_items=handoff_input_data.pre_handoff_items,
                new_items=handoff_input_data.new_items
            )
        return filter_func

    handoffs_list = [
        handoff(
            agent=_facility_search_agent_global, 
            tool_name_override="FacilitySearch", 
            tool_description_override="Finds relevant treatment facilities based on user location, insurance, and treatment needs.",
            input_filter=create_handoff_input_filter(["facility", "search", "location", "insurance", "treatment"])
        ),
        handoff(
            agent=_insurance_verification_agent_global, 
            tool_name_override="InsuranceVerification", 
            tool_description_override="Verifies insurance coverage and benefits for specific treatment facilities.",
            input_filter=create_handoff_input_filter(["insurance", "verify", "coverage", "benefits", "plan"])
        ),
        handoff(
            agent=_appointment_scheduler_agent_global, 
            tool_name_override="AppointmentScheduler", 
            tool_description_override="Schedules treatment appointments with facilities and manages calendar integration.",
            input_filter=create_handoff_input_filter(["appointment", "schedule", "book", "calendar", "date", "time"])
        ),
        handoff(
            agent=_intake_form_agent_global, 
            tool_name_override="IntakeForm", 
            tool_description_override="Assists with completing intake forms and patient information collection.",
            input_filter=create_handoff_input_filter(["intake", "form", "paperwork", "information", "patient"])
        ),
        handoff(
            agent=_treatment_reminder_agent_global, 
            tool_name_override="TreatmentReminder", 
            tool_description_override="Creates and manages treatment reminders, appointments, and milestone tracking.",
            input_filter=create_handoff_input_filter(["reminder", "schedule", "appointment", "medication", "milestone"])
        ),
        handoff(
            agent=_treatment_communication_agent_global, 
            tool_name_override="TreatmentCommunication", 
            tool_description_override="Handles communication with treatment facilities on behalf of the user.",
            input_filter=create_handoff_input_filter(["communicate", "email", "contact", "facility", "message"])
        )
    ]
    
    triage_agent_instance = await create_treatment_triage_agent(arcade_client_global, handoff_actions=handoffs_list)
    user_agents[user_id] = triage_agent_instance
    conversation_histories[user_id] = []
    
    logger.info(f"Treatment Triage Agent created for user {user_id} with {len(handoffs_list)} handoffs.")
    return triage_agent_instance

async def _extract_text_from_streamed_result(result_stream: RunResultStreaming) -> Optional[str]:
    final_message_content: Optional[str] = None
    async for event in result_stream.stream_events():
        if event.type == "run_item_stream_event" and event.item.type == "message_output_item":
            final_message_content = ItemHelpers.text_message_output(event.item)
    if final_message_content is None and result_stream.final_output is not None:
        final_message_content = str(result_stream.final_output)
    return final_message_content



@app.get("/", response_class=HTMLResponse)
async def index(request: Request): 
    return templates.TemplateResponse("treatment_onboarding.html", {"request": request})

@app.post("/chat", response_model=ChatResponse, responses={
    400: {"model": ErrorResponse},
    401: {"description": "Arcade Tool Authorization Required or Pending", "content": {"application/json": {"example": {"error": "AuthHelperError", "message": "Please authorize via URL.", "authorization_url": "...", "auth_id_for_wait": "..."}}}},
    500: {"model": ErrorResponse}
})
async def chat(chat_request: ChatRequest):
    user_message = chat_request.message
    user_id = chat_request.user_id
    
    await track_api_usage(user_id, "chat", "user_interaction", "openai", 0, 0.0, 0, {"message_length": len(user_message)})
    
    if not user_message or not user_id: 
        raise HTTPException(status_code=400, detail="Message or User ID missing")

    # Create or get existing trace for this user's conversation
    trace_id_val = gen_trace_id()
    
    # Use context manager for proper trace lifecycle management
    with trace(
        workflow_name="TreatmentNavigationFlow", 
        trace_id=trace_id_val, 
        group_id=user_id,
        metadata={
            "request_id": str(id(chat_request)), 
            "interaction_type": "chat_message",
            "message_length": len(user_message)
        }
    ) as workflow_trace:
        # Store trace information for debugging if needed
        if user_id not in user_trace_identifiers: 
            user_trace_identifiers[user_id] = {"group_id": user_id, "session_trace_ids": []}
        user_trace_identifiers[user_id]["session_trace_ids"].append(trace_id_val)

        try:
            agent = await get_or_create_agent(user_id)
            current_conversation_history = conversation_histories.get(user_id, [])
            current_conversation_history.append({"role": "user", "content": user_message})
            
            run_config_for_chat = RunConfig(
                workflow_name="TreatmentNavigationFlow", 
                group_id=user_id, 
                trace_metadata={
                    "request_id": str(id(chat_request)), 
                    "interaction_type": "chat_message"
                }, 
                trace_include_sensitive_data=config.TRACE_API_CALLS
            )
            
            logger.info(f"Starting treatment agent run for user {user_id}")
            result_stream: RunResultStreaming = await run_agent_with_auth_handling(
                runner_callable=Runner.run_streamed,
                starting_agent=agent,
                input_data=current_conversation_history,
                user_id=user_id,
                arcade_client=arcade_client_global,
                run_config_kwargs={"run_config": run_config_for_chat} 
            )
            
            agent_reply_text = await _extract_text_from_streamed_result(result_stream)

            if agent_reply_text is not None:
                current_conversation_history.append({"role": "assistant", "content": agent_reply_text})
                conversation_histories[user_id] = current_conversation_history
            else:
                agent_reply_text = "I encountered an issue generating a response. Please try again."
                logger.error(f"Agent run for user {user_id} resulted in None reply after streaming.")

            # Extract appointment ID if present
            extracted_appointment_id = None
            if "APPOINTMENT_SCHEDULED::" in agent_reply_text:
                match = re.search(r"APPOINTMENT_SCHEDULED::([a-zA-Z0-9-]+)", agent_reply_text)
                if match: 
                    extracted_appointment_id = match.group(1)
            
            return ChatResponse(reply=agent_reply_text, appointment_id=extracted_appointment_id)
            
        except InputGuardrailTripwireTriggered as input_tripwire:
            # Handle input guardrail violations (crisis detection, off-topic, etc.)
            logger.critical(f"INPUT GUARDRAIL TRIGGERED for user {user_id}: {input_tripwire}")
            
            # Check if this was a crisis detection tripwire
            guardrail_results = getattr(input_tripwire, 'guardrail_results', [])
            crisis_detected = False
            crisis_resources = []
            
            for result in guardrail_results:
                if hasattr(result, 'output') and hasattr(result.output, 'output_info'):
                    output_info = result.output.output_info
                    if isinstance(output_info, dict):
                        if output_info.get('crisis_detected'):
                            crisis_detected = True
                            crisis_resources = output_info.get('recommended_resources', [])
                            logger.critical(f"CRISIS DETECTED for user {user_id}: Level {output_info.get('urgency_level')}")
                        elif not output_info.get('is_relevant', True):
                            # Off-topic request
                            logger.info(f"Off-topic request from user {user_id}: {output_info.get('reasoning', 'No reason provided')}")
                            return ChatResponse(
                                reply="I'm specialized in helping people find mental health and substance use treatment. For other topics, I'd recommend contacting the appropriate support channels. Is there anything related to mental health or substance use treatment I can help you with?"
                            )
            
            if crisis_detected:
                # Provide immediate crisis response
                crisis_response = """🚨 I've detected that you may be experiencing a mental health or substance use crisis. Please reach out for immediate help:

**IMMEDIATE CRISIS RESOURCES:**
• **National Suicide Prevention Lifeline: 988**
• **Crisis Text Line: Text HOME to 741741**  
• **Emergency Services: 911**
• **SAMHSA National Helpline: 1-800-662-4357**

You don't have to go through this alone. These resources have trained professionals available 24/7 to help.

After you've gotten the immediate support you need, I'm here to help you navigate longer-term treatment options."""

                if crisis_resources:
                    crisis_response += "\n\n**Additional Resources:**\n" + "\n".join([f"• {resource}" for resource in crisis_resources])
                
                return ChatResponse(reply=crisis_response)
            
            # Generic guardrail response if not crisis or off-topic
            return ChatResponse(
                reply="I want to make sure I provide you with the safest and most appropriate help. Could you please rephrase your request so I can better assist you with finding mental health or substance use treatment?"
            )
            
        except OutputGuardrailTripwireTriggered as output_tripwire:
            # Handle output guardrail violations (unsafe responses, medical advice, etc.)
            logger.critical(f"OUTPUT GUARDRAIL TRIGGERED for user {user_id}: {output_tripwire}")
            
            return ChatResponse(
                reply="I apologize, but I need to be extra careful with my responses in this sensitive area. Let me try to help you differently. Could you please tell me specifically what kind of mental health or substance use treatment support you're looking for?"
            )
                
        except AuthHelperError as ahe:
            logger.warning(f"AuthHelperError for user {user_id} during chat: {ahe.message}")
            if ahe.is_api_key_invalid:
                # API key is invalid - log error but continue with degraded functionality
                logger.error(f"Arcade API key is invalid for user {user_id}. Continuing with limited functionality.")
                agent_reply_text = "I'm currently experiencing some connectivity issues with external services, but I can still help you with treatment guidance and basic support. Some features like Google Calendar integration may not be available right now."
                return ChatResponse(reply=agent_reply_text)
            elif ahe.requires_user_action and ahe.auth_url:
                return JSONResponse(status_code=401, content={
                    "error": "AuthorizationRequired", 
                    "message": ahe.message, 
                    "authorization_url": ahe.auth_url, 
                    "auth_id_for_wait": ahe.auth_id_for_wait
                })
            else: 
                raise HTTPException(status_code=500, detail=f"Arcade tool authorization process failed: {ahe.message}")
        except ToolError as te: 
            logger.error(f"Tool execution error for user {user_id}: {te.message}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"A tool used by the agent encountered an error: {te.message}")
        except Exception as e:
            logger.error(f"Unexpected error during chat processing for user {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        # Context manager automatically handles trace.finish()

@app.post("/api/facility_search")
async def facility_search_endpoint(request_data: FacilitySearchRequest):
    """Search for treatment facilities based on user criteria."""
    global _facility_search_agent_global, arcade_client_global
    
    user_id = request_data.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not _facility_search_agent_global:
        tool_provider = get_tool_provider()
        assert tool_provider, "Tool provider missing for FacilitySearchAgent"
        _facility_search_agent_global = await create_facility_search_agent(arcade_client_global, tool_provider.create_tool_getter())
        assert _facility_search_agent_global, "Failed to init FacilitySearchAgent"
    
    search_prompt = f"Search for {request_data.treatment_type} treatment facilities in {request_data.location}"
    if request_data.insurance_provider:
        search_prompt += f" that accept {request_data.insurance_provider} insurance"
    if request_data.specialties:
        search_prompt += f" specializing in {', '.join(request_data.specialties)}"
    
    messages = [{"role": "user", "content": search_prompt}]
    
    try:
        run_config = RunConfig(workflow_name="FacilitySearchFlow", group_id=user_id)
        agent_run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, 
            starting_agent=_facility_search_agent_global,
            input_data=messages,
            user_id=user_id,
            arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config}
        )
        
        response_text = str(agent_run_result.final_output) if agent_run_result.final_output else "No facilities found matching your criteria."
        
        return {"status": "success", "message": response_text}
        
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={
                "error": "AuthorizationRequired", 
                "message": ahe.message, 
                "authorization_url": ahe.auth_url,
                "auth_id_for_wait": ahe.auth_id_for_wait
            })
        else:
            raise HTTPException(status_code=500, detail=f"Authorization failed: {ahe.message}")
    except Exception as e:
        logger.error(f"Error in facility search for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Facility search failed: {str(e)}")

@app.post("/api/insurance_verification")
async def insurance_verification_endpoint(request_data: InsuranceVerificationRequest):
    """Verify insurance coverage for treatment services."""
    global _insurance_verification_agent_global, arcade_client_global
    
    user_id = request_data.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not _insurance_verification_agent_global:
        tool_provider = get_tool_provider()
        assert tool_provider, "Tool provider missing for InsuranceVerificationAgent"
        _insurance_verification_agent_global = await create_insurance_verification_agent(arcade_client_global, tool_provider.create_tool_getter())
        assert _insurance_verification_agent_global, "Failed to init InsuranceVerificationAgent"
    
    verification_prompt = f"Verify {request_data.insurance_provider} coverage for {request_data.treatment_type} treatment. Insurance ID: {request_data.insurance_id}"
    messages = [{"role": "user", "content": verification_prompt}]
    
    try:
        run_config = RunConfig(workflow_name="InsuranceVerificationFlow", group_id=user_id)
        agent_run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, 
            starting_agent=_insurance_verification_agent_global,
            input_data=messages,
            user_id=user_id,
            arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config}
        )
        
        response_text = str(agent_run_result.final_output) if agent_run_result.final_output else "Unable to verify insurance coverage at this time."
        
        return {"status": "success", "message": response_text}
        
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={
                "error": "AuthorizationRequired", 
                "message": ahe.message, 
                "authorization_url": ahe.auth_url,
                "auth_id_for_wait": ahe.auth_id_for_wait
            })
        else:
            raise HTTPException(status_code=500, detail=f"Authorization failed: {ahe.message}")
    except Exception as e:
        logger.error(f"Error in insurance verification for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Insurance verification failed: {str(e)}")

@app.post("/api/schedule_appointment")
async def schedule_appointment_endpoint(request_data: AppointmentRequest):
    """Schedule an appointment with a treatment facility."""
    global _appointment_scheduler_agent_global, arcade_client_global
    
    user_id = request_data.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not _appointment_scheduler_agent_global:
        tool_provider = get_tool_provider()
        assert tool_provider, "Tool provider missing for AppointmentSchedulerAgent"
        _appointment_scheduler_agent_global = await create_appointment_scheduler_agent(arcade_client_global, tool_provider.create_tool_getter())
        assert _appointment_scheduler_agent_global, "Failed to init AppointmentSchedulerAgent"
    
    appointment_prompt = f"Schedule an appointment with {request_data.facility_name} (contact: {request_data.facility_contact})"
    if request_data.preferred_date:
        appointment_prompt += f" for {request_data.preferred_date}"
    appointment_prompt += f". Urgency level: {request_data.urgency_level}"
    
    messages = [{"role": "user", "content": appointment_prompt}]
    
    try:
        run_config = RunConfig(workflow_name="AppointmentSchedulingFlow", group_id=user_id)
        agent_run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, 
            starting_agent=_appointment_scheduler_agent_global,
            input_data=messages,
            user_id=user_id,
            arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config}
        )
        
        response_text = str(agent_run_result.final_output) if agent_run_result.final_output else "Unable to schedule appointment at this time."
        
        return {"status": "success", "message": response_text}
        
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={
                "error": "AuthorizationRequired", 
                "message": ahe.message, 
                "authorization_url": ahe.auth_url,
                "auth_id_for_wait": ahe.auth_id_for_wait
            })
        else:
            raise HTTPException(status_code=500, detail=f"Authorization failed: {ahe.message}")
    except Exception as e:
        logger.error(f"Error scheduling appointment for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Appointment scheduling failed: {str(e)}")

@app.post("/api/treatment_reminder")
async def treatment_reminder_endpoint(request_data: TreatmentReminderRequest):
    """Set up treatment reminders."""
    global _treatment_reminder_agent_global, arcade_client_global
    
    user_id = request_data.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not _treatment_reminder_agent_global:
        tool_provider = get_tool_provider()
        assert tool_provider, "Tool provider missing for TreatmentReminderAgent"
        _treatment_reminder_agent_global = await create_treatment_reminder_agent(arcade_client_global, tool_provider.create_tool_getter())
        assert _treatment_reminder_agent_global, "Failed to init TreatmentReminderAgent"
    
    reminder_prompt = f"Set up a {request_data.reminder_type} reminder for '{request_data.title}' on {request_data.datetime}"
    if request_data.details:
        reminder_prompt += f". Additional details: {request_data.details}"
    
    messages = [{"role": "user", "content": reminder_prompt}]
    
    try:
        run_config = RunConfig(workflow_name="TreatmentReminderFlow", group_id=user_id)
        agent_run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, 
            starting_agent=_treatment_reminder_agent_global,
            input_data=messages,
            user_id=user_id,
            arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config}
        )
        
        response_text = str(agent_run_result.final_output) if agent_run_result.final_output else "Unable to set up reminder at this time."
        
        return {"status": "success", "message": response_text}
        
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={
                "error": "AuthorizationRequired", 
                "message": ahe.message, 
                "authorization_url": ahe.auth_url,
                "auth_id_for_wait": ahe.auth_id_for_wait
            })
        else:
            raise HTTPException(status_code=500, detail=f"Authorization failed: {ahe.message}")
    except Exception as e:
        logger.error(f"Error setting treatment reminder for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Treatment reminder setup failed: {str(e)}")

@app.get("/api/profile/{user_id}")
async def get_user_profile(user_id: str):
    """Get user profile information."""
    try:
        profile = await fetch_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        return {"status": "success", "profile": profile}
    except Exception as e:
        logger.error(f"Error fetching profile for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

@app.get("/api/treatments/{user_id}")
async def get_user_treatments(user_id: str):
    """Get user's treatment information."""
    try:
        treatments = await fetch_treatments(user_id)
        return {"status": "success", "treatments": treatments or []}
    except Exception as e:
        logger.error(f"Error fetching treatments for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch treatments: {str(e)}")

@app.get("/api/appointments/{user_id}")
async def get_user_appointments(user_id: str):
    """Get user's appointment information."""
    try:
        appointments = await fetch_appointments(user_id)
        return {"status": "success", "appointments": appointments or []}
    except Exception as e:
        logger.error(f"Error fetching appointments for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch appointments: {str(e)}")

@app.get("/api/check_auth_status/{toolkit_name}")
async def api_check_toolkit_authorization_status(request: Request, toolkit_name: str, user_id: str = Query(...)):
    """Check authorization status for a specific toolkit."""
    try:
        if not arcade_client_global:
            raise HTTPException(status_code=500, detail="Arcade client not initialized")
        
        auth_status = await check_toolkit_authorization_status(
            arcade_client=arcade_client_global,
            toolkit_name=toolkit_name,
            user_id=user_id
        )
        return {"status": "success", "auth_status": auth_status}
    except Exception as e:
        logger.error(f"Error checking auth status for {toolkit_name}, user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check auth status: {str(e)}")

@app.get("/debug", response_class=HTMLResponse)
async def debug_dashboard_page(request: Request):
    return templates.TemplateResponse("debug_dashboard.html", {"request": request})

@app.get("/vision-test", response_class=HTMLResponse)
async def vision_test_page(request: Request):
    """Vision analysis test interface."""
    return templates.TemplateResponse("vision_test.html", {"request": request})

@app.get("/api/debug/dashboard")
@debug_endpoint
async def debug_dashboard():
    """Get debug dashboard data."""
    try:
        debug_data = await get_debug_dashboard_data()
        return {"status": "success", "debug_data": debug_data}
    except Exception as e:
        logger.error(f"Error getting debug dashboard data: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/js-error")
async def log_js_error(request: Request):
    """Log JavaScript errors from the frontend."""
    try:
        error_data = await request.json()
        logger.error(f"Frontend JS Error: {error_data.get('message', 'Unknown error')} at {error_data.get('filename', 'unknown file')}:{error_data.get('lineno', 'unknown line')}")
        return {"status": "logged"}
    except Exception as e:
        logger.error(f"Error logging JS error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.get("/api/usage_stats/{user_id}")
async def get_usage_stats(user_id: str, days: int = 30):
    """Get user's API usage statistics."""
    try:
        stats = await get_user_usage_stats(user_id, days)
        return {"status": "success", "usage_stats": stats}
    except Exception as e:
        logger.error(f"Error getting usage stats for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get usage stats: {str(e)}")

# Vision Analysis Endpoints
@app.post("/api/vision/analyze_medical_document", response_model=VisionAnalysisResponse)
async def analyze_medical_document_endpoint(
    user_id: str = Form(...),
    document_type: str = Form("medical_report"),
    additional_context: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    """Analyze medical documents like test results, doctor notes, or medical reports."""
    if not config.ENABLE_VISION_ANALYSIS:
        raise HTTPException(status_code=503, detail="Vision analysis is disabled")
    
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file format
    file_extension = file.filename.split('.')[-1].lower() if file.filename else ""
    if file_extension not in config.SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported image format. Supported formats: {', '.join(config.SUPPORTED_IMAGE_FORMATS)}"
        )
    
    try:
        # Read file data
        file_data = await file.read()
        
        # Check file size
        file_size_mb = len(file_data) / (1024 * 1024)
        if file_size_mb > config.MAX_VISION_FILE_SIZE_MB:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {config.MAX_VISION_FILE_SIZE_MB}MB"
            )
        
        # Track API usage
        await track_api_usage(
            user_id, 
            "vision_analysis", 
            "medical_document", 
            "openai", 
            0, 
            0.0, 
            0, 
            {"document_type": document_type, "file_size_mb": file_size_mb}
        )
        
        # Analyze the document
        analysis_result = await analyze_medical_document_file(
            file_data, 
            file.content_type, 
            document_type, 
            additional_context
        )
        
        return VisionAnalysisResponse(
            success=not analysis_result.get("error", False),
            analysis_type="medical_document",
            results=analysis_result,
            error_message=analysis_result.get("error_message") if analysis_result.get("error") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing medical document for user {user_id}: {e}", exc_info=True)
        return VisionAnalysisResponse(
            success=False,
            analysis_type="medical_document",
            results={},
            error_message=f"Analysis failed: {str(e)}"
        )

@app.post("/api/vision/analyze_prescription", response_model=VisionAnalysisResponse)
async def analyze_prescription_endpoint(
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    """Analyze prescription labels to extract medication information."""
    if not config.ENABLE_VISION_ANALYSIS:
        raise HTTPException(status_code=503, detail="Vision analysis is disabled")
    
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file format
    file_extension = file.filename.split('.')[-1].lower() if file.filename else ""
    if file_extension not in config.SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported image format. Supported formats: {', '.join(config.SUPPORTED_IMAGE_FORMATS)}"
        )
    
    try:
        # Read file data
        file_data = await file.read()
        
        # Check file size
        file_size_mb = len(file_data) / (1024 * 1024)
        if file_size_mb > config.MAX_VISION_FILE_SIZE_MB:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {config.MAX_VISION_FILE_SIZE_MB}MB"
            )
        
        # Track API usage
        await track_api_usage(
            user_id, 
            "vision_analysis", 
            "prescription_label", 
            "openai", 
            0, 
            0.0, 
            0, 
            {"file_size_mb": file_size_mb}
        )
        
        # Analyze the prescription
        analysis_result = await analyze_prescription_label_file(file_data, file.content_type)
        
        return VisionAnalysisResponse(
            success=not analysis_result.get("error", False),
            analysis_type="prescription_label",
            results=analysis_result,
            error_message=analysis_result.get("error_message") if analysis_result.get("error") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing prescription for user {user_id}: {e}", exc_info=True)
        return VisionAnalysisResponse(
            success=False,
            analysis_type="prescription_label",
            results={},
            error_message=f"Analysis failed: {str(e)}"
        )

@app.post("/api/vision/analyze_insurance_card", response_model=VisionAnalysisResponse)
async def analyze_insurance_card_endpoint(
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    """Analyze insurance cards to extract coverage information."""
    if not config.ENABLE_VISION_ANALYSIS:
        raise HTTPException(status_code=503, detail="Vision analysis is disabled")
    
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file format
    file_extension = file.filename.split('.')[-1].lower() if file.filename else ""
    if file_extension not in config.SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported image format. Supported formats: {', '.join(config.SUPPORTED_IMAGE_FORMATS)}"
        )
    
    try:
        # Read file data
        file_data = await file.read()
        
        # Check file size
        file_size_mb = len(file_data) / (1024 * 1024)
        if file_size_mb > config.MAX_VISION_FILE_SIZE_MB:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {config.MAX_VISION_FILE_SIZE_MB}MB"
            )
        
        # Track API usage
        await track_api_usage(
            user_id, 
            "vision_analysis", 
            "insurance_card", 
            "openai", 
            0, 
            0.0, 
            0, 
            {"file_size_mb": file_size_mb}
        )
        
        # Analyze the insurance card
        analysis_result = await analyze_insurance_card_file(file_data, file.content_type)
        
        return VisionAnalysisResponse(
            success=not analysis_result.get("error", False),
            analysis_type="insurance_card",
            results=analysis_result,
            error_message=analysis_result.get("error_message") if analysis_result.get("error") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing insurance card for user {user_id}: {e}", exc_info=True)
        return VisionAnalysisResponse(
            success=False,
            analysis_type="insurance_card",
            results={},
            error_message=f"Analysis failed: {str(e)}"
        )

@app.post("/api/vision/analyze_treatment_form", response_model=VisionAnalysisResponse)
async def analyze_treatment_form_endpoint(
    user_id: str = Form(...),
    form_type: str = Form("intake_form"),
    file: UploadFile = File(...)
):
    """Analyze treatment forms to extract patient information."""
    if not config.ENABLE_VISION_ANALYSIS:
        raise HTTPException(status_code=503, detail="Vision analysis is disabled")
    
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file format
    file_extension = file.filename.split('.')[-1].lower() if file.filename else ""
    if file_extension not in config.SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported image format. Supported formats: {', '.join(config.SUPPORTED_IMAGE_FORMATS)}"
        )
    
    try:
        # Read file data
        file_data = await file.read()
        
        # Check file size
        file_size_mb = len(file_data) / (1024 * 1024)
        if file_size_mb > config.MAX_VISION_FILE_SIZE_MB:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {config.MAX_VISION_FILE_SIZE_MB}MB"
            )
        
        # Track API usage
        await track_api_usage(
            user_id, 
            "vision_analysis", 
            "treatment_form", 
            "openai", 
            0, 
            0.0, 
            0, 
            {"form_type": form_type, "file_size_mb": file_size_mb}
        )
        
        # Analyze the treatment form
        analysis_result = await analyze_treatment_form_file(file_data, file.content_type, form_type)
        
        return VisionAnalysisResponse(
            success=not analysis_result.get("error", False),
            analysis_type="treatment_form",
            results=analysis_result,
            error_message=analysis_result.get("error_message") if analysis_result.get("error") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing treatment form for user {user_id}: {e}", exc_info=True)
        return VisionAnalysisResponse(
            success=False,
            analysis_type="treatment_form",
            results={},
            error_message=f"Analysis failed: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
