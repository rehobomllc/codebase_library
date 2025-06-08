import asyncio
import json
import os
from dotenv import load_dotenv
from pathlib import Path
import httpx
import re
from celery import Celery, group
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, Dict, Any
import redis.asyncio as aioredis
from enum import Enum
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import traceback

# Added: Load .env file
# Construct the path to the .env file, assuming it's in the same directory as tasks.py
# or one level up if tasks.py is in a subdirectory of scholarship_chat_app.
# Given that .env is in scholarship_chat_app and tasks.py is also in scholarship_chat_app.
BASE_DIR = Path(__file__).resolve().parent
# Try loading .env from the same directory as tasks.py
dotenv_path = BASE_DIR / ".env"
if not dotenv_path.exists():
    # If not found, try one level up (e.g. if tasks.py was in a 'workers' subdirectory)
    # This might not be necessary if .env is always at BASE_DIR
    dotenv_path = BASE_DIR.parent / ".env"

print(f"Attempting to load .env from: {dotenv_path}")
loaded_ok = load_dotenv(dotenv_path=dotenv_path)
print(f".env loaded: {loaded_ok}")
print(f"DATABASE_URL from tasks.py: {os.getenv('DATABASE_URL')}")
print(f"ARCADE_API_KEY from tasks.py: {os.getenv('ARCADE_API_KEY')}")
print(f"OPENAI_API_KEY from tasks.py: {os.getenv('OPENAI_API_KEY')}")

from celery import Celery
from arcadepy import AsyncArcade
from agents import Runner, RunConfig, ModelSettings # MODIFIED: Ensure Runner, RunConfig, and ModelSettings are imported

# Assuming app.py initializes and configures this celery_app instance if it needs to be shared
# For a standalone tasks.py, you might need to initialize Celery app here if not already done by app.py
# However, the prompt implies app.py's Celery app is used.
# We need to ensure REDIS_URL is available.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("scholarship_tasks", broker=REDIS_URL, backend=REDIS_URL)

# Import database save function
# This might cause a circular import if database.py imports tasks.py or celery_app from tasks
# A common pattern is to have db operations in their own module that both app.py and tasks.py can import
# For now, assuming direct import works or save_essays is accessible another way.
# From the prompt, it seems `save_essays` is in `services.database`
# Import database helpers from the local package (relative import ensures the
# module is found whether or not the project root is on PYTHONPATH).
# Import database helpers. When the module is imported as
# `scholarship_chat_app.tasks`, the relative path works. If the module is
# imported as a top-level `tasks` (e.g. during ad-hoc testing), fall back to an
# absolute import so developers don't hit an ImportError.

try:
    from .services.database import save_essays, save_failed_scrape  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from services.database import save_essays, save_failed_scrape  # noqa: F401

# Import progress tracking functions
try:
    from .services.database import (
        init_essay_extraction_progress, 
        update_essay_extraction_progress, 
        get_essay_extraction_progress,
        clear_essay_extraction_progress
    )  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from services.database import (
        init_essay_extraction_progress, 
        update_essay_extraction_progress, 
        get_essay_extraction_progress,
        clear_essay_extraction_progress
    )  # noqa: F401

# Import agent creator
try:
    from .scholarship_agents.essay_extractor import create_essay_extractor  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from scholarship_agents.essay_extractor import create_essay_extractor  # noqa: F401

# Import enhanced Arcade agents
try:
    from .scholarship_agents.validation_agent_v2_arcade import (
        enhanced_validation_with_arcade,
        validate_candidates_concurrent,
        create_arcade_essay_extraction_agent,
        create_arcade_scholarship_monitor,
    )  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from scholarship_agents.validation_agent_v2_arcade import (
        enhanced_validation_with_arcade,
        validate_candidates_concurrent,
        create_arcade_essay_extraction_agent,
        create_arcade_scholarship_monitor
    )  # noqa: F401

# Import database manager
try:
    from .services.database import DatabaseManager
except ImportError:  # pragma: no cover – fallback for direct execution
    from services.database import DatabaseManager

# Create a global database manager instance for tasks
_task_db_manager = DatabaseManager()

# Helper functions to handle database pool for progress tracking
async def task_init_essay_extraction_progress(user_id: str, total_scholarships: int):
    """Wrapper for init_essay_extraction_progress that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await init_essay_extraction_progress(pool, user_id, total_scholarships)

async def task_update_essay_extraction_progress(user_id: str, scholarship_pk: str, status: str, **kwargs):
    """Wrapper for update_essay_extraction_progress that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await update_essay_extraction_progress(pool, user_id, scholarship_pk, status, **kwargs)

async def task_get_essay_extraction_progress(user_id: str):
    """Wrapper for get_essay_extraction_progress that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await get_essay_extraction_progress(pool, user_id)

async def task_clear_essay_extraction_progress(user_id: str):
    """Wrapper for clear_essay_extraction_progress that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await clear_essay_extraction_progress(pool, user_id)

logger = get_task_logger(__name__)

# Ensure ARCADE_API_KEY is loaded for AsyncArcade client
ARCADE_API_KEY = os.getenv("ARCADE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # For potential use by agents if not using Arcade proxy

if not ARCADE_API_KEY:
    logger.warning("ARCADE_API_KEY not found in environment. Essay extraction agent may fail.")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not found in environment. Agents may fail if directly using OpenAI.")

HTML_TRIM_LENGTH = 30000 # Increased to capture more content for parsing
COMMON_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# ---- Unified status enum for crawl & essay extraction progress ----
class ProgressStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def choices(cls):
        return [cls.QUEUED, cls.IN_PROGRESS, cls.COMPLETED, cls.FAILED]

# Redis client for pub/sub progress updates
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

# Helper function to run async code from sync Celery task
def async_to_sync(awaitable):
    return asyncio.run(awaitable)

async def web_search_for_scholarship_application(user_id: str, scholarship_name: str, provider: str, arcade_client) -> Optional[Dict[str, Any]]:
    """
    Search the web for a scholarship's actual application page when the original URL fails.
    Uses multiple creative strategies to bypass login walls and access requirements.
    Returns the best match with URL and content summary, or None if not found.
    """
    logger.info(f"Starting enhanced web search fallback for scholarship: {scholarship_name}")
    
    # Generate comprehensive search queries using multiple strategies
    search_queries = []
    
    # Strategy 1: Provider-specific search (if available)
    if provider and provider.lower() != 'unknown':
        search_queries.extend([
            f"{scholarship_name} application {provider}",
            f'"{scholarship_name}" apply site:{provider}',
            f'site:{provider} "{scholarship_name}" requirements'
        ])
    
    # Strategy 2: Archive and cache services (bypass login walls)
    search_queries.extend([
        f'site:web.archive.org "{scholarship_name}" application',
        f'site:archive.today "{scholarship_name}" requirements',
        f'site:webcitation.org "{scholarship_name}" application'
    ])
    
    # Strategy 3: Document search (PDFs often bypass login)
    search_queries.extend([
        f'"{scholarship_name}" filetype:pdf application',
        f'"{scholarship_name}" filetype:doc requirements',
        f'"{scholarship_name}" scholarship guidelines filetype:pdf'
    ])
    
    # Strategy 4: Community and forum sources (students share requirements)
    search_queries.extend([
        f'"{scholarship_name}" site:reddit.com application requirements',
        f'"{scholarship_name}" site:collegeconfidential.com essays',
        f'"{scholarship_name}" application questions reddit'
    ])
    
    # Strategy 5: Educational aggregator sites
    search_queries.extend([
        f'"{scholarship_name}" site:fastweb.com',
        f'"{scholarship_name}" site:scholarships.com',
        f'"{scholarship_name}" site:cappex.com',
        f'"{scholarship_name}" site:unigo.com'
    ])
    
    # Strategy 6: Government and public databases
    search_queries.extend([
        f'"{scholarship_name}" site:grants.gov',
        f'"{scholarship_name}" site:studentaid.gov',
        f'"{scholarship_name}" site:nsf.gov'
    ])
    
    # Strategy 7: General application-focused searches
    search_queries.extend([
        f'"{scholarship_name}" application form requirements',
        f"{scholarship_name} apply online essay requirements", 
        f"{scholarship_name} scholarship application portal"
    ])
    
    logger.info(f"Generated {len(search_queries)} enhanced search queries for {scholarship_name}")
    
    try:
        # Try each search query until we find a good result
        for i, query in enumerate(search_queries):
            logger.info(f"Attempting search query {i+1}/{len(search_queries)}: {query}")
            
            try:
                search_result = await arcade_client.tools.execute(
                    tool_name="GoogleScholarshipSearchTool",
                    input={"query": query, "num_results": 5},
                    user_id=user_id
                )
                
                if not search_result or not search_result.get("results"):
                    logger.warning(f"No results for query: {query}")
                    continue
                
                # Evaluate each result for application page relevance
                for result in search_result.get("results", []):
                    url = result.get("url", "")
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    
                    if not url:
                        continue
                    
                    # Enhanced scoring system with source type bonuses
                    relevance_score = 0
                    content_text = f"{title} {snippet}".lower()
                    
                    # Source type bonuses (reward alternative sources)
                    if any(archive in url.lower() for archive in ['archive.org', 'archive.today', 'webcitation.org']):
                        relevance_score += 15  # Archive sources bonus
                        logger.info(f"Archive source bonus for: {url}")
                    
                    if url.lower().endswith(('.pdf', '.doc', '.docx')):
                        relevance_score += 20  # Document bonus (likely has full requirements)
                        logger.info(f"Document source bonus for: {url}")
                    
                    if any(community in url.lower() for community in ['reddit.com', 'collegeconfidential.com', 'gradcafe.com']):
                        relevance_score += 10  # Community source bonus
                        logger.info(f"Community source bonus for: {url}")
                    
                    if any(aggregator in url.lower() for aggregator in ['fastweb.com', 'scholarships.com', 'cappex.com', 'unigo.com']):
                        relevance_score += 12  # Aggregator bonus
                        logger.info(f"Aggregator source bonus for: {url}")
                    
                    if any(gov in url.lower() for gov in ['.gov', 'grants.gov', 'studentaid.gov']):
                        relevance_score += 18  # Government source bonus (high trust)
                        logger.info(f"Government source bonus for: {url}")
                    
                    # Application terms (high priority)
                    application_terms = [
                        "application", "apply", "requirements", "eligibility",
                        "essay", "prompt", "questions", "form", "portal",
                        "deadline", "submit", "criteria", "guidelines"
                    ]
                    for term in application_terms:
                        if term in content_text:
                            relevance_score += 12  # Slightly reduced individual weight
                    
                    # Scholarship name match (very high priority)
                    name_words = scholarship_name.lower().split()
                    for word in name_words:
                        if len(word) > 2 and word in content_text:
                            relevance_score += 20  # Reduced from 25 to balance with source bonuses
                    
                    # URL indicators of application pages
                    url_application_indicators = [
                        "application", "apply", "form", "scholarship",
                        "requirements", "eligibility", "portal", "guidelines"
                    ]
                    for indicator in url_application_indicators:
                        if indicator in url.lower():
                            relevance_score += 8  # Reduced from 10
                    
                    # Avoid low-quality sources (but less penalty for alternative sources)
                    avoid_terms = ["wikipedia", "news", "blog", "forum"]  # Removed reddit since it can be valuable
                    for term in avoid_terms:
                        if term in url.lower() or term in content_text:
                            relevance_score -= 15  # Reduced penalty
                    
                    logger.info(f"URL candidate: {url}, relevance score: {relevance_score}")
                    
                    # If this looks promising, get page summary to validate (lower threshold for alternative sources)
                    threshold = 25 if any(alt in url.lower() for alt in ['archive.org', '.pdf', '.gov', 'reddit.com']) else 30
                    if relevance_score >= threshold:
                        logger.info(f"Getting page summary for promising URL: {url}")
                        
                        try:
                            # For document URLs, skip page summary (PDFs often can't be summarized)
                            if url.lower().endswith(('.pdf', '.doc', '.docx')):
                                logger.info(f"Document URL found for {scholarship_name}: {url} (score: {relevance_score})")
                                return {
                                    "url": url,
                                    "title": title,
                                    "summary": f"Document: {title} - {snippet}",
                                    "search_query_used": query,
                                    "relevance_score": relevance_score,
                                    "source_method": "document_fallback",
                                    "source_type": "document"
                                }
                            
                            summary_result = await arcade_client.tools.execute(
                                tool_name="Web.GetPageSummary", 
                                input={"url": url},
                                user_id=user_id
                            )
                            
                            if summary_result and summary_result.get("summary"):
                                summary_text = summary_result.get("summary", "").lower()
                                
                                # Additional validation based on page content
                                page_score = relevance_score
                                
                                # Look for strong application indicators in page content
                                strong_indicators = [
                                    "essay prompt", "essay question", "application requirement",
                                    "how to apply", "application process", "submission deadline",
                                    "required documents", "application form", "scholarship guidelines"
                                ]
                                for indicator in strong_indicators:
                                    if indicator in summary_text:
                                        page_score += 15  # Reduced from 20
                                
                                # Lower final threshold for alternative sources
                                final_threshold = 40 if any(alt in url.lower() for alt in ['archive.org', '.gov', 'reddit.com', 'fastweb.com']) else 50
                                if page_score >= final_threshold:
                                    source_type = "archive" if "archive" in url.lower() else \
                                                "government" if ".gov" in url.lower() else \
                                                "community" if any(c in url.lower() for c in ['reddit.com', 'collegeconfidential.com']) else \
                                                "aggregator" if any(a in url.lower() for a in ['fastweb.com', 'scholarships.com']) else \
                                                "standard"
                                    
                                    logger.info(f"Found suitable application page for {scholarship_name}: {url} (score: {page_score}, type: {source_type})")
                                    return {
                                        "url": url,
                                        "title": title,
                                        "summary": summary_result.get("summary", ""),
                                        "search_query_used": query,
                                        "relevance_score": page_score,
                                        "source_method": "enhanced_web_search_fallback",
                                        "source_type": source_type
                                    }
                        
                        except Exception as e:
                            logger.warning(f"Error getting page summary for {url}: {e}")
                            continue
                
            except Exception as e:
                logger.warning(f"Error with search query '{query}': {e}")
                continue
        
        logger.warning(f"No suitable application page found for {scholarship_name} after trying {len(search_queries)} enhanced queries")
        return None
        
    except Exception as e:
        logger.error(f"Error in enhanced web search fallback for {scholarship_name}: {e}")
        return None

async def extract_essays_task_wrapper(user_id: str, scholarship_url: str, scholarship_pk: str, scholarship_name: str):
    """
    Asynchronous wrapper for extracting essays.
    Fetches HTML, invokes the essay extraction agent, and saves the results.
    Enhanced with web search fallback when original URL fails.
    """
    logger.info(f"Starting essay extraction for {scholarship_name} ({scholarship_pk}) at {scholarship_url}")

    if not ARCADE_API_KEY:
        logger.error("ARCADE_API_KEY is not set. Cannot initialize AsyncArcade for essay extraction.")
        return {"status": "error", "scholarship_pk": scholarship_pk, "error": "ARCADE_API_KEY not configured"}

    from arcadepy import AsyncArcade

    html_content_full = ""
    arcade_client = None
    local_redis_client = None
    extraction_error = None
    original_url = scholarship_url  # Keep track of original URL
    fallback_used = False
    fallback_info = None

    try:
        local_redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)

        headers = {"User-Agent": COMMON_USER_AGENT}
        
        # First attempt: Try original URL
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            try:
                response = await client.get(scholarship_url)
                response.raise_for_status()
                html_content_full = response.text
                logger.info(f"Successfully fetched HTML for {scholarship_name} ({scholarship_pk}). Original length: {len(html_content_full)}")
            
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                # Original URL failed - try web search fallback
                logger.warning(f"Original URL failed for {scholarship_name} ({scholarship_pk}): {e}")
                logger.info(f"Attempting web search fallback for {scholarship_name}")
                
                # Extract provider from original URL for better search
                provider = None
                if scholarship_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(scholarship_url)
                    if parsed.netloc:
                        provider = parsed.netloc.replace('www.', '')
                
                # Search for the actual application page
                fallback_result = await web_search_for_scholarship_application(
                    user_id, scholarship_name, provider, arcade_client
                )
                
                if fallback_result:
                    # Found a good alternative URL - try to fetch it
                    fallback_url = fallback_result["url"]
                    logger.info(f"Trying fallback URL for {scholarship_name}: {fallback_url}")
                    
                    try:
                        fallback_response = await client.get(fallback_url)
                        fallback_response.raise_for_status()
                        html_content_full = fallback_response.text
                        scholarship_url = fallback_url  # Update URL for essay extraction
                        fallback_used = True
                        fallback_info = fallback_result
                        logger.info(f"Successfully fetched HTML from fallback URL for {scholarship_name}. Length: {len(html_content_full)}")
                    
                    except (httpx.HTTPStatusError, httpx.RequestError) as fallback_error:
                        logger.error(f"Fallback URL also failed for {scholarship_name}: {fallback_error}")
                        extraction_error = f"Original URL failed ({e}), fallback URL also failed ({fallback_error})"
                    return {"status": "error", "scholarship_pk": scholarship_pk, "error": extraction_error}
                # No suitable fallback found
                logger.error(f"No suitable fallback URL found for {scholarship_name}")
                extraction_error = f"Original URL failed ({e}), no suitable fallback found"
                return {"status": "error", "scholarship_pk": scholarship_pk, "error": extraction_error}

        # Continue with essay extraction using the HTML content (original or fallback)
        html_content_trimmed = html_content_full[:HTML_TRIM_LENGTH]
        if len(html_content_full) > HTML_TRIM_LENGTH:
            logger.info(f"HTML content for {scholarship_name} ({scholarship_pk}) trimmed to {HTML_TRIM_LENGTH} characters.")

        # Prepare message for the agent
        url_source = "fallback web search" if fallback_used else "original URL"
        agent_message = (
            f"Scholarship HTML Content (trimmed to {HTML_TRIM_LENGTH} chars, from {url_source}):\n{html_content_trimmed}\n\n"
            f"Scholarship PK: {scholarship_pk}\n\n"
            "Please extract essay prompts based on the above HTML and Scholarship PK. "
            "Ensure the PK is included in your JSON output."
        )

        essay_agent = await create_essay_extractor(arcade_client=arcade_client)
        
        logger.info(f"Invoking essay extraction agent for {scholarship_name} ({scholarship_pk}) using {url_source}.")
        
        # Create RunConfig for essay extraction
        runner_input_messages = [{"role": "user", "content": agent_message}]
        model_settings_for_run = ModelSettings(tool_choice="none")
        current_run_config = RunConfig(
            model_settings=model_settings_for_run,
            workflow_name="EssayExtractionWorkflow",
            group_id=user_id
        )
        
        agent_run_result = await Runner.run(
            starting_agent=essay_agent,
            input=runner_input_messages,
            run_config=current_run_config
        )
        
        logger.info(f"Full agent_run_result object for {scholarship_name} ({scholarship_pk}): {agent_run_result!r}")

        # Extract agent response
        agent_response_output = None
        if agent_run_result and hasattr(agent_run_result, 'final_output'):
            if hasattr(agent_run_result.final_output, 'content'):
                agent_response_output = agent_run_result.final_output.content
            else:
                agent_response_output = agent_run_result.final_output 
        else:
            logger.warning(f"agent_run_result for {scholarship_name} ({scholarship_pk}) did not have a final_output attribute or was None. Result: {agent_run_result!r}")

        extracted_essays = []
        if agent_response_output:
            raw_json_output = str(agent_response_output)
            logger.info(f"Raw JSON output from agent for {scholarship_name} ({scholarship_pk}): {raw_json_output}")
            
            try:
                extracted_essays = json.loads(raw_json_output)
                if not isinstance(extracted_essays, list):
                    logger.error(f"Agent for {scholarship_name} ({scholarship_pk}) did not return a list. Output: {raw_json_output}")
                    extracted_essays = [] 
            except json.JSONDecodeError as e:
                logger.error(f"JSONDecodeError for {scholarship_name} ({scholarship_pk}): {e}. Raw output: {raw_json_output}")
                try:
                    match = re.search(r'\[(.*?)\]', raw_json_output, re.DOTALL)
                    if match:
                        corrected_json_str = match.group(0)
                        logger.info(f"Attempting to parse extracted JSON: {corrected_json_str}")
                        extracted_essays = json.loads(corrected_json_str)
                        if not isinstance(extracted_essays, list): 
                            extracted_essays = []
                    else:
                        extracted_essays = []
                except Exception:
                    extracted_essays = [] 
        else:
            logger.warning(f"No valid output from essay agent for {scholarship_name} ({scholarship_pk}). Response: {agent_response_output!r}")

        logger.info(f"Extracted {len(extracted_essays)} essays for {scholarship_name} ({scholarship_pk}).")
        
        # Add metadata to essays including fallback information
        for essay in extracted_essays:
            if "scholarship_pk" not in essay:
                essay["scholarship_pk"] = scholarship_pk
            
            # Add scholarship metadata for better frontend display
            essay["scholarship_name"] = scholarship_name
            essay["scholarship_url"] = scholarship_url
            essay["extraction_timestamp"] = datetime.now().isoformat()
            
            # Add fallback metadata if used
            if fallback_used and fallback_info:
                essay["extraction_method"] = fallback_info.get("source_method", "web_search_fallback")
                essay["original_url"] = original_url
                essay["fallback_url"] = scholarship_url
                essay["fallback_search_query"] = fallback_info.get("search_query_used")
                essay["fallback_relevance_score"] = fallback_info.get("relevance_score")
                essay["fallback_source_type"] = fallback_info.get("source_type", "unknown")
                
                # Add source-specific metadata
                if fallback_info.get("source_type") == "document":
                    essay["extraction_note"] = "Extracted from document source (PDF/DOC)"
                elif fallback_info.get("source_type") == "archive":
                    essay["extraction_note"] = "Extracted from archived version"
                elif fallback_info.get("source_type") == "community":
                    essay["extraction_note"] = "Extracted from community/forum source"
                elif fallback_info.get("source_type") == "government":
                    essay["extraction_note"] = "Extracted from government database"
                elif fallback_info.get("source_type") == "aggregator":
                    essay["extraction_note"] = "Extracted from scholarship aggregator site"
                else:
                    essay["extraction_note"] = "Extracted using enhanced web search fallback"
            else:
                essay["extraction_method"] = "original_url"
                essay["extraction_note"] = "Extracted from original scholarship URL"

        if extracted_essays: 
            await task_save_essays(user_id, extracted_essays)
            logger.info(f"Successfully saved {len(extracted_essays)} essays for {scholarship_pk} to Postgres.")
        else:
            logger.info(f"No essays found or extracted for {scholarship_name} ({scholarship_pk}). Nothing to save to Postgres for essays.")
        
        # Prepare result with fallback information
        result = {
            "status": "success", 
            "scholarship_pk": scholarship_pk, 
            "essays_found": len(extracted_essays)
        }
        
        if fallback_used:
            result["fallback_used"] = True
            result["original_url"] = original_url
            result["successful_url"] = scholarship_url
            result["fallback_method"] = "web_search"
            
        return result

    except Exception as e:
        logger.error(f"Generic error in extract_essays_task_wrapper for {scholarship_name} ({scholarship_pk}): {e}", exc_info=True)
        extraction_error = f"Generic error: {type(e).__name__} - {str(e)}"
        return {"status": "error", "scholarship_pk": scholarship_pk, "error": str(e)}
    finally:
        if arcade_client and hasattr(arcade_client, 'aclose'):
            await arcade_client.aclose()
        # If there was an error during the main processing, log it using save_failed_scrape
        if extraction_error:
            logger.info(f"Attempting to save failed scrape due to earlier error: {extraction_error}")
            await task_save_failed_scrape(user_id, scholarship_pk, original_url, scholarship_name, extraction_error)

@celery_app.task(name="extract_essays", bind=True, max_retries=3, default_retry_delay=60)
def extract_essays_task(self, user_id: str, scholarship_url: str, scholarship_pk: str, scholarship_name: str):
    """
    Celery task to extract essay prompts from a scholarship URL.
    This task is synchronous but calls an asynchronous wrapper.
    """
    logger.info(f"Received task: extract_essays for user {user_id}, scholarship_pk {scholarship_pk}, url {scholarship_url}")
    try:
        result = async_to_sync(extract_essays_task_wrapper(user_id, scholarship_url, scholarship_pk, scholarship_name))
        logger.info(f"Essay extraction task completed for {scholarship_pk}. Result: {result}")
        return result
    except SQLAlchemyError as e: 
        logger.error(f"Database error during essay extraction for {scholarship_pk}: {e}")
        self.retry(exc=e)
    except httpx.TimeoutException as e: 
        logger.error(f"Timeout error during essay extraction for {scholarship_pk}: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Unhandled exception in extract_essays_task for {scholarship_pk}: {e}", exc_info=True)
        raise

# To run Celery worker (from ScholarshipFinder/openai-agents-arcade directory):
# celery -A scholarship_chat_app.tasks worker -l info -c 2
# Ensure your .env file is in scholarship_chat_app/ and has REDIS_URL and ARCADE_API_KEY 

async def publish_essay_extraction_update(user_id: str, update_data: dict):
    """Publish essay extraction progress update via Redis pub/sub with enhanced timeline data"""
    try:
        # Enhance update data with timeline-specific fields
        enhanced_data = {
            **update_data,
            'timestamp': update_data.get('timestamp', datetime.now().isoformat()),
            'step_reason': update_data.get('step_reason', ''),
            'stage_label': update_data.get('stage_label', ''),
            'fallback_used': update_data.get('fallback_used', False),
            'progress_percentage': update_data.get('progress_percentage', 0)
        }
        
        channel = f"essay_extraction_updates:{user_id}"
        message = json.dumps(enhanced_data)
        await redis_client.publish(channel, message)
        logger.info(f"Published enhanced essay extraction update for user {user_id}: {enhanced_data.get('status', 'unknown')} - {enhanced_data.get('stage_label', 'No stage')}")
    except Exception as e:
        logger.warning(f"Failed to publish essay extraction update for user {user_id}: {e}")

async def extract_single_essay_immediate(user_id: str, scholarship_url: str, scholarship_pk: str, scholarship_name: str, session_id: str) -> dict:
    """
    Extract essays for a single scholarship immediately with enhanced progress updates.
    Returns result dict with status, essays_found, and metadata.
    """
    logger.info(f"Starting immediate essay extraction for {scholarship_name} ({scholarship_pk})")
    
    # Update progress to queued with detailed info
    await task_update_essay_extraction_progress(
        user_id, scholarship_pk, ProgressStatus.QUEUED,
        scholarship_name=scholarship_name,
        queued_at=datetime.now().isoformat()
    )
    
    # Publish enhanced queued update
    await publish_essay_extraction_update(user_id, {
        'status': ProgressStatus.QUEUED,
        'scholarship_pk': scholarship_pk,
        'scholarship_name': scholarship_name,
        'session_id': session_id,
        'stage_label': 'Queued for Processing',
        'step_reason': f'Scholarship "{scholarship_name}" added to extraction queue',
        'progress_percentage': 0,
        'timestamp': datetime.now().isoformat()
    })
    
    # Update progress to in_progress
    await task_update_essay_extraction_progress(
        user_id, scholarship_pk, ProgressStatus.IN_PROGRESS,
        scholarship_name=scholarship_name,
        started_at=datetime.now().isoformat()
    )
    
    # Publish enhanced in_progress update
    await publish_essay_extraction_update(user_id, {
        'status': ProgressStatus.IN_PROGRESS,
        'scholarship_pk': scholarship_pk,
        'scholarship_name': scholarship_name,
        'session_id': session_id,
        'stage_label': 'Initializing Extraction',
        'step_reason': f'Starting essay extraction process for {scholarship_name}',
        'progress_percentage': 20,
        'timestamp': datetime.now().isoformat()
    })
    
    try:
        # Publish validation stage update
        await publish_essay_extraction_update(user_id, {
            'status': 'validating',
            'scholarship_pk': scholarship_pk,
            'scholarship_name': scholarship_name,
            'session_id': session_id,
            'stage_label': 'Validating Scholarship URL',
            'step_reason': f'Checking accessibility of {scholarship_url}',
            'progress_percentage': 40,
            'timestamp': datetime.now().isoformat()
        })
        
        # Run the existing essay extraction logic
        result = await extract_essays_task_wrapper(user_id, scholarship_url, scholarship_pk, scholarship_name)
        
        # Determine if fallback was used based on result
        fallback_used = result.get('fallback_used', False)
        fallback_reason = ''
        if fallback_used:
            fallback_reason = result.get('fallback_reason', 'Original URL inaccessible, used alternative search methods')
        
        # Publish extraction stage update
        await publish_essay_extraction_update(user_id, {
            'status': 'extracting',
            'scholarship_pk': scholarship_pk,
            'scholarship_name': scholarship_name,
            'session_id': session_id,
            'stage_label': 'Extracting Essay Requirements',
            'step_reason': fallback_reason if fallback_used else f'Processing content from {scholarship_url}',
            'fallback_used': fallback_used,
            'progress_percentage': 80,
            'timestamp': datetime.now().isoformat()
        })
        
        if result.get('status') == 'success':
            essays_found = result.get('essays_found', 0)
            
            # Update progress to completed
            await task_update_essay_extraction_progress(
                user_id, scholarship_pk, ProgressStatus.COMPLETED,
                scholarship_name=scholarship_name,
                essays_found=essays_found,
                completed_at=datetime.now().isoformat(),
                fallback_used=fallback_used
            )
            
            # Publish enhanced success update
            await publish_essay_extraction_update(user_id, {
                'status': ProgressStatus.COMPLETED,
                'scholarship_pk': scholarship_pk,
                'scholarship_name': scholarship_name,
                'essays_found': essays_found,
                'fallback_used': fallback_used,
                'session_id': session_id,
                'stage_label': 'Extraction Completed Successfully',
                'step_reason': f'Found {essays_found} essay requirements' + (f' using fallback methods' if fallback_used else ''),
                'progress_percentage': 100,
                'timestamp': datetime.now().isoformat()
            })
            
        else:
            error_message = result.get('error', 'Unknown error')
            
            # Update progress to failed
            await task_update_essay_extraction_progress(
                user_id, scholarship_pk, ProgressStatus.FAILED,
                scholarship_name=scholarship_name,
                error_message=error_message,
                failed_at=datetime.now().isoformat()
            )
            
            # Publish enhanced failure update
            await publish_essay_extraction_update(user_id, {
                'status': ProgressStatus.FAILED,
                'scholarship_pk': scholarship_pk,
                'scholarship_name': scholarship_name,
                'error': error_message,
                'session_id': session_id,
                'stage_label': 'Extraction Failed',
                'step_reason': f'Failed to extract essays: {error_message}' + (f' (fallback also failed)' if fallback_used else ''),
                'fallback_used': fallback_used,
                'progress_percentage': 0,
                'timestamp': datetime.now().isoformat()
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error in immediate essay extraction for {scholarship_name}: {e}", exc_info=True)
        
        # Update progress to failed
        await task_update_essay_extraction_progress(
            user_id, scholarship_pk, ProgressStatus.FAILED,
            scholarship_name=scholarship_name,
            error_message=str(e),
            failed_at=datetime.now().isoformat()
        )
        
        # Publish enhanced failure update
        await publish_essay_extraction_update(user_id, {
            'status': ProgressStatus.FAILED,
            'scholarship_pk': scholarship_pk,
            'scholarship_name': scholarship_name,
            'error': str(e),
            'session_id': session_id,
            'stage_label': 'System Error',
            'step_reason': f'Unexpected error during extraction: {str(e)}',
            'fallback_used': False,
            'progress_percentage': 0,
            'timestamp': datetime.now().isoformat()
        })
        
        return {"status": "error", "scholarship_pk": scholarship_pk, "error": str(e)}

async def extract_essays_immediate_batch(user_id: str, scholarships: list, max_concurrent: int = 3) -> dict:
    """
    Extract essays for multiple scholarships immediately with controlled concurrency.
    Provides enhanced real-time progress updates via Redis pub/sub.
    """
    session_id = f"essay_extraction_{user_id}_{int(datetime.now().timestamp())}"
    total_scholarships = len(scholarships)
    
    logger.info(f"Starting immediate essay extraction batch for user {user_id}: {total_scholarships} scholarships")
    
    # Initialize progress tracking
    await task_init_essay_extraction_progress(user_id, total_scholarships)
    
    # Publish enhanced start update
    await publish_essay_extraction_update(user_id, {
        'status': ProgressStatus.QUEUED,
        'total_scholarships': total_scholarships,
        'session_id': session_id,
        'stage_label': 'Batch Processing Initialized',
        'step_reason': f'Starting batch extraction for {total_scholarships} scholarships with max {max_concurrent} concurrent processes',
        'progress_percentage': 0,
        'timestamp': datetime.now().isoformat()
    })
    
    # Create semaphore to limit concurrent extractions
    semaphore = asyncio.Semaphore(max_concurrent)
    completed_count = 0
    
    async def bounded_extract(scholarship, index):
        nonlocal completed_count
        async with semaphore:
            scholarship_url = scholarship.get("application_url") or scholarship.get("url")
            scholarship_pk = scholarship.get("url")  # Use original URL as PK
            scholarship_name = scholarship.get("title", "Untitled Scholarship")
            
            # Publish individual scholarship start update
            await publish_essay_extraction_update(user_id, {
                'status': 'in_progress',
                'scholarship_pk': scholarship_pk,
                'scholarship_name': scholarship_name,
                'session_id': session_id,
                'stage_label': f'Processing Scholarship {index + 1}/{total_scholarships}',
                'step_reason': f'Starting extraction for "{scholarship_name}"',
                'progress_percentage': (index / total_scholarships) * 100,
                'batch_progress': {
                    'current': index + 1,
                    'total': total_scholarships,
                    'completed': completed_count
                },
                'timestamp': datetime.now().isoformat()
            })
            
            result = await extract_single_essay_immediate(user_id, scholarship_url, scholarship_pk, scholarship_name, session_id)
            
            completed_count += 1
            
            # Publish individual completion update
            await publish_essay_extraction_update(user_id, {
                'status': 'extracting',
                'scholarship_pk': scholarship_pk,
                'scholarship_name': scholarship_name,
                'session_id': session_id,
                'stage_label': f'Completed {completed_count}/{total_scholarships}',
                'step_reason': f'Finished processing "{scholarship_name}" - {result.get("status", "unknown")}',
                'progress_percentage': (completed_count / total_scholarships) * 90,  # Leave 10% for final processing
                'batch_progress': {
                    'current': index + 1,
                    'total': total_scholarships,
                    'completed': completed_count
                },
                'timestamp': datetime.now().isoformat()
            })
            
            return result
    
    # Run all extractions concurrently with controlled parallelism
    results = await asyncio.gather(*[bounded_extract(s, i) for i, s in enumerate(scholarships)], return_exceptions=True)
    
    # Count results
    successful = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
    failed = sum(1 for r in results if isinstance(r, dict) and r.get('status') != 'success' or isinstance(r, Exception))
    total_essays_found = sum(r.get('essays_found', 0) for r in results if isinstance(r, dict))
    
    # Determine overall batch status
    batch_status = 'batch_completed'
    if failed == total_scholarships:
        batch_status = 'failed'
    elif failed > 0:
        batch_status = 'completed'  # Partial success
    
    # Publish enhanced final update
    await publish_essay_extraction_update(user_id, {
        'status': batch_status,
        'total_scholarships': total_scholarships,
        'successful': successful,
        'failed': failed,
        'essays_found': total_essays_found,
        'session_id': session_id,
        'stage_label': 'Batch Processing Completed',
        'step_reason': f'Processed {total_scholarships} scholarships: {successful} successful, {failed} failed, {total_essays_found} essays found',
        'progress_percentage': 100,
        'batch_summary': {
            'total_processed': total_scholarships,
            'successful_extractions': successful,
            'failed_extractions': failed,
            'total_essays_found': total_essays_found,
            'success_rate': (successful / total_scholarships * 100) if total_scholarships > 0 else 0
        },
        'timestamp': datetime.now().isoformat()
    })
    
    logger.info(f"Immediate essay extraction batch completed for user {user_id}: {successful} successful, {failed} failed, {total_essays_found} essays found")
    
    return {
        'status': batch_status,
        'total_scholarships': total_scholarships,
        'successful': successful,
        'failed': failed,
        'essays_found': total_essays_found,
        'session_id': session_id
    }

@celery_app.task(name="enhanced_validation_task", bind=True, max_retries=2)
def enhanced_validation_task(self, user_id: str, scholarship_candidates: dict):
    """
    Celery task for enhanced scholarship validation using Arcade Web tools
    """
    try:
        return async_to_sync(_enhanced_validation_task_async(user_id, scholarship_candidates))
    except Exception as e:
        logger.error(f"Enhanced validation failed for user {user_id}: {str(e)}")
        self.retry(countdown=60, exc=e)

async def _enhanced_validation_task_async(user_id: str, scholarship_candidates: dict):
    """
    Async implementation of enhanced validation task
    """
    if not ARCADE_API_KEY:
        logger.error("ARCADE_API_KEY not available for enhanced validation")
        return {"error": "Arcade API key not configured"}
    
    arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
    
    candidates = scholarship_candidates.get("scholarship_candidates", [])

    validation_results_list = await validate_candidates_concurrent(
        user_id, candidates, arcade_client
    )

    combined = {
        "validated_scholarships": [],
        "rejected_scholarships": [],
        "validation_summary": {"total_processed": 0},
    }
    for res in validation_results_list:
        combined["validated_scholarships"].extend(res.get("validated_scholarships", []))
        combined["rejected_scholarships"].extend(res.get("rejected_scholarships", []))
        combined["validation_summary"]["total_processed"] += res.get(
            "validation_summary", {}
        ).get("total_processed", 0)

    logger.info(
        f"Enhanced validation completed for user {user_id}: "
        f"{len(combined['validated_scholarships'])} validated, "
        f"{len(combined['rejected_scholarships'])} rejected"
    )

    return combined

@celery_app.task(name="arcade_essay_extraction_task", bind=True, max_retries=2)
def arcade_essay_extraction_task(self, user_id: str, scholarship_url: str, scholarship_pk: str, scholarship_name: str):
    """
    Enhanced essay extraction using Arcade Web tools for comprehensive site mapping
    """
    try:
        return async_to_sync(_arcade_essay_extraction_async(user_id, scholarship_url, scholarship_pk, scholarship_name))
    except Exception as e:
        logger.error(f"Arcade essay extraction failed for {scholarship_name}: {str(e)}")
        # Save failed scrape in sync context
        async_to_sync(save_failed_scrape(user_id, scholarship_pk, scholarship_url, scholarship_name, str(e)))
        self.retry(countdown=60, exc=e)

async def _arcade_essay_extraction_async(user_id: str, scholarship_url: str, scholarship_pk: str, scholarship_name: str):
    """
    Async implementation of Arcade essay extraction
    """
    if not ARCADE_API_KEY:
        logger.error("ARCADE_API_KEY not available for essay extraction")
        return {"error": "Arcade API key not configured"}
    
    arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
    
    # Create Arcade essay extraction agent
    async def get_tools(toolkits):
        from agents_arcade import get_arcade_tools
        return await get_arcade_tools(arcade_client, toolkits)
    
    extraction_agent = await create_arcade_essay_extraction_agent(arcade_client, get_tools)
    
    # Run comprehensive essay extraction
    extraction_prompt = f"""
Extract ALL essay requirements from this scholarship website: {scholarship_url}

Scholarship: {scholarship_name}

Use MapWebsite to discover all related pages, then ScrapeUrl to extract complete essay requirements.
Return detailed JSON with all prompts, requirements, and submission instructions.
"""
    
    from agents import Runner
    result = await Runner.run(
        starting_agent=extraction_agent,
        input=extraction_prompt,
        context={"user_id": user_id, "scholarship_pk": scholarship_pk}
    )
    
    # Parse the extraction results
    output = str(result.final_output)
    json_match = re.search(r'```json\s*([^`]*)\s*```', output, re.DOTALL)
    if json_match:
        extraction_data = json.loads(json_match.group(1))
    else:
        extraction_data = json.loads(output)
    
    # Save enhanced essay data
    if extraction_data.get("essay_requirements"):
        await task_save_essays(user_id, extraction_data["essay_requirements"])
        
    # Update progress
    await task_update_essay_extraction_progress(
        user_id=user_id,
        scholarship_pk=scholarship_pk,
        status=ProgressStatus.COMPLETED,
        pages_scraped=len(extraction_data.get("scholarship_info", {}).get("pages_scraped", [])),
        completeness_score=extraction_data.get("extraction_quality", {}).get("completeness_score", 0)
    )
    
    logger.info(f"Arcade essay extraction completed for {scholarship_name}: "
               f"{len(extraction_data.get('essay_requirements', []))} requirements found")
    
    return extraction_data

@celery_app.task(name="scholarship_monitoring_task", bind=True)
def scholarship_monitoring_task(self, target_sites: list, user_profiles: dict):
    """
    Proactive scholarship monitoring using Arcade tools
    """
    try:
        return async_to_sync(_scholarship_monitoring_async(target_sites, user_profiles))
    except Exception as e:
        logger.error(f"Scholarship monitoring failed: {str(e)}")
        self.retry(countdown=300, exc=e)  # Retry in 5 minutes

async def _scholarship_monitoring_async(target_sites: list, user_profiles: dict):
    """
    Monitor scholarship sites for new opportunities
    """
    if not ARCADE_API_KEY:
        logger.error("ARCADE_API_KEY not available for monitoring")
        return {"error": "Arcade API key not configured"}
    
    arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
    
    async def get_tools(toolkits):
        from agents_arcade import get_arcade_tools
        return await get_arcade_tools(arcade_client, toolkits)
    
    monitor_agent = await create_arcade_scholarship_monitor(arcade_client, get_tools)
    
    monitoring_prompt = f"""
Monitor these scholarship websites for new opportunities:
{json.dumps(target_sites, indent=2)}

User profiles to match against:
{json.dumps(user_profiles, indent=2)}

Use CrawlWebsite and MapWebsite to discover new scholarships and updates.
Return JSON with new opportunities found.
"""
    
    from agents import Runner
    result = await Runner.run(
        starting_agent=monitor_agent,
        input=monitoring_prompt,
        context={"monitoring_sites": target_sites}
    )
    
    # Parse monitoring results
    output = str(result.final_output)
    json_match = re.search(r'```json\s*([^`]*)\s*```', output, re.DOTALL)
    if json_match:
        monitoring_data = json.loads(json_match.group(1))
    else:
        monitoring_data = json.loads(output)
    
    logger.info(f"Scholarship monitoring completed: "
               f"{monitoring_data.get('monitoring_summary', {}).get('new_scholarships_found', 0)} new scholarships found")
    
    return monitoring_data 

@celery_app.task(name="extract_all_essays", bind=True, max_retries=1, default_retry_delay=300)
def extract_all_essays_task(self, user_id: str, timeline_session_id: str = None):
    """
    Celery task to extract essay prompts from ALL scholarships for a user.
    Provides real-time progress updates via Redis pub/sub with timeline integration.
    """
    logger.info(f"Starting bulk essay extraction for user {user_id}")
    
    try:
        result = async_to_sync(extract_all_essays_task_wrapper(user_id, timeline_session_id))
        logger.info(f"Bulk essay extraction completed for user {user_id}. Result: {result}")
        return result
    except Exception as e:
        logger.error(f"Unhandled exception in extract_all_essays_task for user {user_id}: {e}", exc_info=True)
        # Publish failure update
        if timeline_session_id:
            async_to_sync(publish_timeline_update(user_id, {
                "session_id": timeline_session_id,
                "operation": "bulk_essay_extraction",
                "status": "failed",
                "step": "error",
                "message": f"Bulk essay extraction failed: {str(e)}",
                "error": str(e)
            }))
        raise

async def extract_all_essays_task_wrapper(user_id: str, timeline_session_id: str = None):
    """
    Async implementation of bulk essay extraction with timeline updates
    """
    from services.database import fetch_scholarships
    from datetime import datetime
    
    # Initialize timeline tracking
    if timeline_session_id:
        await publish_timeline_update(user_id, {
            "session_id": timeline_session_id,
            "operation": "bulk_essay_extraction",
            "status": "started",
            "step": "initializing",
            "message": "Starting bulk essay extraction..."
        })
    
    try:
        # Step 1: Fetch all scholarships for the user
        await publish_timeline_update(user_id, {
            "session_id": timeline_session_id,
            "operation": "bulk_essay_extraction", 
            "status": "active",
            "step": "fetching_scholarships",
            "message": "Fetching your scholarships..."
        })
        
        user_scholarships = await fetch_scholarships(user_id)
        
        if not user_scholarships:
            result = {
                "status": "completed",
                "message": "No scholarships found for user",
                "total_processed": 0,
                "essays_found": 0,
                "errors": 0
            }
            
            if timeline_session_id:
                await publish_timeline_update(user_id, {
                    "session_id": timeline_session_id,
                    "operation": "bulk_essay_extraction",
                    "status": "completed",
                    "step": "completed",
                    "message": "No scholarships found to process",
                    "stats": result
                })
            
            return result
        
        # Filter out expired scholarships and those without URLs
        valid_scholarships = []
        for scholarship in user_scholarships:
            # Check if scholarship has required URL
            scholarship_url = scholarship.get("application_url") or scholarship.get("url")
            if not scholarship_url:
                continue
                
            # Check if deadline has expired
            deadline_str = scholarship.get('deadline')
            is_expired = False
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                    if deadline <= datetime.now(deadline.tzinfo):
                        is_expired = True
                except (ValueError, TypeError):
                    pass
            
            if not is_expired:
                valid_scholarships.append({
                    "scholarship": scholarship,
                    "url": scholarship_url,
                    "pk": scholarship.get("url") or scholarship.get("id", scholarship_url),
                    "name": scholarship.get("title", "Unknown Scholarship")
                })
        
        total_scholarships = len(valid_scholarships)
        logger.info(f"Found {total_scholarships} valid scholarships to process for user {user_id}")
        
        if total_scholarships == 0:
            result = {
                "status": "completed",
                "message": "No valid scholarships found (all may be expired or missing URLs)",
                "total_processed": 0,
                "essays_found": 0,
                "errors": 0
            }
            
            if timeline_session_id:
                await publish_timeline_update(user_id, {
                    "session_id": timeline_session_id,
                    "operation": "bulk_essay_extraction",
                    "status": "completed",
                    "step": "completed",
                    "message": "No valid scholarships to process (expired or missing URLs)",
                    "stats": result
                })
            
            return result
        
        # Step 2: Process scholarships in batches
        await publish_timeline_update(user_id, {
            "session_id": timeline_session_id,
            "operation": "bulk_essay_extraction",
            "status": "active", 
            "step": "processing_essays",
            "message": f"Processing {total_scholarships} scholarships...",
            "progress": 0,
            "total": total_scholarships
        })
        
        # Process with controlled concurrency
        import asyncio
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent extractions
        
        async def bounded_extraction(scholarship_data, index):
            async with semaphore:
                scholarship = scholarship_data["scholarship"]
                url = scholarship_data["url"] 
                pk = scholarship_data["pk"]
                name = scholarship_data["name"]
                
                try:
                    # Update progress
                    if timeline_session_id:
                        await publish_timeline_update(user_id, {
                            "session_id": timeline_session_id,
                            "operation": "bulk_essay_extraction",
                            "status": "active",
                            "step": "processing_essays", 
                            "message": f"Processing {name}...",
                            "progress": index,
                            "total": total_scholarships,
                            "current_scholarship": name
                        })
                    
                    # Extract essays for this scholarship
                    result = await extract_essays_task_wrapper(user_id, url, pk, name)
                    
                    # Add scholarship name to result for tracking
                    if isinstance(result, dict):
                        result["scholarship_name"] = name
                        
                    return result
                    
                except Exception as e:
                    logger.error(f"Error extracting essays for {name}: {e}")
                    return {
                        "status": "error",
                        "scholarship_pk": pk,
                        "scholarship_name": name,
                        "error": str(e),
                        "essays_found": 0
                    }
        
        # Execute all extractions
        extraction_tasks = [
            bounded_extraction(scholarship_data, index) 
            for index, scholarship_data in enumerate(valid_scholarships)
        ]
        
        results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        
        # Step 3: Analyze results
        await publish_timeline_update(user_id, {
            "session_id": timeline_session_id,
            "operation": "bulk_essay_extraction",
            "status": "active",
            "step": "analyzing_results", 
            "message": "Analyzing extraction results..."
        })
        
        successful_extractions = 0
        total_essays_found = 0
        error_count = 0
        error_details = []
        
        for result in results:
            if isinstance(result, dict):
                if result.get("status") == "success":
                    successful_extractions += 1
                    total_essays_found += result.get("essays_found", 0)
                elif result.get("status") == "error":
                    error_count += 1
                    error_details.append({
                        "scholarship": result.get("scholarship_name", "Unknown"),
                        "error": result.get("error", "Unknown error")
                    })
            else:
                # Exception was raised
                error_count += 1
                error_details.append({
                    "scholarship": "Unknown",
                    "error": str(result)
                })
        
        # Step 4: Final results
        final_result = {
            "status": "completed",
            "message": f"Bulk essay extraction completed! Processed {total_scholarships} scholarships, found {total_essays_found} essays.",
            "total_processed": total_scholarships,
            "successful_extractions": successful_extractions,
            "essays_found": total_essays_found,
            "errors": error_count,
            "error_details": error_details[:5] if error_details else [],  # Limit error details
            "completion_time": datetime.now().isoformat()
        }
        
        if timeline_session_id:
            await publish_timeline_update(user_id, {
                "session_id": timeline_session_id,
                "operation": "bulk_essay_extraction",
                "status": "completed",
                "step": "completed",
                "message": f"✅ Bulk extraction complete! Found {total_essays_found} essays from {successful_extractions}/{total_scholarships} scholarships.",
                "stats": final_result
            })
        
        logger.info(f"Bulk essay extraction completed for user {user_id}: {final_result}")
        return final_result
        
    except Exception as e:
        logger.error(f"Error in bulk essay extraction for user {user_id}: {e}", exc_info=True)
        
        error_result = {
            "status": "error",
            "message": f"Bulk essay extraction failed: {str(e)}",
            "error": str(e),
            "total_processed": 0,
            "essays_found": 0,
            "errors": 1
        }
        
        if timeline_session_id:
            await publish_timeline_update(user_id, {
                "session_id": timeline_session_id,
                "operation": "bulk_essay_extraction",
                "status": "failed",
                "step": "error",
                "message": f"Bulk essay extraction failed: {str(e)}",
                "error": str(e)
            })
        
        return error_result

async def publish_timeline_update(user_id: str, update_data: dict):
    """Publish timeline update via Redis pub/sub for real-time UI updates"""
    try:
        import redis.asyncio as redis
        import json
        import os
        
        REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(REDIS_URL)
        
        channel = f"timeline_updates:{user_id}"
        message = json.dumps(update_data)
        await redis_client.publish(channel, message)
        await redis_client.aclose()
        
        logger.info(f"Published timeline update for user {user_id}: {update_data.get('step', 'unknown')}")
    except Exception as e:
        logger.warning(f"Failed to publish timeline update for user {user_id}: {e}") 

async def task_save_essays(user_id: str, essay_prompts_for_one_scholarship: list):
    """Wrapper for save_essays that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await save_essays(pool, user_id, essay_prompts_for_one_scholarship)

async def task_save_failed_scrape(user_id: str, scholarship_pk: str, url: str, scholarship_name: str, error_message: str):
    """Wrapper for save_failed_scrape that handles pool management"""
    pool = _task_db_manager.get_pool()
    if not pool:
        # Try to initialize with the DATABASE_URL if pool is not available
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL:
            await _task_db_manager.initialize_pool(DATABASE_URL)
            pool = _task_db_manager.get_pool()
        if not pool:
            raise RuntimeError("Database pool not initialized in tasks")
    return await save_failed_scrape(pool, user_id, scholarship_pk, url, scholarship_name, error_message) 