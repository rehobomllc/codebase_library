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
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Form, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from arcadepy import AsyncArcade
# OpenAI Agents SDK imports
from agents import Agent, Runner, RunConfig, ItemHelpers, set_default_openai_key, ModelSettings
from agents.result import RunResult, RunResultStreaming # Import specific result types
from agents.handoffs import handoff
from agents.tracing import trace, gen_trace_id
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
    db_manager, fetch_profile, save_profile, save_scholarships, fetch_scholarships,
    save_essays, fetch_essays, save_failed_scrape, save_active_crawl, get_active_crawl,
    update_search_status, get_search_status, init_essay_extraction_progress,
    update_essay_extraction_progress, get_essay_extraction_progress,
    clear_essay_extraction_progress, track_api_usage, get_user_usage_stats,
    search_master_scholarships, get_master_scholarships_stats
)
from debug_utils import tracker, get_debug_dashboard_data, inject_debug_script, debug_endpoint
from tasks import (
    extract_essays_task, extract_essays_immediate_batch,
    extract_single_essay_immediate, extract_all_essays_task,
    extract_essays_task_wrapper, extract_all_essays_task_wrapper
)
from debug_search import SearchDebugger, debug_scholarship_search
from services.billing import verify_subscription, verify_feature_access

from scholarship_agents.triage_agent import create_triage_agent
from scholarship_agents.search_agent import create_search_agent
from scholarship_agents.validation_agent import create_validation_agent
from scholarship_agents.essay_agent import create_essay_agent
from scholarship_agents.form_agent import create_form_agent
from scholarship_agents.reminder_agent import create_reminder_agent
from scholarship_agents.processing_agent import create_processing_agent

from utils.tool_provider import initialize_tool_provider, get_tool_provider, UnifiedToolProvider
from utils.confidence_scorer import ScholarshipConfidenceScorer, UserProfileInput, ScholarshipDataInput, FactorScore

# NEW: Import Arcade Auth Helper
from utils.arcade_auth_helper import run_agent_with_auth_handling, AuthHelperError, check_toolkit_authorization_status

# Import the precision orchestrator
from scholarship_agents.precision_orchestrator import EnhancedPrecisionScholarshipOrchestrator

# SSL Certificate Fix for macOS
import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['CURL_CA_BUNDLE'] = certifi.where()

# Standard imports
import asyncio
import asyncpg
from typing import Optional, Dict, Any, List, AsyncGenerator

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

file_handler = logging.FileHandler(BASE_DIR / "scholarship_app.log")
file_handler.setFormatter(json_formatter)
root_logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(json_formatter)
root_logger.addHandler(stream_handler)

logger = logging.getLogger("scholarship_app")

logging.getLogger("arcadepy").setLevel(logging.WARNING)
logging.getLogger("agents").setLevel(logging.INFO)
logging.getLogger("agents_arcade").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

for _name in ["arcadepy._base_client", "httpcore", "httpcore.connection", "httpcore.http11", "openai._base_client", "asyncio"]:
    logging.getLogger(_name).setLevel(logging.WARNING)

DEFAULT_SCRAPE_SITES = ["https://www.profellow.com", "https://www.appily.com/scholarships", "https://www.niche.com/colleges/scholarships/"]
app = FastAPI(title="Scholarship Finder")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

user_agents: Dict[str, Agent] = {}
conversation_histories: Dict[str, List[Dict[str, Any]]] = {}
user_workflow_traces: Dict[str, Any] = {}
user_trace_identifiers: Dict[str, Dict[str, Any]] = {}

arcade_client_global: Optional[AsyncArcade] = None
_search_agent_global: Optional[Agent] = None
_essay_agent_global: Optional[Agent] = None
_form_agent_global: Optional[Agent] = None
_reminder_agent_global: Optional[Agent] = None
_validation_agent_global: Optional[Agent] = None
_processing_agent_global: Optional[Agent] = None

class ChatRequest(BaseModel): message: str; user_id: str
class ChatResponse(BaseModel): reply: str; crawl_id: Optional[str] = None
class ErrorResponse(BaseModel): error: str
class ScrapeEssayRequest(BaseModel): user_id: str; scholarship_url: str; scholarship_pk: str; scholarship_name: str
class StartEssayDraftRequest(BaseModel): user_id: str; essay_id: str; prompt_text: str; scholarship_name: str; word_limit: Optional[str] = None
class FillFormRequest(BaseModel): user_id: str; scholarship_url: str; scholarship_name: str; form_type: str
class SetReminderRequest(BaseModel): user_id: str; scholarship_name: str; deadline: str; reminder_date: Optional[str] = None
class BulkEssayExtractionRequest(BaseModel): user_id: str

_tool_cache = {}
async def get_cached_tools(toolkits): # Kept for any legacy use, new agents use UnifiedToolProvider
    key = tuple(sorted(toolkits))
    if key not in _tool_cache:
        if not arcade_client_global: raise RuntimeError("Arcade client not initialized for get_cached_tools")
        _tool_cache[key] = await get_arcade_tools(arcade_client_global, toolkits=toolkits)
        logger.info(f"Cached tools (old method) for {toolkits}")
    return _tool_cache[key]

def _parse_deadline_for_scorer(deadline_str: Optional[str]) -> Optional[str]:
    if not deadline_str: return None
    common_formats = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%B %d, %Y"]
    for fmt in common_formats:
        try: dt_obj = datetime.strptime(deadline_str.split("T")[0], fmt.split("T")[0]); return dt_obj.strftime("%Y-%m-%d")
        except ValueError: continue
    try: dt_obj = datetime.fromisoformat(deadline_str.replace('Z', '+00:00')); return dt_obj.strftime("%Y-%m-%d")
    except ValueError: logger.warning(f"Could not parse deadline '{deadline_str}' for scorer."); return None

def _create_relevance_indicators(factor_scores: List[FactorScore]) -> List[Dict[str, Any]]:
    indicators = []
    factor_display_map = {
        "gpa": {"label": "GPA", "icon": "🎓"}, "major_field": {"label": "Major/Field", "icon": "🔬"},
        "academic_level": {"label": "Academic Level", "icon": "📚"}, "location": {"label": "Location", "icon": "📍"},
        "demographics": {"label": "Demographics", "icon": "👥"}, "keywords_description": {"label": "Keywords", "icon": "🔑"},
        "application_complexity": {"label": "Complexity", "icon": "🧩"}, "deadline_urgency": {"label": "Deadline", "icon": "📅"},
        "data_quality": {"label": "Info Quality", "icon": "ℹ️"},
    }
    for factor in factor_scores:
        display_info = factor_display_map.get(factor.factor_name, {"label": factor.factor_name.replace("_", " ").title(), "icon": "❓"})
        status = "neutral"
        if factor.is_positive_match and factor.score >= 0.7: status = "matched"
        elif factor.is_positive_match and factor.score >= 0.5: status = "partial-match"
        elif factor.is_concern and factor.score < 0.4: status = "mismatch"
        elif factor.is_concern: status = "potential-issue"
        if status != "neutral" or factor.weight > 0.05:
            indicators.append({"factor": display_info["label"], "status": status, "icon": display_info["icon"], "details": factor.reason, "score_debug": f"{factor.score:.2f} (w: {factor.weight:.2f})"})
    return indicators

async def filter_expired_scholarships(scholarships: List[Dict[str, Any]], user_id: str, auto_refresh: bool = True) -> tuple[List[Dict[str, Any]], bool]:
    """
    Enhanced scholarship deadline filtering with improved date parsing and strict current date checking.
    Only returns scholarships with deadlines on or after the current date.
    """
    if not scholarships: 
        return scholarships, False
    
    current_scholarships = []
    expired_scholarships = []
    parsing_errors = []
    
    # Use actual current date instead of hardcoded future date
    now = datetime.now(timezone.utc)
    logger.info(f"Filtering scholarships with current date set to: {now.strftime('%Y-%m-%d')}")
    
    for scholarship in scholarships:
        deadline_str = scholarship.get("deadline")
        scholarship_title = scholarship.get('title', 'Unknown')
        
        if not deadline_str:
            # No deadline specified - include with warning
            logger.warning(f"No deadline specified for '{scholarship_title}' - including by default")
            current_scholarships.append(scholarship)
            continue
            
        try:
            deadline = None
            
            if isinstance(deadline_str, str):
                # Enhanced date format parsing
                date_formats = [
                    "%Y-%m-%d",                    # 2025-06-15
                    "%Y-%m-%dT%H:%M:%S",          # 2025-06-15T23:59:59
                    "%Y-%m-%dT%H:%M:%S.%f",       # 2025-06-15T23:59:59.000000
                    "%Y-%m-%dT%H:%M:%SZ",         # 2025-06-15T23:59:59Z
                    "%Y-%m-%dT%H:%M:%S.%fZ",      # 2025-06-15T23:59:59.000000Z
                    "%m/%d/%Y",                   # 06/15/2025
                    "%m-%d-%Y",                   # 06-15-2025
                    "%d/%m/%Y",                   # 15/06/2025 (international)
                    "%B %d, %Y",                  # June 15, 2025
                    "%b %d, %Y",                  # Jun 15, 2025
                    "%B %d %Y",                   # June 15 2025
                    "%b %d %Y",                   # Jun 15 2025
                    "%Y/%m/%d",                   # 2025/06/15
                    "%d-%m-%Y",                   # 15-06-2025
                    "%d.%m.%Y",                   # 15.06.2025
                    "%Y.%m.%d",                   # 2025.06.15
                ]
                
                # Clean the deadline string
                deadline_str_clean = deadline_str.strip()
                
                # Try each format
                for fmt in date_formats:
                    try:
                        if "T" in fmt and "T" in deadline_str_clean:
                            deadline = datetime.strptime(deadline_str_clean, fmt)
                        elif "T" not in fmt and "T" in deadline_str_clean:
                            # Extract date part only
                            date_part = deadline_str_clean.split("T")[0]
                            deadline = datetime.strptime(date_part, fmt)
                        else:
                            deadline = datetime.strptime(deadline_str_clean, fmt)
                        
                        # Ensure timezone info
                        if deadline.tzinfo is None:
                            deadline = deadline.replace(tzinfo=timezone.utc)
                        break
                        
                    except ValueError:
                        continue
                
                # If standard parsing failed, try ISO format parsing
                if deadline is None:
                    try:
                        # Handle ISO format with timezone
                        iso_str = deadline_str_clean.replace('Z', '+00:00')
                        deadline = datetime.fromisoformat(iso_str)
                    except ValueError:
                        pass
                
                # If still no deadline parsed, try fuzzy parsing for common formats
                if deadline is None:
                    try:
                        import re
                        # Extract year-month-day pattern
                        date_pattern = r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})'
                        match = re.search(date_pattern, deadline_str_clean)
                        if match:
                            year, month, day = match.groups()
                            deadline = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                    except Exception:
                        pass
                        
            else:
                logger.warning(f"Deadline not string for '{scholarship_title}': {type(deadline_str)}")
                current_scholarships.append(scholarship)
                continue
            
            # If we still couldn't parse the deadline
            if deadline is None:
                error_msg = f"Excluding '{scholarship_title}' due to unparseable deadline string: '{deadline_str}'"
                logger.warning(error_msg) # Keep as warning as it indicates a data quality issue from source
                parsing_errors.append({"scholarship": scholarship_title, "deadline": deadline_str, "error": "unparseable_and_excluded"})
                # DO NOT add to current_scholarships.
                # Scholarship is now excluded by not being added to current_scholarships.
                continue
            
            # Compare with current date
            if deadline >= now:
                # Deadline is in the future - include
                current_scholarships.append(scholarship)
                logger.debug(f"Including '{scholarship_title}' with deadline: {deadline.strftime('%Y-%m-%d')}")
            else:
                # Deadline has passed - exclude
                expired_scholarships.append(scholarship)
                days_expired = (now - deadline).days
                logger.info(f"Filtering expired '{scholarship_title}' (deadline: {deadline.strftime('%Y-%m-%d')}, expired {days_expired} days ago)")
                
        except Exception as e:
            error_msg = f"Error processing deadline for '{scholarship_title}': {e}"
            logger.warning(error_msg)
            parsing_errors.append({"scholarship": scholarship_title, "deadline": deadline_str, "error": str(e)})
            # Include scholarships with processing errors for manual review
            current_scholarships.append(scholarship)
    
    expired_count = len(expired_scholarships)
    current_count = len(current_scholarships)
    error_count = len(parsing_errors)
    
    # Enhanced logging
    logger.info(f"Deadline filtering results for {user_id}:")
    logger.info(f"  - Current/future scholarships: {current_count}")
    logger.info(f"  - Expired scholarships: {expired_count}")
    logger.info(f"  - Parsing errors: {error_count}")
    
    if parsing_errors:
        logger.warning(f"Date parsing errors encountered: {parsing_errors}")
    
    # Auto-refresh logic - trigger if more than 60% of scholarships are expired
    should_auto_refresh = False
    if expired_count > 0 and auto_refresh:
        total_with_valid_dates = current_count + expired_count
        if total_with_valid_dates > 0:
            expired_percentage = expired_count / total_with_valid_dates
            if expired_percentage > 0.6:  # More than 60% expired
                logger.info(f"Auto-triggering refresh for {user_id} - {expired_count}/{total_with_valid_dates} ({expired_percentage:.1%}) expired")
                asyncio.create_task(auto_refresh_expired_scholarships(user_id, expired_scholarships, current_scholarships))
                should_auto_refresh = True
    
    return current_scholarships, should_auto_refresh

async def check_link_validity(scholarships: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
    if not scholarships: return scholarships
    logger.info(f"Starting link validity check for {len(scholarships)} scholarships for user {user_id}")
    valid_scholarships = []
    async def check_single_link(scholarship: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = scholarship.get("title", "Untitled Scholarship"); url = scholarship.get("application_url") or scholarship.get("url")
        if not url: logger.warning(f"Scholarship '{title}' has no URL"); return None
        try: parsed = urlparse(url); assert parsed.scheme and parsed.netloc
        except Exception as e: logger.warning(f"Scholarship '{title}' URL parsing failed: {url}, error: {e}"); return None
        scholarship_with_status = scholarship.copy(); scholarship_with_status['link_status'] = 'checking'
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            try:
                response = await client.head(url)
                if 200 <= response.status_code < 400: scholarship_with_status['link_status'] = 'valid'; return scholarship_with_status
                response = await client.get(url)
                if 200 <= response.status_code < 400: scholarship_with_status['link_status'] = 'valid'; return scholarship_with_status
                scholarship_with_status['link_status'] = 'invalid'; return scholarship_with_status
            except httpx.RequestError as e: logger.warning(f"Link check HTTP error for '{title}': {e}"); scholarship_with_status['link_status'] = 'error'; return scholarship_with_status
            except Exception as e: logger.warning(f"Generic link check error for '{title}': {e}"); scholarship_with_status['link_status'] = 'error'; return scholarship_with_status
    results = await asyncio.gather(*[check_single_link(s) for s in scholarships], return_exceptions=True)
    for result in results:
        if result is not None and not isinstance(result, Exception) and result.get('link_status') == 'valid': valid_scholarships.append(result)
        elif isinstance(result, Exception): logger.error(f"Link check gather exception: {result}")
    logger.info(f"Link validity check for {user_id}: {len(valid_scholarships)} valid links, {len(scholarships) - len(valid_scholarships)} issues.")
    return valid_scholarships

async def recover_invalid_links(user_id: str, rejected_scholarships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rejected_scholarships or not arcade_client_global: return []
    recovered_scholarships = []
    async def recover_single_scholarship(scholarship: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = scholarship.get("title", "").strip(); provider = (scholarship.get("provider", scholarship.get("organization", "")) or "").strip()
        if not title: return None
        search_queries = []
        if provider: search_queries.extend([f'"{title}" scholarship site:{provider.lower().replace(" ", "")}.com', f'"{title}" scholarship "{provider}"'])
        search_queries.extend([f'"{title}" scholarship application', f'{title} scholarship'])
        for query_idx, search_query in enumerate(search_queries):
            try:
                search_results = await arcade_client_global.tools.execute(tool_name="GoogleScholarshipSearchTool", input={"query": search_query, "num_results": 3}, user_id=user_id)
                if not search_results or not isinstance(search_results, dict) or not search_results.get("results"): continue
                for cand_idx, candidate in enumerate(search_results["results"]):
                    if not isinstance(candidate, dict): continue
                    candidate_url = candidate.get("url", candidate.get("link", ""));
                    if not candidate_url: continue
                    try:
                        page_summary = await arcade_client_global.tools.execute(tool_name="Web.GetPageSummary", input={"url": candidate_url}, user_id=user_id)
                        if not page_summary or not isinstance(page_summary, dict): continue
                        page_content = page_summary.get("summary", "").lower(); page_title_text = page_summary.get("title", "").lower()
                        title_words = set(title.lower().split()); provider_words = set(provider.lower().split()) if provider else set()
                        relevance_score = sum(1 for word in title_words if word in page_content or word in page_title_text) / len(title_words) * 40 if title_words else 0
                        if provider_words: relevance_score += sum(1 for word in provider_words if word in page_content) / len(provider_words) * 20
                        scholarship_terms = ["scholarship", "apply", "application", "eligibility", "deadline", "award"]
                        relevance_score += min(sum(1 for term in scholarship_terms if term in page_content) * 5, 25)
                        application_terms = ["submit", "form", "requirements", "criteria", "graduate", "student"]
                        relevance_score += min(sum(1 for term in application_terms if term in page_content) * 3, 15)
                        if relevance_score >= 60:
                            recovered_scholarship = scholarship.copy()
                            recovered_scholarship.update({"url": candidate_url, "application_url": candidate_url, "source_verified_by": "fallback_agent", "recovery_query": search_query, "recovery_score": relevance_score, "original_url": scholarship.get("url", "N/A")})
                            logger.info(f"Successfully recovered URL for '{title}': {candidate_url} (score: {relevance_score:.1f})"); return recovered_scholarship
                    except Exception: continue # Inner loop error
            except Exception: continue # Outer loop error
        return None
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_VALIDATIONS)
    async def bounded_recovery(s):
        async with semaphore:
            return await recover_single_scholarship(s)
    try:
        recovery_results = await asyncio.gather(*[bounded_recovery(s) for s in rejected_scholarships], return_exceptions=True)
        for result in recovery_results:
            if result is not None and not isinstance(result, Exception): recovered_scholarships.append(result)
            elif isinstance(result, Exception): logger.error(f"Recovery exception: {result}")
    except Exception as e: logger.error(f"Error in parallel scholarship recovery for {user_id}: {e}"); return []
    logger.info(f"Link recovery for {user_id}: {len(recovered_scholarships)}/{len(rejected_scholarships)} recovered.")
    return recovered_scholarships
    
async def get_or_create_agent(user_id: str) -> Agent:
    global _search_agent_global, _essay_agent_global, _form_agent_global, _reminder_agent_global, _validation_agent_global, _processing_agent_global, arcade_client_global
    if user_id in user_agents: return user_agents[user_id]
    if not arcade_client_global: raise RuntimeError("Arcade client not initialized.")
    tool_provider = get_tool_provider();
    if not tool_provider: raise RuntimeError("UnifiedToolProvider not initialized.")
    agent_tool_getter = tool_provider.create_tool_getter()
    if _search_agent_global is None: _search_agent_global = await create_search_agent(arcade_client_global, agent_tool_getter)
    if _essay_agent_global is None: _essay_agent_global = await create_essay_agent(arcade_client_global, agent_tool_getter)
    if _form_agent_global is None: _form_agent_global = await create_form_agent(arcade_client_global, agent_tool_getter)
    if _reminder_agent_global is None: _reminder_agent_global = await create_reminder_agent(arcade_client_global, agent_tool_getter)
    if _validation_agent_global is None: _validation_agent_global = await create_validation_agent(arcade_client_global, agent_tool_getter)
    if _processing_agent_global is None: _processing_agent_global = await create_processing_agent(arcade_client_global, agent_tool_getter)
    if not all([_search_agent_global, _essay_agent_global, _form_agent_global, _reminder_agent_global, _validation_agent_global, _processing_agent_global]):
        raise RuntimeError("One or more specialized global agents failed to initialize.")
    handoffs_list = [
        handoff(agent=_search_agent_global, tool_name_override="SearchScholarships", tool_description_override="Finds relevant scholarship opportunities."),
        handoff(agent=_form_agent_global, tool_name_override="FillApplicationForm", tool_description_override="Assists in locating and filling out scholarship application forms."),
        handoff(agent=_essay_agent_global, tool_name_override="DraftScholarshipEssay", tool_description_override="Helps draft, refine, or adapt scholarship essays."),
        handoff(agent=_reminder_agent_global, tool_name_override="SetScholarshipReminder", tool_description_override="Manages scholarship deadlines and reminders.")
    ]
    triage_agent_instance = await create_triage_agent(arcade_client_global, handoff_actions=handoffs_list)
    user_agents[user_id] = triage_agent_instance; conversation_histories[user_id] = []
    logger.info(f"TriageAgent created for user {user_id} with {len(handoffs_list)} handoffs.")
    return triage_agent_instance

async def _extract_text_from_streamed_result(result_stream: RunResultStreaming) -> Optional[str]:
    final_message_content: Optional[str] = None
    async for event in result_stream.stream_events():
        if event.type == "run_item_stream_event" and event.item.type == "message_output_item":
            final_message_content = ItemHelpers.text_message_output(event.item)
    if final_message_content is None and result_stream.final_output is not None:
        final_message_content = str(result_stream.final_output)
    return final_message_content

@app.on_event("startup")
async def startup_event():
    global arcade_client_global
    logger.info("Application startup sequence initiated...")
    
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
    
    if config.OPENAI_API_KEY: set_default_openai_key(config.OPENAI_API_KEY); logger.info("Default OpenAI API key set.")
    else: logger.warning("OPENAI_API_KEY not found.")
    if config.ARCADE_API_KEY:
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            custom_http_client = httpx.AsyncClient(verify=ssl_context, timeout=30.0)
            arcade_client_global = AsyncArcade(api_key=config.ARCADE_API_KEY, http_client=custom_http_client)
            initialize_tool_provider(arcade_client_global); logger.info("AsyncArcade client and ToolProvider initialized.")
        except Exception as e: logger.error(f"Arcade client/ToolProvider init failed: {e}", exc_info=True); initialize_tool_provider(None)
    else: logger.warning("ARCADE_API_KEY not found."); initialize_tool_provider(None)
    config_errors = config.validate_configuration()
    if config_errors: logger.critical(f"CRITICAL CONFIG ERRORS: {config_errors}")
    else: logger.info("Configuration validated.")
    logger.info("Application startup completed.")

@app.on_event("shutdown")
async def shutdown_event():
    global arcade_client_global
    logger.info("Application shutting down...")
    
    # Close database pool
    try:
        await db_manager.close_pool()
        logger.info("Database pool closed.")
    except Exception as e:
        logger.error(f"Error closing database pool: {e}", exc_info=True)
    
    if arcade_client_global and hasattr(arcade_client_global, 'close'):
        try: await arcade_client_global.close(); logger.info("AsyncArcade client closed.")
        except Exception as e: logger.error(f"Error closing AsyncArcade client: {e}", exc_info=True)
    logger.info("Application shutdown complete.")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request): return templates.TemplateResponse("onboarding.html", {"request": request})

@app.get("/test_new_profile", response_class=HTMLResponse)
async def test_new_profile(request: Request):
    try:
        with open(BASE_DIR / "test_new_profile.html", "r") as f: content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError: return HTMLResponse(content="<h1>Test file not found</h1><p>Please create test_new_profile.html</p>")

@app.post("/chat", response_model=ChatResponse, responses={
    400: {"model": ErrorResponse},
    401: {"description": "Arcade Tool Authorization Required or Pending", "content": {"application/json": {"example": {"error": "AuthHelperError", "message": "Please authorize via URL.", "authorization_url": "...", "auth_id_for_wait": "..."}}}},
    500: {"model": ErrorResponse}
})
async def chat(chat_request: ChatRequest):
    user_message = chat_request.message; user_id = chat_request.user_id
    await track_api_usage(user_id, "chat", "user_interaction", "openai", 0, 0.0, 0, {"message_length": len(user_message)})
    if not user_message or not user_id: raise HTTPException(status_code=400, detail="Message or User ID missing")
    
    workflow_trace = user_workflow_traces.get(user_id)
    if not workflow_trace:
        trace_id_val = gen_trace_id(); workflow_trace = trace("ScholarshipChatFlow", trace_id=trace_id_val, group_id=user_id); user_workflow_traces[user_id] = workflow_trace
        if user_id not in user_trace_identifiers: user_trace_identifiers[user_id] = {"group_id": user_id, "session_trace_ids": []}
        user_trace_identifiers[user_id]["session_trace_ids"].append(trace_id_val)
    workflow_trace.start(mark_as_current=True)

    try:
        agent = await get_or_create_agent(user_id)
        current_conversation_history = conversation_histories.get(user_id, [])
        current_conversation_history.append({"role": "user", "content": user_message})
        
        run_config_for_chat = RunConfig(workflow_name="ScholarshipChatFlow", group_id=user_id, trace_metadata={"request_id": str(id(chat_request)), "interaction_type": "chat_message"}, trace_include_sensitive_data=config.TRACE_API_CALLS)
        
        logger.info(f"Starting agent run (chat) for user {user_id} via auth helper.")
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
            agent_reply_text = "I encountered an issue generating a response."
            logger.error(f"Agent run for user {user_id} (chat) resulted in None reply after streaming.")

        extracted_crawl_id = None
        if "CRAWL_STARTED::" in agent_reply_text:
            match = re.search(r"CRAWL_STARTED::([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", agent_reply_text)
            if match: extracted_crawl_id = match.group(1); await save_active_crawl(user_id, extracted_crawl_id)
        
        return ChatResponse(reply=agent_reply_text, crawl_id=extracted_crawl_id)
            
    except AuthHelperError as ahe:
        logger.warning(f"AuthHelperError for user {user_id} during chat: {ahe.message}, Auth URL: {ahe.auth_url}, Requires Action: {ahe.requires_user_action}")
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={"error": "AuthorizationRequired", "message": ahe.message, "authorization_url": ahe.auth_url, "auth_id_for_wait": ahe.auth_id_for_wait})
        else: 
            raise HTTPException(status_code=500, detail=f"Arcade tool authorization process failed: {ahe.message}")
    except ToolError as te: 
        logger.error(f"Tool execution error for user {user_id} (chat): {te.message}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A tool used by the agent encountered an error: {te.message}")
    except Exception as e:
        logger.error(f"Unexpected error during chat processing for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        if workflow_trace: workflow_trace.finish(reset_current=True)

REDIS_URL = config.REDIS_URL
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
celery_app = Celery("scholarship_tasks", broker=REDIS_URL, backend=REDIS_URL)
@celery_app.task(name="monitor_and_process_crawl")
def monitor_and_process_crawl(user_id: str, crawl_id: str):
    import asyncio, json, os as celery_os, redis as sync_redis; from arcadepy import AsyncArcade as CeleryAsyncArcade
    redis_sync_client = sync_redis.from_url(celery_os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    async def _inner_monitor():
        arcade_api_key_for_celery = celery_os.getenv("ARCADE_API_KEY")
        if not arcade_api_key_for_celery: logger.error(f"[CeleryTask] ARCADE_API_KEY not found for crawl {crawl_id}"); redis_sync_client.publish(f"crawl_updates:{crawl_id}", json.dumps({"status": "FAILED", "error": "Celery misconfiguration"})); return
        celery_arcade_cli = CeleryAsyncArcade(api_key=arcade_api_key_for_celery)
        status = "PENDING"
        try:
            while status not in ("COMPLETED", "FAILED", "CANCELLED", "ERROR"):
                stat = await celery_arcade_cli.tools.execute("Web.GetCrawlStatus", {"crawl_id": crawl_id}, user_id=user_id)
                redis_sync_client.publish(f"crawl_updates:{crawl_id}", json.dumps(stat)); status = stat.get("status", "").upper(); await asyncio.sleep(5)
            if status == "COMPLETED": data = await celery_arcade_cli.tools.execute("Web.GetCrawlData", {"crawl_id": crawl_id}, user_id=user_id); redis_sync_client.set(f"crawl_data:{crawl_id}", json.dumps(data)); redis_sync_client.publish(f"crawl_updates:{crawl_id}", json.dumps({"status": "DATA_READY"}))
        except Exception as e_celery: logger.error(f"[CeleryTask] Error monitoring crawl {crawl_id} for user {user_id}: {e_celery}", exc_info=True); redis_sync_client.publish(f"crawl_updates:{crawl_id}", json.dumps({"status": "ERROR", "message": str(e_celery)}))
        finally:
            if celery_arcade_cli: await celery_arcade_cli.close()
    asyncio.run(_inner_monitor())

async def stream_crawl_status(user_id: str, crawl_id: str) -> AsyncGenerator[str, None]:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"crawl_updates:{crawl_id}")
    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message": continue
            yield f"data: {msg['data']}\\n\\n"
            try:
                if json.loads(msg["data"]).get("status", "").upper() in ("DATA_READY", "FAILED", "CANCELLED", "ERROR", "TERMINATED"): break
            except Exception: pass
    finally: await pubsub.unsubscribe(f"crawl_updates:{crawl_id}")

@app.get("/crawl_updates")
async def crawl_updates(user_id: str, crawl_id: str):
    if not user_id or not crawl_id: raise HTTPException(status_code=400, detail="user_id and crawl_id are required")
    stored_crawl_id = await get_active_crawl(user_id)
    if stored_crawl_id != crawl_id:
        logger.warning(f"Requested crawl_id {crawl_id} not active for user {user_id}. Current: {stored_crawl_id}")
        async def term_stream(): 
            yield f"data: {json.dumps({'status': 'TERMINATED', 'reason': 'Crawl ID mismatch.'})}\\n\\n"
        return StreamingResponse(term_stream(), media_type='text/event-stream')
    return StreamingResponse(stream_crawl_status(user_id, crawl_id), media_type='text/event-stream')

async def stream_essay_extraction_status(user_id: str) -> AsyncGenerator[str, None]:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"essay_extraction_updates:{user_id}")
    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message": continue
            yield f"data: {msg['data']}\\n\\n"
            try:
                if json.loads(msg["data"]).get("status", "").lower() in ("batch_completed", "terminated", "error"): break
            except Exception: pass
    finally: await pubsub.unsubscribe(f"essay_extraction_updates:{user_id}")

@app.get("/essay_extraction_updates")
async def essay_extraction_updates(user_id: str):
    if not user_id: raise HTTPException(status_code=400, detail="user_id is required")
    logger.info(f"Starting essay extraction SSE stream for user {user_id}")
    return StreamingResponse(stream_essay_extraction_status(user_id), media_type='text/event-stream')

@app.get("/api/essay_extraction_progress")
async def get_essay_extraction_progress_api(user_id: str):
    if not user_id: raise HTTPException(status_code=400, detail="user_id is required")
    progress = await get_essay_extraction_progress(user_id)
    return progress if progress else {"status": "not_started", "message": "No essay extraction in progress"}
    
@app.get("/arcade_logs/{user_id}")
async def get_arcade_logs(user_id: str, limit: int = 10):
    if not arcade_client_global: raise HTTPException(status_code=500, detail="Arcade client not initialized")
    return {"status": "success", "user_id": user_id, "message": "Arcade log retrieval placeholder."}

@app.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request): return templates.TemplateResponse("debug.html", {"request": request})

@app.get("/debug_redirect", response_class=HTMLResponse)
async def debug_redirect_page(request: Request):
    try:
        with open(BASE_DIR / "debug_redirect.html", "r") as f: 
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError: 
        return HTMLResponse(content="<h1>Debug file not found</h1><p>Please create debug_redirect.html</p>")

@app.get("/debug_frontend", response_class=HTMLResponse)
async def debug_frontend(request: Request):
    with open(BASE_DIR / "debug_frontend.html", "r") as f: content = f.read()
    return HTMLResponse(content=content)

@app.get("/check_crawl_status")
async def check_crawl_status(user_id: str, crawl_id: str):
    if not arcade_client_global: raise HTTPException(status_code=500, detail="Arcade client not initialized")
    return {"status": "UNKNOWN", "message": "Crawl status check placeholder."}

@app.post("/cancel_crawl")
async def cancel_crawl(request: Request):
    if not arcade_client_global: raise HTTPException(status_code=500, detail="Arcade client not initialized")
    return {"success": True, "message": "Crawl cancellation placeholder."}

@app.get("/agent_traces/{user_id}")
async def get_agent_traces_info(user_id: str):
    if not arcade_client_global: raise HTTPException(status_code=503, detail="System not fully initialized.")
    return {"status": "success", "user_id": user_id, "message": "Agent trace info placeholder."}

@app.get("/trace_status/{user_id}")
async def get_trace_status(user_id: str):
    if not arcade_client_global: raise HTTPException(status_code=503, detail="System not fully initialized.")
    return {"status": "success", "user_id": user_id, "message": "Trace status placeholder."}

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request): return templates.TemplateResponse("onboarding.html", {"request": request})

@app.post("/onboarding/submit")
async def onboarding_submit(request: Request):
    try:
        payload = await request.json(); user_id = payload.get("google_email") or payload.get("name") or "onboarding_user"
        logger.info(f"Onboarding submit for user_id: {user_id}")
        if not user_id or not user_id.strip(): logger.error(f"User ID is empty or invalid: '{user_id}'"); return JSONResponse(status_code=400, content={"success": False, "error": "User identifier required."})
        await save_profile(user_id, payload)
        return JSONResponse(content={"success": True, "user_id": user_id})
    except Exception as e: logger.error(f"Error during onboarding submit: {e}", exc_info=True); return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/onboarding/colleges")
async def onboarding_colleges(q: str = ""):
    if len(q) < 2: return []
    colleges = ["Stanford University", "Harvard University", "MIT"] # Abridged
    return [college for college in colleges if q.lower() in college.lower()][:10]

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request): # This route doesn't call agents directly needing Arcade auth
    user_id = request.query_params.get("user_id")
    if not user_id: 
        logger.warning("Dashboard accessed without user_id")
        return HTMLResponse("User ID is missing.", status_code=400)
    user = {"name": "Student"}
    profile_data = await fetch_profile(user_id) or {}
    user["name"] = profile_data.get("name", "Student")
    
    # Fetch scholarships from the database
    scholarships_from_db = await fetch_scholarships(user_id)
    
    # Apply the enhanced deadline filtering before rendering
    # Set auto_refresh to True to enable background refresh if many are expired
    scholarships_to_render, _ = await filter_expired_scholarships(scholarships_from_db, user_id, auto_refresh=True)
    
    essays_list = await fetch_essays(user_id)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "user_id": user_id, 
        "scholarships": scholarships_to_render, 
        "essays": essays_list, 
        "calendar_events": [], 
        "google_sheet_url": None, 
        "calendar_url": None, 
        "faq_list": []
    })

@app.post("/start_search")
async def start_search(request: Request):
    user_id = None  # Initialize for error handling
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        # Track API usage (moved inside the main try block after user_id is confirmed)
        if user_id: # Ensure user_id is available before tracking
            await track_api_usage(user_id, "start_search", "search_operation", "openai", 0, 0.0, 0, {"search_type": "scholarship_search"})
        else: 
            # If user_id is still None after trying to get it from JSON, raise error
            raise HTTPException(status_code=400, detail="user_id is required in request payload")
        
        logger.info(f"Starting search for user: {user_id}")
        
        profile = await fetch_profile(user_id)
        if not profile: 
            logger.error(f"No profile found for user: {user_id}")
            raise HTTPException(status_code=404, detail="User profile not found.")
        
        logger.info(f"Profile fetched for user {user_id}: {len(str(profile))} characters")
    
        # Create comprehensive profile data for the search agent (Remains the same)
        user_profile_data = {
            "user_id": user_id,
            "name": profile.get('name', 'N/A'),
            "academic_level": profile.get('academic_level', 'undergraduate'),
            "major": profile.get('major', ''),
            "location": profile.get('location', ''),
            "college": profile.get('college', ''),
            "gpa": profile.get('gpa', ''),
            "demographics": profile.get('demographics', []),
            "interests": profile.get('interests', []),
            "achievements": profile.get('achievements', []),
            "merits": profile.get('merits', []),
            "financial_need": profile.get('financial_need', ''),
            "graduation_year": profile.get('graduation_year', ''),
            "scholarship_types": profile.get('scholarship_types', []),
            "previous_apps": profile.get('previous_apps', [])
        }
        
        # search_prompt_message (Remains the same)
        search_prompt_message = f"""User has requested a scholarship search. Please use the search_master_database tool to find relevant scholarships based on their complete profile.

User Profile Data:
{json.dumps(user_profile_data, indent=2)}

IMPORTANT INSTRUCTIONS:
1. Use the search_master_database tool immediately with the user profile JSON above
2. Return results in JSON format with scholarship_candidates array
3. Do NOT ask for additional information - use the profile data provided
4. Focus on finding scholarships that match their academic level, major, location, and interests
5. Return results in this exact format:
{{
  "search_summary": {{"strategy": "database_search", "profile_used": true}},
  "scholarship_candidates": [array of scholarships found]
}}"""

        tool_provider = get_tool_provider()
        if not tool_provider:
            logger.error("Tool provider not initialized")
            raise HTTPException(status_code=503, detail="Tool provider not initialized")
            
        logger.info(f"Tool provider initialized for user {user_id}")
        
        agent_tool_getter = tool_provider.create_tool_getter()
        # search_agent = await create_search_agent(arcade_client_global, agent_tool_getter) # Not directly used here anymore for precision search

        # logger.info(f"Search agent created for user {user_id}") # Related to above
        
        logger.info(f"Initializing EnhancedPrecisionScholarshipOrchestrator for user {user_id}")
        orchestrator = EnhancedPrecisionScholarshipOrchestrator(
            arcade_client_global,
            agent_tool_getter # Pass the getter from the initialized tool_provider
        )
        
        orchestrator_profile = user_profile_data # Use the already created user_profile_data
        
        logger.info(f"Running enhanced precision search for user {user_id}")
        
        orchestrator_results = await orchestrator.run_enhanced_precision_search(orchestrator_profile)
        
        logger.info(f"Orchestrator completed for user {user_id}. Results type: {type(orchestrator_results)}")
        
        final_scholarships = orchestrator_results.get("final_scholarships", [])
        logger.info(f"Found {len(final_scholarships)} final scholarships for user {user_id}")
        
        if final_scholarships:
            try:
                user_gpa = float(profile.get('gpa')) if profile.get('gpa') else None
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse GPA for user {user_id}: {profile.get('gpa')} - {e}")
                user_gpa = None
            
            logger.info(f"Applying confidence scoring for user {user_id}")
            
            user_profile_for_scorer = UserProfileInput(
                user_id=user_id,
                gpa=user_gpa,
                major=profile.get('major'),
                academic_level=profile.get('academic_level'),
                location_state=profile.get('location_state', profile.get('location', '').split(',')[0].strip() if profile.get('location') else None),
                demographics=profile.get('demographics', []),
                interests_keywords=profile.get('merits', []) + profile.get('interests', []),
                preferred_complexity=profile.get('preferred_complexity', 'medium')
            )
            
            enriched_scholarships = []
            for i, schol_data in enumerate(final_scholarships):
                try:
                    schol_min_gpa = float(schol_data.get('min_gpa')) if schol_data.get('min_gpa') else None
                except (ValueError, TypeError):
                    schol_min_gpa = None
                
                scholarship_input_for_scorer = ScholarshipDataInput(
                    scholarship_id=schol_data.get('id', schol_data.get('url', f'unknown_id_{i}')),
                    name=schol_data.get('title', schol_data.get('name', 'Untitled Scholarship')),
                    min_gpa=schol_min_gpa,
                    eligible_majors=schol_data.get('eligible_majors', []),
                    eligible_academic_levels=schol_data.get('eligible_academic_levels', []),
                    eligible_locations_state=schol_data.get('eligible_locations_state', []),
                    demographic_specific=schol_data.get('demographic_specific', []),
                    keywords=schol_data.get('keywords', []),
                    description=schol_data.get('description', ''),
                    application_complexity_estimate=schol_data.get('application_complexity_estimate', 'medium'),
                    deadline=_parse_deadline_for_scorer(schol_data.get('deadline')),
                    award_amount=schol_data.get('amount', schol_data.get('award_amount')),
                    url=schol_data.get('url')
                )
                
                scorer = ScholarshipConfidenceScorer(user_profile_for_scorer, scholarship_input_for_scorer)
                confidence_analysis = scorer.get_full_confidence_analysis()
                
                schol_data['confidence_score'] = confidence_analysis.confidence_score
                schol_data['summary_explanation'] = confidence_analysis.summary_explanation
                schol_data['matching_criteria_details'] = confidence_analysis.matching_criteria_details
                schol_data['potential_concerns'] = confidence_analysis.potential_concerns
                schol_data['suggested_actions'] = confidence_analysis.suggested_actions
                schol_data['relevance_indicators'] = _create_relevance_indicators(confidence_analysis.raw_match_details.factor_scores)
                
                enriched_scholarships.append(schol_data)
            
            enriched_scholarships.sort(key=lambda s: s.get('confidence_score', 0), reverse=True)
            
            logger.info(f"========= BEFORE EXPIRED FILTER (start_search) User: {user_id}. Count: {len(enriched_scholarships)} =========")
            # Filter all scholarships (including web-sourced) before saving
            logger.info(f"Applying final date filter to {len(enriched_scholarships)} enriched scholarships before saving for user {user_id}")
            enriched_scholarships, _ = await filter_expired_scholarships(enriched_scholarships, user_id, auto_refresh=False)
            logger.info(f"========= AFTER EXPIRED FILTER (start_search) User: {user_id}. Count: {len(enriched_scholarships)} =========")
            logger.info(f"{len(enriched_scholarships)} scholarships remaining after final date filter for user {user_id}")
            
            logger.info(f"Saving {len(enriched_scholarships)} enriched scholarships for user {user_id}")
            
            await save_scholarships(user_id, enriched_scholarships)
            await update_search_status(user_id, "enhanced_precision_search_completed")
            
            pipeline_summary = orchestrator_results.get("pipeline_summary", {})
            performance_metrics = orchestrator_results.get("performance_metrics", {})
            management_infrastructure = orchestrator_results.get("management_infrastructure", {})
            
            total_essays_found = 0
            if orchestrator_results.get("essay_results"):
                essay_reqs = orchestrator_results["essay_results"].get("scholarship_essay_requirements", [])
                for req in essay_reqs:
                    total_essays_found += len(req.get("essay_requirements", []))
            
            logger.info(f"Search completed successfully for user {user_id} with {len(enriched_scholarships)} scholarships")
            
            return JSONResponse(content={
                "status": "success",
                "message": f"Enhanced precision search completed with {len(enriched_scholarships)} scholarships",
                "results": {
                    "final_scholarships_count": len(enriched_scholarships),
                    "scholarships": enriched_scholarships,
                    "essays_extracted": total_essays_found,
                    "pipeline_summary": pipeline_summary,
                    "performance_metrics": performance_metrics,
                    "management_infrastructure": management_infrastructure,
                    "enhanced_features": [
                        "multi_toolkit_validation",
                        "comprehensive_essay_discovery",
                        "form_analysis_and_management",
                        "google_workspace_integration",
                        "portal_deep_analysis"
                    ]
                },
                "orchestrator_results": orchestrator_results
            })
        
        else:
            logger.info(f"No scholarships found for user {user_id}")
            await update_search_status(user_id, "enhanced_precision_search_no_results")
            return JSONResponse(content={
                "status": "no_results",
                "message": "Enhanced precision search found no qualifying scholarships",
                "results": {
                    "final_scholarships_count": 0,
                    "scholarships": [],
                    "pipeline_summary": orchestrator_results.get("pipeline_summary", {}),
                    "performance_metrics": orchestrator_results.get("performance_metrics", {}),
                    "pipeline_errors": orchestrator_results.get("pipeline_errors", [])
                }
            })
    
    except AuthHelperError as ahe:
        logger.warning(f"AuthHelperError for user {user_id} during enhanced precision search: {ahe.message}")
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={
                "error": "AuthorizationRequired", 
                "message": ahe.message, 
                "authorization_url": ahe.auth_url, 
                "auth_id_for_wait": ahe.auth_id_for_wait
            })
        # For non-actionable auth errors, or if URL is missing, raise 500
        raise HTTPException(status_code=500, detail=f"Enhanced precision search failed due to authorization issue: {ahe.message}")
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 400, 404) directly
        raise
        
    except Exception as e:
        logger.error(f"Unexpected error in /start_search for user {user_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        if user_id: # Check if user_id was populated before error
            try:
                await update_search_status(user_id, "search_error", error_message=str(e), error_type=type(e).__name__)
            except Exception as status_error:
                logger.error(f"Failed to update search status for user {user_id} after another error: {status_error}")
        
        error_detail = f"Internal server error during scholarship search: {type(e).__name__}: {str(e)}"
        raise HTTPException(status_code=500, detail=error_detail)

@app.post("/api/set_scholarship_reminder")
async def set_scholarship_reminder(request_data: SetReminderRequest):
    global _reminder_agent_global, arcade_client_global
    user_id = request_data.user_id; scholarship_name = request_data.scholarship_name; deadline = request_data.deadline
    if not all([user_id, scholarship_name, deadline]): raise HTTPException(status_code=400, detail="Missing required fields")
    reminder_date_final = request_data.reminder_date 
    if not reminder_date_final: 
        try: deadline_dt_rem = datetime.fromisoformat(deadline.replace('Z','+00:00')); reminder_date_final = (deadline_dt_rem - timedelta(days=3)).isoformat()
        except: reminder_date_final = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat() 

    user_profile_rem = await fetch_profile(user_id)
    if not user_profile_rem: raise HTTPException(status_code=404, detail="User profile not found")

    if not _reminder_agent_global:
        tool_provider_rem = get_tool_provider(); assert tool_provider_rem, "Tool provider missing for ReminderAgent"
        _reminder_agent_global = await create_reminder_agent(arcade_client_global, tool_provider_rem.create_tool_getter())
        assert _reminder_agent_global, "Failed to init ReminderAgent"
    
    user_context_rem = f"User: {user_profile_rem.get('name', 'N/A')}. Task: Set reminder for scholarship '{scholarship_name}', deadline: {deadline}, reminder date: {reminder_date_final}."
    messages_rem = [{"role": "user", "content": user_context_rem}]
    run_config_rem = RunConfig(workflow_name="DirectReminderSettingWorkflow", group_id=user_id, trace_include_sensitive_data=config.TRACE_API_CALLS)

    try:
        logger.info(f"Invoking ReminderAgent for user {user_id} via auth helper.")
        agent_run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, 
            starting_agent=_reminder_agent_global,
            input_data=messages_rem,
            user_id=user_id,
            arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config_rem, "context": {"user_id": user_id}}
        )
        response_content_rem = str(agent_run_result.final_output) if agent_run_result and agent_run_result.final_output else "Reminder agent did not return a response."
        return {"status": "success", "message": f"Reminder set for {scholarship_name}", "response": response_content_rem}
        
    except AuthHelperError as ahe:
        logger.warning(f"AuthHelperError for ReminderAgent, user {user_id}: {ahe.message}")
        if ahe.requires_user_action and ahe.auth_url:
            return JSONResponse(status_code=401, content={"error": "AuthorizationRequired", "message": ahe.message, "authorization_url": ahe.auth_url, "auth_id_for_wait": ahe.auth_id_for_wait, "tool_name": "Google Calendar/Gmail"})
        raise HTTPException(status_code=500, detail=f"Reminder setting failed due to authorization issue: {ahe.message}")
    except Exception as e_rem:
        logger.error(f"Error setting scholarship reminder: {e_rem}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set scholarship reminder: {str(e_rem)}")

@app.get("/api/check_auth_status/{toolkit_name}") # NEW Endpoint
async def api_check_toolkit_authorization_status(request: Request, toolkit_name: str, user_id: str = Query(...)):
    if not user_id: raise HTTPException(status_code=400, detail="user_id is required.")
    if not arcade_client_global: raise HTTPException(status_code=503, detail="Arcade client not initialized.")
    
    tool_provider = get_tool_provider()
    if not tool_provider: raise HTTPException(status_code=503, detail="Tool provider not initialized.")

    try:
        test_tools = await tool_provider.create_tool_getter()([toolkit_name])
        if not test_tools:
            raise HTTPException(status_code=404, detail=f"No tools found for toolkit '{toolkit_name}' or toolkit unknown.")
        test_agent = Agent(name=f"{toolkit_name.capitalize()}AuthTestAgent",instructions=f"Briefly use a {toolkit_name} tool.",model=config.DEFAULT_AGENT_MODEL,tools=test_tools,model_settings=ModelSettings(temperature=0.1))
        
        test_input_for_toolkit = f"Perform a simple test action using a {toolkit_name} tool."
        if toolkit_name.lower() == "google": test_input_for_toolkit = "List one file name from my Google Drive."
        elif toolkit_name.lower() == "github": test_input_for_toolkit = "List one of my GitHub repositories."
        is_authorized, message_or_auth_url = await check_toolkit_authorization_status(arcade_client=arcade_client_global,user_id=user_id,toolkit_name=toolkit_name,test_agent=test_agent,test_input=test_input_for_toolkit)
        
        if is_authorized:
            return {"status": "authorized", "toolkit": toolkit_name, "message": message_or_auth_url}
        else:
            if message_or_auth_url and message_or_auth_url.startswith("http"):
                 return JSONResponse(status_code=401, content={"status": "authorization_required", "toolkit": toolkit_name, "authorization_url": message_or_auth_url, "message": f"User needs to authorize the '{toolkit_name}' toolkit."})
            else: 
                return JSONResponse(status_code=500, content={"status": "error", "toolkit": toolkit_name, "message": message_or_auth_url or f"Could not determine authorization status for {toolkit_name}."})
    except Exception as e:
        logger.error(f"Error in /api/check_auth_status for toolkit '{toolkit_name}', user '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check authorization status for '{toolkit_name}': {str(e)}")

async def invoke_scholarship_processing_agent(user_id: str, raw_data: list, arcade_client: AsyncArcade, user_profile: Optional[Dict] = None):
    global _processing_agent_global 
    if not _processing_agent_global: 
        tool_provider = get_tool_provider(); assert tool_provider
        _processing_agent_global = await create_processing_agent(arcade_client, tool_provider.create_tool_getter())
    prompt = "Process raw scholarship data..." # Abridged
    messages = [{"role": "user", "content": prompt}]
    run_cfg = RunConfig(workflow_name="ScholarshipDataProcessingFlow_Invoke", group_id=user_id)
    try:
        run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, starting_agent=_processing_agent_global, input_data=messages,
            user_id=user_id, arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_cfg, "context": {"user_id": user_id}}
        )
        if run_result and run_result.final_output: 
            try: parsed = json.loads(str(run_result.final_output)); return parsed if isinstance(parsed, list) else []
            except: return []
        return []
    except AuthHelperError as ahe: logger.error(f"AuthHelperError in invoke_scholarship_processing_agent for user {user_id}: {ahe.message}"); return [] 
    except Exception as e: logger.error(f"Error in invoke_scholarship_processing_agent for user {user_id}: {e}", exc_info=True); return []

async def invoke_scholarship_validation_agent(user_id: str, scholarship_candidates: dict, arcade_client: AsyncArcade):
    global _validation_agent_global 
    if not _validation_agent_global: 
        tool_provider = get_tool_provider(); assert tool_provider
        _validation_agent_global = await create_validation_agent(arcade_client, tool_provider.create_tool_getter())
    prompt = "Validate scholarship opportunities..." # Abridged
    messages = [{"role": "user", "content": prompt}]
    run_cfg = RunConfig(workflow_name="ScholarshipValidationFlow_Invoke", group_id=user_id)
    empty_res = {"validated_scholarships": [], "rejected_scholarships": [], "validation_summary": {}}
    try:
        run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, starting_agent=_validation_agent_global, input_data=messages,
            user_id=user_id, arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_cfg, "context": {"user_id": user_id}}
        )
        if run_result and run_result.final_output: 
            try: parsed = json.loads(str(run_result.final_output)); return parsed if isinstance(parsed, dict) else empty_res
            except: return empty_res
        return empty_res
    except AuthHelperError as ahe: logger.error(f"AuthHelperError in invoke_scholarship_validation_agent for user {user_id}: {ahe.message}"); return empty_res
    except Exception as e: logger.error(f"Error in invoke_scholarship_validation_agent for user {user_id}: {e}", exc_info=True); return empty_res

async def auto_refresh_expired_scholarships(user_id: str, expired_scholarships_input: List[Dict[str, Any]], current_scholarships_input: List[Dict[str, Any]]):
    try:
        logger.info(f"Starting auto refresh for user {user_id} with {len(expired_scholarships_input)} expired scholarships")
        profile_auto = await fetch_profile(user_id)
        if not profile_auto: logger.error(f"Cannot auto-refresh for user {user_id}: profile not found"); return
        prompt_auto = "AUTOMATIC REFRESH: Find NEW, CURRENT scholarships..." # Abridged
        await update_search_status(user_id, "auto_refreshing")
        agent_auto = await get_or_create_agent(user_id)
        messages_auto = [{"role": "user", "content": prompt_auto}]
        run_config_auto = RunConfig(workflow_name="AutoRefreshFlow", group_id=user_id, trace_metadata={"trigger": "auto_refresh_task", "expired_count": len(expired_scholarships_input)}, trace_include_sensitive_data=config.TRACE_API_CALLS)
        
        result_stream: RunResultStreaming = await run_agent_with_auth_handling(
            runner_callable=Runner.run_streamed, starting_agent=agent_auto, input_data=messages_auto,
            user_id=user_id, arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config_auto, "context": {"user_id": user_id}}
        )
        reply_auto = await _extract_text_from_streamed_result(result_stream)
        logger.info(f"Auto-refresh agent interaction completed for user {user_id}. Reply: {reply_auto[:100] if reply_auto else 'No reply'}")
        new_scholarships_count = 0 
        await update_search_status(user_id, "auto_refresh_completed", new_scholarships_found=new_scholarships_count, essays_extracted=0)
    except AuthHelperError as e_auth_auto: logger.warning(f"Auth error (auto-refresh) for user {user_id}: {e_auth_auto.auth_url}"); await update_search_status(user_id, "auto_refresh_auth_required")
    except Exception as e_auto_outer: logger.error(f"Error in auto-refresh for user {user_id}: {e_auto_outer}", exc_info=True); await update_search_status(user_id, "auto_refresh_failed")

async def update_search_status(user_id: str, status: str, **kwargs):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import update_search_status as db_update_search_status
    return await db_update_search_status(pool, user_id, status, **kwargs)

async def get_search_status(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import get_search_status as db_get_search_status
    return await db_get_search_status(pool, user_id)

async def init_essay_extraction_progress(user_id: str, total_scholarships: int):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import init_essay_extraction_progress as db_init_essay_extraction_progress
    return await db_init_essay_extraction_progress(pool, user_id, total_scholarships)

async def update_essay_extraction_progress(user_id: str, scholarship_pk: str, status: str, **kwargs):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import update_essay_extraction_progress as db_update_essay_extraction_progress
    return await db_update_essay_extraction_progress(pool, user_id, scholarship_pk, status, **kwargs)

async def get_essay_extraction_progress(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import get_essay_extraction_progress as db_get_essay_extraction_progress
    return await db_get_essay_extraction_progress(pool, user_id)

async def clear_essay_extraction_progress(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import clear_essay_extraction_progress as db_clear_essay_extraction_progress
    return await db_clear_essay_extraction_progress(pool, user_id)

async def track_api_usage(user_id: str, tool_name: str, operation_type: str, api_provider: str, tokens_used: int = 0, estimated_cost: float = 0.0, pages_scraped: int = 0, metadata: dict = None):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import track_api_usage as db_track_api_usage
    return await db_track_api_usage(pool, user_id, tool_name, operation_type, api_provider, tokens_used, estimated_cost, pages_scraped, metadata)

async def get_user_usage_stats(user_id: str, days: int = 30):
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized")
    from services.database import get_user_usage_stats as db_get_user_usage_stats
    return await db_get_user_usage_stats(pool, user_id, days)

@app.post("/api/scrape_single_scholarship_essays")
async def scrape_single_scholarship_essays(request_data: ScrapeEssayRequest):
    logger.info(f"Received request to scrape essays for scholarship_pk: {request_data.scholarship_pk} for user: {request_data.user_id}")
    await track_api_usage(request_data.user_id, "scrape_essays", "essay_extraction", "openai", 0, 0.0, 1, {"scholarship_pk": request_data.scholarship_pk})
    session_id_val = f"essay_extraction_{request_data.user_id}_{int(datetime.now().timestamp())}"
    asyncio.create_task(extract_single_essay_immediate(user_id=request_data.user_id, scholarship_url=request_data.scholarship_url, scholarship_pk=request_data.scholarship_pk, scholarship_name=request_data.scholarship_name, session_id=session_id_val))
    return {"status": "success", "message": f"Essay extraction started for \"{request_data.scholarship_name}\"", "session_id": session_id_val }

@app.post("/api/scrape_all_essays")
async def scrape_all_essays(request_data: BulkEssayExtractionRequest):
    logger.info(f"Received request to extract essays from all scholarships for user: {request_data.user_id}")
    timeline_session_id_bulk = f"bulk_essay_extraction_{request_data.user_id}_{int(datetime.now().timestamp())}"
    asyncio.create_task(extract_all_essays_task_wrapper(user_id=request_data.user_id, timeline_session_id=timeline_session_id_bulk))
    return {"status": "success", "message": f"Bulk essay extraction started", "session_id": timeline_session_id_bulk}

@app.post("/api/start_essay_draft")
async def start_essay_draft_endpoint(request_data: StartEssayDraftRequest):
    global _essay_agent_global, arcade_client_global
    user_id = request_data.user_id; scholarship_name = request_data.scholarship_name; prompt = request_data.prompt_text
    if not all([user_id, scholarship_name, prompt]): raise HTTPException(status_code=400, detail="Missing required fields for essay draft.")
    if not _essay_agent_global:
        tool_provider = get_tool_provider(); assert tool_provider
        _essay_agent_global = await create_essay_agent(arcade_client_global, tool_provider.create_tool_getter())
    
    user_profile_essay = await fetch_profile(user_id)
    profile_summary = f"User: {user_profile_essay.get('name', 'Student')}. Interests: {', '.join(user_profile_essay.get('interests',[]))[:100]}..." if user_profile_essay else "User profile not available."
    
    draft_prompt = (f"User '{user_id}' wants to draft an essay for scholarship '{scholarship_name}'.\n"
                    f"Prompt: \"{prompt}\"\n"
                    f"Word Limit: {request_data.word_limit or 'Not specified'}\n"
                    f"User Profile Summary: {profile_summary}\n"
                    f"Please draft a compelling essay and save it to a new Google Document using available tools. Provide the link to the document.")
    messages_draft = [{"role": "user", "content": draft_prompt}]
    run_config_draft = RunConfig(workflow_name="EssayDraftingFlow", group_id=user_id)
    try:
        run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, starting_agent=_essay_agent_global, input_data=messages_draft,
            user_id=user_id, arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config_draft, "context": {"user_id": user_id}}
        )
        agent_reply = str(run_result.final_output) if run_result and run_result.final_output else "Essay agent did not return a response."
        doc_link_match = re.search(r"(https://docs\.google\.com/document/d/[a-zA-Z0-9_-]+(?:/edit)?)", agent_reply)
        doc_link = doc_link_match.group(0) if doc_link_match else None
        return {"status": "success", "message": agent_reply, "document_link": doc_link}
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url: return JSONResponse(status_code=401, content={"error": "AuthorizationRequired", "message": ahe.message, "authorization_url": ahe.auth_url})
        raise HTTPException(status_code=500, detail=f"Essay drafting auth failed: {ahe.message}")
    except Exception as e: raise HTTPException(status_code=500, detail=f"Failed to start essay draft: {str(e)}")

@app.post("/api/fill_scholarship_form")
async def fill_scholarship_form_endpoint(request_data: FillFormRequest):
    global _form_agent_global, arcade_client_global
    user_id = request_data.user_id; scholarship_url = request_data.scholarship_url; scholarship_name = request_data.scholarship_name
    if not all([user_id, scholarship_url, scholarship_name]): raise HTTPException(status_code=400, detail="Missing required fields for form filling.")
    if not _form_agent_global:
        tool_provider = get_tool_provider(); assert tool_provider
        _form_agent_global = await create_form_agent(arcade_client_global, tool_provider.create_tool_getter())

    user_profile_form = await fetch_profile(user_id)
    profile_summary_form = f"User Profile: Name: {user_profile_form.get('name', 'Student')}, Email: {user_id}, Major: {user_profile_form.get('major', 'N/A')}..." if user_profile_form else "User profile not available."
    
    form_fill_prompt = (f"User '{user_id}' needs help with the scholarship form for '{scholarship_name}' at URL: {scholarship_url}.\n"
                        f"Form Type: {request_data.form_type}.\n"
                        f"User Profile Summary: {profile_summary_form}\n"
                        f"Please guide the user through discovering, processing, and filling this form. If it's a PDF, aim to convert/use Google Docs. For web forms, interact directly. Use profile data where appropriate. DO NOT SUBMIT.")
    messages_form = [{"role": "user", "content": form_fill_prompt}]
    run_config_form = RunConfig(workflow_name="FormFillingFlow", group_id=user_id)
    try:
        run_result: RunResult = await run_agent_with_auth_handling(
            runner_callable=Runner.run, starting_agent=_form_agent_global, input_data=messages_form,
            user_id=user_id, arcade_client=arcade_client_global,
            run_config_kwargs={"run_config": run_config_form, "context": {"user_id": user_id}}
        )
        agent_reply = str(run_result.final_output) if run_result and run_result.final_output else "Form agent did not provide a response."
        doc_link_match = re.search(r"(https://docs\.google\.com/document/d/[a-zA-Z0-9_-]+(?:/edit)?)", agent_reply)
        doc_link = doc_link_match.group(0) if doc_link_match else None
        return {"status": "success", "message": agent_reply, "document_link": doc_link}
    except AuthHelperError as ahe:
        if ahe.requires_user_action and ahe.auth_url: return JSONResponse(status_code=401, content={"error": "AuthorizationRequired", "message": ahe.message, "authorization_url": ahe.auth_url})
        raise HTTPException(status_code=500, detail=f"Form filling auth failed: {ahe.message}")
    except Exception as e: raise HTTPException(status_code=500, detail=f"Failed to start form filling: {str(e)}")

@app.get("/api/scholarships")
async def get_scholarships_data(user_id: str, request: Request, include_expired: bool = False):
    """
    Get scholarships for a user with enhanced deadline filtering.
    By default, only returns scholarships with current/future deadlines.
    """
    profile = await fetch_profile(user_id)
    if not profile: 
        raise HTTPException(status_code=404, detail="User profile not found")
    
    status_val = await get_search_status(user_id)
    scholarships = await fetch_scholarships(user_id)
    
    total_count = len(scholarships) if scholarships else 0
    logger.info(f"Retrieved {total_count} total scholarships for user {user_id}")
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    if scholarships:
        if not include_expired:
            # Apply enhanced deadline filtering - only show current/future opportunities
            scholarships, auto_refresh_triggered = await filter_expired_scholarships(scholarships, user_id, auto_refresh=True)
            filtered_count = len(scholarships)
            expired_count = total_count - filtered_count
            
            logger.info(f"Deadline filtering for {user_id}: {filtered_count} current, {expired_count} expired/filtered")
            
            if auto_refresh_triggered:
                logger.info(f"Auto-refresh triggered for {user_id} due to high number of expired scholarships")
        else:
            logger.info(f"Including expired scholarships for user {user_id} (include_expired=True)")
    
    return {
        "status": status_val, 
        "scholarships": scholarships or [],
        "metadata": {
            "total_scholarships": total_count,
            "current_scholarships": len(scholarships) if scholarships else 0,
            "expired_filtered": total_count - (len(scholarships) if scholarships else 0) if not include_expired else 0,
            "include_expired": include_expired,
            "filter_date": current_date  # Use actual current date
        }
    }

@app.get("/api/essays")
async def get_essays(user_id: str):
    essays_list = await fetch_essays(user_id)
    return {"essays": essays_list or []}

@app.get("/api/profile/{user_id}")
async def get_user_profile(user_id: str):
    profile_val = await fetch_profile(user_id)
    return {"profile": profile_val, "exists": bool(profile_val)}

@app.post("/api/refresh_expired_scholarships")
async def refresh_expired_scholarships(request: Request):
    """
    Refresh scholarships for a user, triggering a new search focused on current opportunities.
    This will search specifically for scholarships with deadlines on or after the current date.
    """
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id: 
        raise HTTPException(status_code=400, detail="user_id is required")
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Refreshing scholarships for user {user_id} with current date filtering (>= {current_date})")
    
    # Update search status to indicate refresh with date filtering
    await update_search_status(user_id, "refreshing_with_date_filter", 
                              message="Searching for current scholarship opportunities",
                              filter_date=current_date)
    
    asyncio.create_task(auto_refresh_expired_scholarships(user_id, [], [])) 
    return JSONResponse(content={
        "status": "refresh_initiated", 
        "message": f"Scholarship refresh process initiated with current date filtering ({current_date}+).",
        "filter_applied": f"deadlines_after_{current_date}"
    })

@app.post("/api/force_fresh_search")
async def force_fresh_search(request: Request):
    """
    Force a completely fresh scholarship search with strict current date filtering.
    This will clear existing scholarships and search only for opportunities with current deadlines.
    """
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Forcing fresh scholarship search for user {user_id} with strict date filtering")
    
    # Clear existing scholarships first
    await save_scholarships(user_id, [])
    
    # Update search status
    await update_search_status(user_id, "fresh_search_with_date_filter",
                              message="Starting fresh search for current scholarship opportunities only",
                              filter_date=current_date,
                              search_type="fresh_current_only")
    
    # Trigger fresh search through precision search
    profile = await fetch_profile(user_id)
    if profile:
        # This will be handled by a background task or returned as instruction for frontend
        return JSONResponse(content={
            "status": "fresh_search_initiated",
            "message": "Fresh scholarship search initiated. Please use the precision search feature for best results.",
            "recommendation": "Use the 'Search Scholarships' feature to find current opportunities",
            "filter_applied": f"current_deadlines_only_{current_date.split('-')[0]}+"
        })
    else:
        raise HTTPException(status_code=404, detail="User profile not found")

@app.post("/api/download_essays", dependencies=[Depends(verify_subscription)])
async def download_essays(request: Request, user_id: str = Query(...)): 
    await track_api_usage(user_id, "download_essays", "premium_feature", "internal", 0, 0.0, 0, {"feature": "essay_pack_download"})
    try:
        import zipfile; import io
        essays_dl = await fetch_essays(user_id)
        if not essays_dl: raise HTTPException(status_code=404, detail="No essays found for download")
        zip_buffer_dl = io.BytesIO()
        with zipfile.ZipFile(zip_buffer_dl, 'w', zipfile.ZIP_DEFLATED) as zip_file_dl:
            for i, essay_content_dl in enumerate(essays_dl, 1):
                filename_dl = f"essay_{i}_{essay_content_dl.get('scholarship_name', 'unknown').replace(' ', '_')}.txt"
                content_dl = f"Scholarship: {essay_content_dl.get('scholarship_name', 'Unknown')}\nURL: {essay_content_dl.get('scholarship_url', 'N/A')}\nPrompt: {essay_content_dl.get('prompt_text', 'N/A')}\n"
                if essay_content_dl.get('max_words'): content_dl += f"Word Limit: {essay_content_dl.get('max_words')}\n"
                content_dl += f"\nExtracted on: {essay_content_dl.get('created_at', 'Unknown')}\n{'-'*50}\n\n"
                zip_file_dl.writestr(filename_dl, content_dl.encode('utf-8')) 
        zip_buffer_dl.seek(0)
        return StreamingResponse(zip_buffer_dl, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=scholarship_essays.zip"})
    except Exception as e_dl: logger.error(f"Error creating essay download for user {user_id}: {e_dl}", exc_info=True); raise HTTPException(status_code=500, detail="Failed to create essay download")


if __name__ == '__main__':
    if not config.OPENAI_API_KEY or not config.ARCADE_API_KEY: logger.critical("Critical API keys missing. Check .env.")
    uvicorn_params = {"app": "app:app", "host": "0.0.0.0", "port": 5000, "log_level": config.LOG_LEVEL.lower(), "reload": os.getenv("DEV_MODE", "false").lower() == "true"}
    if config.USE_HTTPS and config.SSL_CERT_FILE and config.SSL_KEY_FILE and os.path.exists(config.SSL_CERT_FILE) and os.path.exists(config.SSL_KEY_FILE):
        uvicorn_params.update({"ssl_certfile": config.SSL_CERT_FILE, "ssl_keyfile": config.SSL_KEY_FILE})
        logger.info(f"🔐 HTTPS enabled at {config.APP_URL}")
    else: logger.info(f"🌐 HTTP enabled at http://localhost:{uvicorn_params['port']}")
    uvicorn.run(**uvicorn_params)

@app.post("/api/debug_search")
async def debug_search_endpoint_test_alias(request: Request): 
    try: data = await request.json(); user_profile_data = data.get("user_profile", {})
    except: raise HTTPException(status_code=400, detail="Invalid JSON")
    logger.info(f"Debug search for user_id: {data.get('user_id', 'debug_user')}")
    results = await debug_scholarship_search(user_profile_data)
    return {"success": True, "debug_results": results}

@app.get("/api/test_route")
async def test_route(): return {"status": "success", "message": "Test endpoint working"}

@app.post("/api/smart_search") 
async def smart_search_alias(request: Request):
    """Alias for precision search with smart features"""
    return await hybrid_search_endpoint(request)

# ==========================================
# DEBUG ENDPOINTS
# ==========================================

@app.get("/api/debug/dashboard")
@debug_endpoint
async def debug_dashboard():
    """Get comprehensive debug dashboard data"""
    return get_debug_dashboard_data()

@app.post("/api/debug/js-error")
async def log_js_error(request: Request):
    """Log JavaScript errors from frontend"""
    try:
        data = await request.json()
        tracker.log_error(
            Exception(f"JavaScript Error: {data.get('message', 'Unknown')}"),
            {
                "source": "frontend",
                "timestamp": data.get('timestamp'),
                "level": data.get('level', 'error'),
                "url": str(request.url),
                "user_agent": request.headers.get("user-agent")
            }
        )
        return {"status": "logged"}
    except Exception as e:
        tracker.log_error(e, {"context": "js-error-endpoint"})
        return {"status": "error", "message": str(e)}

@app.get("/api/debug/logs")
@debug_endpoint
async def get_debug_logs(limit: int = 50):
    """Get recent debug logs"""
    data = get_debug_dashboard_data()
    return {
        "requests": data["requests"]["recent"][-limit:],
        "errors": data["errors"]["recent"][-limit:],
        "performance": data["performance"]
    }

@app.get("/debug/onboarding")
async def debug_onboarding_page(request: Request):
    """Special debug version of onboarding with enhanced logging"""
    # Inject debug script into the template
    debug_script = inject_debug_script()
    
    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "debug_mode": True,
        "debug_script": debug_script
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

# Database wrapper functions that automatically provide the pool
async def fetch_profile(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import fetch_profile as db_fetch_profile
    return await db_fetch_profile(pool, user_id)

async def save_profile(user_id: str, profile: dict):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import save_profile as db_save_profile
    return await db_save_profile(pool, user_id, profile)

async def save_scholarships(user_id: str, scholarships: list):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import save_scholarships as db_save_scholarships
    return await db_save_scholarships(pool, user_id, scholarships)

async def fetch_scholarships(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import fetch_scholarships as db_fetch_scholarships
    return await db_fetch_scholarships(pool, user_id)

async def fetch_essays(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import fetch_essays as db_fetch_essays
    return await db_fetch_essays(pool, user_id)

async def save_active_crawl(user_id: str, crawl_id: str):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import save_active_crawl as db_save_active_crawl
    return await db_save_active_crawl(pool, user_id, crawl_id)

async def get_active_crawl(user_id: str):
    pool = db_manager.get_pool()
    if not pool:
        await db_manager.initialize_pool(config.DATABASE_URL)
        pool = db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool initialization failed")
    from services.database import get_active_crawl as db_get_active_crawl
    return await db_get_active_crawl(pool, user_id)

DEFAULT_SCRAPE_SITES = ["https://www.profellow.com", "https://www.appily.com/scholarships", "https://www.niche.com/colleges/scholarships/"]

@app.get("/api/debug/master_database_stats")
@debug_endpoint
async def get_master_database_stats():
    """Get statistics about the master scholarship database"""
    try:
        pool = db_manager.get_pool()
        if not pool:
            raise HTTPException(status_code=503, detail="Database not available")
        
        stats = await get_master_scholarships_stats(pool)
        return stats
    except Exception as e:
        logger.error(f"Error fetching database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search_master_database")
async def search_master_database_endpoint(request: Request):
    """Search the master scholarship database directly"""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        limit = data.get("limit", 50)
        current_only = data.get("current_only", True)
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Get user profile for search context
        profile = await fetch_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        pool = db_manager.get_pool()
        if not pool:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Search master database
        scholarships = await search_master_scholarships(
            pool, 
            profile, 
            limit=limit, 
            current_only=current_only
        )
        
        # Filter expired scholarships if requested
        if current_only:
            scholarships, has_expired = await filter_expired_scholarships(scholarships, user_id, auto_refresh=False)
        
        return {
            "status": "success",
            "scholarships_found": len(scholarships),
            "scholarships": scholarships,
            "source": "master_database",
            "search_params": {
                "user_id": user_id,
                "limit": limit,
                "current_only": current_only,
                "user_profile": {
                    "academic_level": profile.get('academic_level'),
                    "major": profile.get('major'),
                    "location": profile.get('location')
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Master database search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hybrid_search")
async def hybrid_search_endpoint(request: Request):
    """Perform hybrid search using both master database and web search"""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        web_search_enabled = data.get("web_search_enabled", True)
        db_limit = data.get("db_limit", 30)
        web_limit = data.get("web_limit", 20)
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Update search status
        await update_search_status(user_id, "searching_hybrid", source="master_database_plus_web")
        
        results = {
            "database_results": [],
            "web_results": [],
            "total_found": 0,
            "search_summary": "",
            "errors": []
        }
        
        try:
            # 1. Search master database first
            profile = await fetch_profile(user_id)
            if profile:
                pool = db_manager.get_pool()
                if pool:
                    db_scholarships = await search_master_scholarships(
                        pool, 
                        profile, 
                        limit=db_limit, 
                        current_only=True
                    )
                    
                    # Filter expired scholarships
                    db_scholarships, _ = await filter_expired_scholarships(db_scholarships, user_id, auto_refresh=False)
                    results["database_results"] = db_scholarships
                    results["search_summary"] = f"Found {len(db_scholarships)} scholarships in master database"
        except Exception as e:
            logger.error(f"Database search failed: {e}")
            results["errors"].append(f"Database search failed: {str(e)}")
        
        # 2. Supplement with web search if enabled and needed
        if web_search_enabled and len(results["database_results"]) < 25:
            try:
                # Use existing precision search for web results
                await update_search_status(user_id, "searching_web_supplement")
                
                # This will trigger the existing search pipeline as backup
                # The precision orchestrator will handle the web search
                tool_provider = get_tool_provider()
                if not tool_provider:
                    raise HTTPException(status_code=503, detail="Tool provider not initialized")
                
                orchestrator = EnhancedPrecisionScholarshipOrchestrator(
                    arcade_client_global,
                    tool_provider.create_tool_getter()
                )
                web_search_results = await orchestrator.run_enhanced_precision_search(profile)
                
                if web_search_results and web_search_results.get("scholarships"):
                    web_scholarships = web_search_results["scholarships"][:web_limit]
                    # Filter expired scholarships
                    web_scholarships, _ = await filter_expired_scholarships(web_scholarships, user_id, auto_refresh=False)
                    results["web_results"] = web_scholarships
                    results["search_summary"] += f" + {len(web_scholarships)} from web search"
            except Exception as e:
                logger.error(f"Web search supplement failed: {e}")
                results["errors"].append(f"Web search failed: {str(e)}")
        
        # 3. Combine and deduplicate results
        all_scholarships = results["database_results"] + results["web_results"]
        
        # Simple deduplication by name similarity
        seen_names = set()
        deduped_scholarships = []
        for scholarship in all_scholarships:
            name_key = scholarship.get('name', '').lower().strip()
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                deduped_scholarships.append(scholarship)
        
        results["total_found"] = len(deduped_scholarships)
        
        # Save combined results
        if deduped_scholarships:
            await save_scholarships(user_id, deduped_scholarships)
        
        # Update status
        await update_search_status(user_id, "completed", 
                                 scholarships_found=results["total_found"],
                                 search_method="hybrid_database_web")
        
        return results
        
    except Exception as e:
        logger.error(f"Hybrid search error: {e}")
        await update_search_status(user_id, "failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/precision_search")
async def precision_search_endpoint(request: Request):
    """
    Precision search endpoint - alias for start_search with enhanced precision orchestrator.
    This endpoint is called by the dashboard precision search button.
    """
    return await start_search(request)
