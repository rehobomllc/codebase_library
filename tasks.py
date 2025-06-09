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
# or one level up if tasks.py is in a subdirectory of treatment_chat_app.
# Given that .env is in treatment_chat_app and tasks.py is also in treatment_chat_app.
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
celery_app = Celery("treatment_tasks", broker=REDIS_URL, backend=REDIS_URL)

# Import database save function
# This might cause a circular import if database.py imports tasks.py or celery_app from tasks
# A common pattern is to have db operations in their own module that both app.py and tasks.py can import
# For now, assuming direct import works or save_essays is accessible another way.
# From the prompt, it seems `save_essays` is in `services.database`
# Import database helpers from the local package (relative import ensures the
# module is found whether or not the project root is on PYTHONPATH).
# Import database helpers. When the module is imported as
# `treatment_chat_app.tasks`, the relative path works. If the module is
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
    from .treatment_agents.essay_extractor import create_essay_extractor  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from treatment_agents.essay_extractor import create_essay_extractor  # noqa: F401

# Import enhanced Arcade agents
try:
    from .treatment_agents.validation_agent_v2_arcade import (
        enhanced_validation_with_arcade,
        validate_candidates_concurrent,
        create_arcade_essay_extraction_agent,
        create_arcade_treatment_monitor,
    )  # type: ignore
except ImportError:  # pragma: no cover – fallback for direct execution
    from treatment_agents.validation_agent_v2_arcade import (
        enhanced_validation_with_arcade,
        validate_candidates_concurrent,
        create_arcade_essay_extraction_agent,
        create_arcade_treatment_monitor
    )  # noqa: F401

# Import database manager
try:
    from .services.database import DatabaseManager
except ImportError:  # pragma: no cover – fallback for direct execution
    from services.database import DatabaseManager

# Create a global database manager instance for tasks
_task_db_manager = DatabaseManager()

# Helper functions to handle database pool for progress tracking
async def task_init_essay_extraction_progress(user_id: str, total_treatments: int):
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
    return await init_essay_extraction_progress(pool, user_id, total_treatments)

async def task_update_essay_extraction_progress(user_id: str, treatment_pk: str, status: str, **kwargs):
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
    return await update_essay_extraction_progress(pool, user_id, treatment_pk, status, **kwargs)

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

async def web_search_for_treatment_application(user_id: str, treatment_name: str, provider: str, arcade_client) -> Optional[Dict[str, Any]]:
    """
    Search the web for a treatment's actual application page when the original URL fails.
    Uses multiple creative strategies to bypass login walls and access requirements.
    Returns the best match with URL and content summary, or None if not found.
    """
    logger.info(f"Starting enhanced web search fallback for treatment: {treatment_name}")
    
    # Generate comprehensive search queries using multiple strategies
    search_queries = []
    
    # Strategy 1: Provider-specific search (if available)
    if provider and provider.lower() != 'unknown':
        search_queries.extend([
            f"{treatment_name} application {provider}",
            f'"{treatment_name}" apply site:{provider}',
            f'site:{provider} "{treatment_name}" requirements'
        ])
    
    # Strategy 2: Archive and cache services (bypass login walls)
    search_queries.extend([
        f'site:web.archive.org "{treatment_name}" application',
        f'site:archive.today "{treatment_name}" requirements',
        f'site:webcitation.org "{treatment_name}" application'
    ])
    
    # Strategy 3: Document search (PDFs often bypass login)
    search_queries.extend([
        f'"{treatment_name}" filetype:pdf application',
        f'"{treatment_name}" filetype:doc requirements',
        f'"{treatment_name}" treatment guidelines filetype:pdf'
    ])
    
    # Strategy 4: Community and forum sources (patients share requirements)
    search_queries.extend([
        f'"{treatment_name}" site:reddit.com application requirements',
        f'"{treatment_name}" site:healthboards.com essays',
        f'"{treatment_name}" application questions reddit'
    ])
    
    # Strategy 5: Medical aggregator sites
    search_queries.extend([
        f'"{treatment_name}" site:healthline.com',
        f'"{treatment_name}" site:webmd.com',
        f'"{treatment_name}" site:mayoclinic.org',
        f'"{treatment_name}" site:medlineplus.gov'
    ])
    
    # Strategy 6: Government and public databases
    search_queries.extend([
        f'"{treatment_name}" site:clinicaltrials.gov',
        f'"{treatment_name}" site:cdc.gov',
        f'"{treatment_name}" site:nih.gov'
    ])
    
    # Strategy 7: General application-focused searches
    search_queries.extend([
        f'"{treatment_name}" application form requirements',
        f"{treatment_name} apply online requirements", 
        f"{treatment_name} treatment application portal"
    ])
    
    logger.info(f"Generated {len(search_queries)} enhanced search queries for {treatment_name}")
    
    try:
        # Try each search query until we find a good result
        for i, query in enumerate(search_queries):
            logger.info(f"Attempting search query {i+1}/{len(search_queries)}: {query}")
            
            try:
                search_result = await arcade_client.tools.execute(
                    tool_name="GoogleTreatmentSearchTool",
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
                    
                    if any(community in url.lower() for community in ['reddit.com', 'healthboards.com', 'patientslikeme.com']):
                        relevance_score += 10  # Community source bonus
                        logger.info(f"Community source bonus for: {url}")
                    
                    if any(aggregator in url.lower() for aggregator in ['healthline.com', 'webmd.com', 'mayoclinic.org']):
                        relevance_score += 12  # Medical aggregator bonus
                        logger.info(f"Medical aggregator source bonus for: {url}")
                    
                    if any(gov in url.lower() for gov in ['.gov', 'clinicaltrials.gov', 'cdc.gov', 'nih.gov']):
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
                    
                    # Treatment name match (very high priority)
                    name_words = treatment_name.lower().split()
                    for word in name_words:
                        if len(word) > 2 and word in content_text:
                            relevance_score += 20  # Reduced from 25 to balance with source bonuses
                    
                    # URL indicators of application pages
                    url_application_indicators = [
                        "application", "apply", "form", "treatment",
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
                                logger.info(f"Document URL found for {treatment_name}: {url} (score: {relevance_score})")
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
                                    "required documents", "application form", "treatment guidelines"
                                ]
                                for indicator in strong_indicators:
                                    if indicator in summary_text:
                                        page_score += 15  # Reduced from 20
                                
                                # Lower final threshold for alternative sources
                                final_threshold = 40 if any(alt in url.lower() for alt in ['archive.org', '.gov', 'reddit.com', 'healthline.com']) else 50
                                if page_score >= final_threshold:
                                    source_type = "archive" if "archive" in url.lower() else \
                                                "government" if ".gov" in url.lower() else \
                                                "community" if any(c in url.lower() for c in ['reddit.com', 'healthboards.com']) else \
                                                "aggregator" if any(a in url.lower() for a in ['healthline.com', 'webmd.com']) else \
                                                "standard"
                                    
                                    logger.info(f"Found suitable application page for {treatment_name}: {url} (score: {page_score}, type: {source_type})")
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
        
        logger.warning(f"No suitable application page found for {treatment_name} after trying {len(search_queries)} enhanced queries")
        return None
        
    except Exception as e:
        logger.error(f"Error in enhanced web search fallback for {treatment_name}: {e}")
        return None 

async def publish_progress_update(user_id: str, progress_data: dict):
    """Publish progress update to Redis pub/sub channel."""
    try:
        channel = f"user:{user_id}:progress"
        await redis_client.publish(channel, json.dumps(progress_data))
        logger.info(f"Published progress update to {channel}: {progress_data}")
    except Exception as e:
        logger.error(f"Failed to publish progress update for user {user_id}: {e}")

async def publish_treatment_progress(user_id: str, treatment_pk: str, status: str, **kwargs):
    """
    Helper function to publish progress updates for individual treatments.
    
    Args:
        user_id: User identifier
        treatment_pk: Treatment identifier  
        status: Current status (queued, in_progress, completed, failed)
        **kwargs: Additional metadata like error messages, extracted essays, etc.
    """
    try:
        progress_data = {
            "type": "treatment_progress",
            "treatment_pk": treatment_pk,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        }
        
        # Update database progress tracking
        await task_update_essay_extraction_progress(user_id, treatment_pk, status, **kwargs)
        
        # Publish to Redis for real-time updates
        await publish_progress_update(user_id, progress_data)
        
    except Exception as e:
        logger.error(f"Failed to publish treatment progress for {treatment_pk}: {e}")

# ---- Task Functions (Celery tasks) ----

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def process_treatments_batch(self, user_id: str, treatment_data_list: list) -> dict:
    """
    Enhanced essay extraction task using Arcade agents.
    Processes a batch of treatments and extracts essay requirements.
    
    Args:
        user_id: User identifier for progress tracking
        treatment_data_list: List of treatment data dictionaries
        
    Returns:
        Dictionary with success/failure results and progress information
    """
    async def _async_process_treatments():
        logger.info(f"Starting essay extraction for {len(treatment_data_list)} treatments (user: {user_id})")
        
        try:
            # Initialize progress tracking
            await task_init_essay_extraction_progress(user_id, len(treatment_data_list))
            
            # Initialize Arcade client
            if not ARCADE_API_KEY:
                error_msg = "ARCADE_API_KEY not configured - cannot proceed with essay extraction"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
            
            # Track results
            successful_extractions = []
            failed_extractions = []
            
            # Process each treatment
            for treatment_data in treatment_data_list:
                treatment_pk = treatment_data.get('treatment_pk')
                treatment_name = treatment_data.get('name', 'Unknown Treatment')
                treatment_url = treatment_data.get('treatment_url')
                
                if not treatment_pk:
                    logger.warning(f"Skipping treatment without treatment_pk: {treatment_data}")
                    continue
                
                logger.info(f"Processing treatment: {treatment_name} (ID: {treatment_pk})")
                
                # Update status to in_progress
                await publish_treatment_progress(
                    user_id, 
                    treatment_pk, 
                    ProgressStatus.IN_PROGRESS,
                    treatment_name=treatment_name,
                    current_step="initializing"
                )
                
                try:
                    # Step 1: Try to extract essays from the original URL
                    extracted_essays = None
                    original_url_success = False
                    
                    if treatment_url:
                        logger.info(f"Attempting essay extraction from original URL: {treatment_url}")
                        
                        await publish_treatment_progress(
                            user_id,
                            treatment_pk,
                            ProgressStatus.IN_PROGRESS,
                            treatment_name=treatment_name,
                            current_step="extracting_from_original_url",
                            url=treatment_url
                        )
                        
                        try:
                            extraction_result = await create_arcade_essay_extraction_agent(
                                treatment_name=treatment_name,
                                treatment_url=treatment_url,
                                arcade_client=arcade_client,
                                user_id=user_id
                            )
                            
                            if extraction_result and extraction_result.get("success"):
                                extracted_essays = extraction_result.get("extracted_essays", [])
                                if extracted_essays:
                                    original_url_success = True
                                    logger.info(f"Successfully extracted {len(extracted_essays)} essays from original URL")
                                else:
                                    logger.warning(f"No essays found at original URL for {treatment_name}")
                            else:
                                logger.warning(f"Essay extraction failed for original URL: {extraction_result.get('error', 'Unknown error')}")
                        
                        except Exception as url_error:
                            logger.warning(f"Error extracting from original URL {treatment_url}: {url_error}")
                    
                    # Step 2: If original URL failed, try web search fallback
                    if not original_url_success:
                        logger.info(f"Original URL extraction failed, trying web search fallback for {treatment_name}")
                        
                        await publish_treatment_progress(
                            user_id,
                            treatment_pk,
                            ProgressStatus.IN_PROGRESS,
                            treatment_name=treatment_name,
                            current_step="searching_alternative_sources"
                        )
                        
                        # Use enhanced web search to find alternative application pages
                        provider = treatment_data.get('provider', '')
                        search_result = await web_search_for_treatment_application(
                            user_id=user_id,
                            treatment_name=treatment_name,
                            provider=provider,
                            arcade_client=arcade_client
                        )
                        
                        if search_result:
                            alternative_url = search_result.get("url")
                            logger.info(f"Found alternative URL for {treatment_name}: {alternative_url}")
                            
                            await publish_treatment_progress(
                                user_id,
                                treatment_pk,
                                ProgressStatus.IN_PROGRESS,
                                treatment_name=treatment_name,
                                current_step="extracting_from_alternative_url",
                                url=alternative_url
                            )
                            
                            try:
                                extraction_result = await create_arcade_essay_extraction_agent(
                                    treatment_name=treatment_name,
                                    treatment_url=alternative_url,
                                    arcade_client=arcade_client,
                                    user_id=user_id
                                )
                                
                                if extraction_result and extraction_result.get("success"):
                                    extracted_essays = extraction_result.get("extracted_essays", [])
                                    if extracted_essays:
                                        logger.info(f"Successfully extracted {len(extracted_essays)} essays from alternative URL")
                                    else:
                                        logger.warning(f"No essays found at alternative URL for {treatment_name}")
                                else:
                                    logger.warning(f"Essay extraction failed for alternative URL: {extraction_result.get('error', 'Unknown error')}")
                            
                            except Exception as alt_error:
                                logger.warning(f"Error extracting from alternative URL {alternative_url}: {alt_error}")
                        else:
                            logger.warning(f"No alternative URL found for {treatment_name}")
                    
                    # Step 3: Save results
                    if extracted_essays:
                        await publish_treatment_progress(
                            user_id,
                            treatment_pk,
                            ProgressStatus.IN_PROGRESS,
                            treatment_name=treatment_name,
                            current_step="saving_results"
                        )
                        
                        # Save essays to database (assuming save_essays function exists)
                        save_result = await save_essays(treatment_pk, extracted_essays)
                        
                        if save_result:
                            successful_extractions.append({
                                "treatment_pk": treatment_pk,
                                "treatment_name": treatment_name,
                                "essay_count": len(extracted_essays),
                                "essays": extracted_essays
                            })
                            
                            await publish_treatment_progress(
                                user_id,
                                treatment_pk,
                                ProgressStatus.COMPLETED,
                                treatment_name=treatment_name,
                                essay_count=len(extracted_essays),
                                essays=extracted_essays
                            )
                            
                            logger.info(f"Successfully processed treatment {treatment_name}: {len(extracted_essays)} essays extracted")
                        else:
                            raise Exception("Failed to save essays to database")
                    else:
                        # No essays found anywhere
                        failed_extractions.append({
                            "treatment_pk": treatment_pk,
                            "treatment_name": treatment_name,
                            "error": "No essays found after trying original URL and web search fallback"
                        })
                        
                        await publish_treatment_progress(
                            user_id,
                            treatment_pk,
                            ProgressStatus.FAILED,
                            treatment_name=treatment_name,
                            error="No essays found after exhaustive search"
                        )
                        
                        logger.warning(f"No essays found for treatment {treatment_name} after all attempts")
                
                except Exception as treatment_error:
                    error_msg = f"Error processing treatment {treatment_name}: {str(treatment_error)}"
                    logger.error(error_msg)
                    
                    failed_extractions.append({
                        "treatment_pk": treatment_pk,
                        "treatment_name": treatment_name,
                        "error": error_msg
                    })
                    
                    await publish_treatment_progress(
                        user_id,
                        treatment_pk,
                        ProgressStatus.FAILED,
                        treatment_name=treatment_name,
                        error=error_msg
                    )
            
            # Final summary
            total_processed = len(successful_extractions) + len(failed_extractions)
            success_rate = (len(successful_extractions) / total_processed * 100) if total_processed > 0 else 0
            
            final_result = {
                "success": True,
                "total_treatments": len(treatment_data_list),
                "successful_extractions": len(successful_extractions),
                "failed_extractions": len(failed_extractions),
                "success_rate": success_rate,
                "results": {
                    "successful": successful_extractions,
                    "failed": failed_extractions
                }
            }
            
            # Publish final summary
            await publish_progress_update(user_id, {
                "type": "batch_complete",
                "summary": final_result,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Batch processing complete for user {user_id}: {len(successful_extractions)}/{total_processed} treatments successful")
            return final_result
            
        except Exception as e:
            error_msg = f"Critical error in essay extraction batch: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # Clear progress on critical failure
            try:
                await task_clear_essay_extraction_progress(user_id)
            except:
                pass
            
            return {
                "success": False,
                "error": error_msg,
                "total_treatments": len(treatment_data_list),
                "successful_extractions": 0,
                "failed_extractions": len(treatment_data_list)
            }
    
    # Run the async function
    return async_to_sync(_async_process_treatments()) 

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2}, retry_backoff=True)
def validate_treatments_task(self, user_id: str, treatments: list) -> dict:
    """
    Enhanced treatment validation task using Arcade agents.
    Validates treatment data and eligibility requirements.
    
    Args:
        user_id: User identifier for progress tracking
        treatments: List of treatment dictionaries to validate
        
    Returns:
        Dictionary with validation results
    """
    async def _async_validate_treatments():
        logger.info(f"Starting validation for {len(treatments)} treatments (user: {user_id})")
        
        try:
            # Initialize Arcade client
            if not ARCADE_API_KEY:
                error_msg = "ARCADE_API_KEY not configured - cannot proceed with validation"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
            
            # Perform concurrent validation
            validation_result = await validate_candidates_concurrent(
                treatment_candidates=treatments,
                arcade_client=arcade_client,
                user_id=user_id
            )
            
            logger.info(f"Validation complete for user {user_id}: {len(validation_result.get('validated_treatments', []))} treatments validated")
            return validation_result
            
        except Exception as e:
            error_msg = f"Critical error in treatment validation: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg,
                "total_treatments": len(treatments),
                "validated_treatments": []
            }
    
    # Run the async function
    return async_to_sync(_async_validate_treatments())

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2}, retry_backoff=True)
def monitor_treatment_site_task(self, treatment_url: str, treatment_name: str) -> dict:
    """
    Task to monitor a treatment site for changes using Arcade monitoring agents.
    
    Args:
        treatment_url: URL of the treatment to monitor
        treatment_name: Name of the treatment
        
    Returns:
        Dictionary with monitoring results
    """
    async def _async_monitor_treatment():
        logger.info(f"Starting monitoring for treatment: {treatment_name} at {treatment_url}")
        
        try:
            # Initialize Arcade client
            if not ARCADE_API_KEY:
                error_msg = "ARCADE_API_KEY not configured - cannot proceed with monitoring"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
            
            # Create and run monitoring agent
            monitoring_result = await create_arcade_treatment_monitor(
                treatment_name=treatment_name,
                treatment_url=treatment_url,
                arcade_client=arcade_client
            )
            
            logger.info(f"Monitoring complete for {treatment_name}: {monitoring_result}")
            return monitoring_result
            
        except Exception as e:
            error_msg = f"Critical error in treatment monitoring: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg,
                "treatment_name": treatment_name,
                "treatment_url": treatment_url
            }
    
    # Run the async function
    return async_to_sync(_async_monitor_treatment())

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1}, retry_backoff=True)
def get_progress_task(self, user_id: str) -> dict:
    """
    Task to get current essay extraction progress for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dictionary with current progress information
    """
    async def _async_get_progress():
        try:
            progress = await task_get_essay_extraction_progress(user_id)
            return {"success": True, "progress": progress}
            
        except Exception as e:
            error_msg = f"Error getting progress for user {user_id}: {str(e)}"
            logger.error(error_msg)
            
            return {
                "success": False,
                "error": error_msg,
                "progress": None
            }
    
    # Run the async function
    return async_to_sync(_async_get_progress())

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1}, retry_backoff=True)
def clear_progress_task(self, user_id: str) -> dict:
    """
    Task to clear essay extraction progress for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dictionary with operation result
    """
    async def _async_clear_progress():
        try:
            await task_clear_essay_extraction_progress(user_id)
            return {"success": True, "message": f"Progress cleared for user {user_id}"}
            
        except Exception as e:
            error_msg = f"Error clearing progress for user {user_id}: {str(e)}"
            logger.error(error_msg)
            
            return {
                "success": False,
                "error": error_msg
            }
    
    # Run the async function
    return async_to_sync(_async_clear_progress())

# ---- Utility Functions ----

def start_treatment_batch_processing(user_id: str, treatment_data_list: list) -> str:
    """
    Start async batch processing of treatments for essay extraction.
    
    Args:
        user_id: User identifier for progress tracking
        treatment_data_list: List of treatment dictionaries
        
    Returns:
        Task ID for tracking the job
    """
    try:
        task = process_treatments_batch.delay(user_id, treatment_data_list)
        logger.info(f"Started treatment batch processing for user {user_id}: task_id={task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to start treatment batch processing for user {user_id}: {e}")
        raise

def start_treatment_validation(user_id: str, treatments: list) -> str:
    """
    Start async validation of treatments.
    
    Args:
        user_id: User identifier
        treatments: List of treatment dictionaries to validate
        
    Returns:
        Task ID for tracking the job
    """
    try:
        task = validate_treatments_task.delay(user_id, treatments)
        logger.info(f"Started treatment validation for user {user_id}: task_id={task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to start treatment validation for user {user_id}: {e}")
        raise

def start_treatment_monitoring(treatment_url: str, treatment_name: str) -> str:
    """
    Start async monitoring of a treatment site.
    
    Args:
        treatment_url: URL of the treatment to monitor
        treatment_name: Name of the treatment
        
    Returns:
        Task ID for tracking the job
    """
    try:
        task = monitor_treatment_site_task.delay(treatment_url, treatment_name)
        logger.info(f"Started treatment monitoring for {treatment_name}: task_id={task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to start treatment monitoring for {treatment_name}: {e}")
        raise

def get_user_progress(user_id: str) -> str:
    """
    Get current essay extraction progress for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Task ID for tracking the job
    """
    try:
        task = get_progress_task.delay(user_id)
        logger.info(f"Started progress retrieval for user {user_id}: task_id={task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to get progress for user {user_id}: {e}")
        raise

def clear_user_progress(user_id: str) -> str:
    """
    Clear essay extraction progress for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Task ID for tracking the job
    """
    try:
        task = clear_progress_task.delay(user_id)
        logger.info(f"Started progress clearing for user {user_id}: task_id={task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to clear progress for user {user_id}: {e}")
        raise

# ---- Background Monitoring ----

@celery_app.task(bind=True)
def periodic_treatment_monitoring(self):
    """
    Periodic task to monitor treatment sites for changes.
    This would typically be scheduled to run daily or weekly.
    """
    async def _async_periodic_monitoring():
        logger.info("Starting periodic treatment monitoring")
        
        try:
            # Get list of treatments to monitor from database
            # This would need to be implemented based on your database schema
            treatments_to_monitor = []  # Placeholder - get from database
            
            if not treatments_to_monitor:
                logger.info("No treatments found for monitoring")
                return {"success": True, "monitored_count": 0}
            
            # Initialize Arcade client
            if not ARCADE_API_KEY:
                logger.warning("ARCADE_API_KEY not configured - skipping periodic monitoring")
                return {"success": False, "error": "ARCADE_API_KEY not configured"}
            
            arcade_client = AsyncArcade(api_key=ARCADE_API_KEY)
            
            monitoring_results = []
            
            # Monitor each treatment
            for treatment in treatments_to_monitor:
                treatment_name = treatment.get('name', 'Unknown')
                treatment_url = treatment.get('url', '')
                
                if not treatment_url:
                    continue
                
                try:
                    logger.info(f"Monitoring treatment: {treatment_name}")
                    
                    result = await create_arcade_treatment_monitor(
                        treatment_name=treatment_name,
                        treatment_url=treatment_url,
                        arcade_client=arcade_client
                    )
                    
                    monitoring_results.append({
                        "treatment_name": treatment_name,
                        "treatment_url": treatment_url,
                        "result": result
                    })
                    
                except Exception as e:
                    logger.error(f"Error monitoring treatment {treatment_name}: {e}")
                    monitoring_results.append({
                        "treatment_name": treatment_name,
                        "treatment_url": treatment_url,
                        "error": str(e)
                    })
            
            logger.info(f"Periodic monitoring complete: {len(monitoring_results)} treatments processed")
            return {
                "success": True,
                "monitored_count": len(monitoring_results),
                "results": monitoring_results
            }
            
        except Exception as e:
            error_msg = f"Critical error in periodic monitoring: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg,
                "monitored_count": 0
            }
    
    # Run the async function
    return async_to_sync(_async_periodic_monitoring())

# ---- Error Handling and Logging ----

@celery_app.task(bind=True)
def cleanup_failed_extractions(self):
    """
    Periodic task to clean up failed essay extractions and retry if appropriate.
    """
    async def _async_cleanup():
        logger.info("Starting cleanup of failed extractions")
        
        try:
            # Get failed extractions from database
            # This would need to be implemented based on your database schema
            failed_extractions = []  # Placeholder - get from database
            
            cleaned_count = 0
            
            for failed_extraction in failed_extractions:
                treatment_pk = failed_extraction.get('treatment_pk')
                failure_reason = failed_extraction.get('error', '')
                failure_time = failed_extraction.get('failed_at')
                
                # Implement cleanup logic based on failure reason and time
                # For example, retry certain types of failures, or clean up old entries
                
                logger.info(f"Cleaned up failed extraction for treatment {treatment_pk}")
                cleaned_count += 1
            
            logger.info(f"Cleanup complete: {cleaned_count} failed extractions processed")
            return {
                "success": True,
                "cleaned_count": cleaned_count
            }
            
        except Exception as e:
            error_msg = f"Error in cleanup task: {str(e)}"
            logger.error(error_msg)
            
            return {
                "success": False,
                "error": error_msg,
                "cleaned_count": 0
            }
    
    # Run the async function
    return async_to_sync(_async_cleanup())

# Configure Celery beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'periodic-treatment-monitoring': {
        'task': 'tasks.periodic_treatment_monitoring',
        'schedule': 86400.0,  # Run daily (24 hours)
    },
    'cleanup-failed-extractions': {
        'task': 'tasks.cleanup_failed_extractions',
        'schedule': 604800.0,  # Run weekly (7 days)
    },
}

celery_app.conf.timezone = 'UTC'

# ---- Module Initialization ----

logger.info("Treatment tasks module initialized successfully")
logger.info(f"ARCADE_API_KEY configured: {bool(ARCADE_API_KEY)}")
logger.info(f"OPENAI_API_KEY configured: {bool(OPENAI_API_KEY)}")
logger.info(f"Redis URL: {REDIS_URL}")

# Export main functions for use by other modules
__all__ = [
    'start_treatment_batch_processing',
    'start_treatment_validation', 
    'start_treatment_monitoring',
    'get_user_progress',
    'clear_user_progress',
    'process_treatments_batch',
    'validate_treatments_task',
    'monitor_treatment_site_task',
    'web_search_for_treatment_application',
    'publish_treatment_progress',
    'ProgressStatus'
] 