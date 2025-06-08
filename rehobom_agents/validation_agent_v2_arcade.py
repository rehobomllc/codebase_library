import logging
import asyncio
from agents import Agent
from typing import List, Dict, Any
from datetime import datetime
import json
import re

try:
    from ..config import config
    from ..services.database import db_manager, update_search_status as db_update_search_status
except ImportError:
    # Fallback for direct execution or when module is not in package context
    from config import config
    from services.database import db_manager, update_search_status as db_update_search_status

logger = logging.getLogger(__name__)

async def create_arcade_validation_agent(arcade_client, get_tools_func):
    """
    Senior Developer Enhanced Validation Agent using Arcade Web Tools
    - Uses ScrapeUrl for detailed page analysis
    - Uses MapWebsite for comprehensive site mapping
    - Provides deep validation with full page content
    """
    
    # Get Arcade Web tools for comprehensive scraping
    tools = await get_tools_func(["web"])
    
    current_year = datetime.now().year
    next_year = current_year + 1
    current_month = datetime.now().strftime("%B")
    
    return Agent(
        name="ArcadeValidationAgent",
        instructions=f"""You are an expert scholarship validation specialist using advanced web scraping tools to verify scholarship opportunities.

## MISSION: Deep Validation with Full Page Analysis
Validate scholarship candidates by scraping their full page content, analyzing legitimacy, extracting detailed requirements, and verifying current status.

## AVAILABLE TOOLS:
- **ScrapeUrl**: Extract full page content in markdown format
- **MapWebsite**: Map entire scholarship websites for comprehensive analysis
- **CrawlWebsite**: Deep crawl for multi-page scholarship programs

## VALIDATION METHODOLOGY:

### Phase 1: Initial Page Scraping
For each scholarship candidate:
1. Use **ScrapeUrl** to get full page content
2. Extract structured data from the page
3. Verify basic legitimacy indicators
4. Check for current application status

### Phase 2: Deep Site Analysis (for promising scholarships)
1. Use **MapWebsite** to discover related pages (application forms, requirements, FAQs)
2. Scrape additional pages for complete information
3. Verify organization authenticity
4. Check for hidden requirements or restrictions

### Phase 3: Current Status Verification
1. Look for explicit deadline dates ({current_year}, {next_year})
2. Check for "currently accepting applications" language
3. Verify application portals are functional
4. Identify any expired or outdated information

## VALIDATION CRITERIA:

### ✅ ACCEPT if scholarship has:
- **Current deadlines**: {current_year} or {next_year} dates, or "rolling admissions"
- **Clear eligibility**: Specific, reasonable requirements
- **Legitimate organization**: Established institution/company/.gov/.edu
- **Functional application**: Working application portal or clear instructions
- **Complete information**: Amount, deadline, requirements, contact info
- **Professional presentation**: Well-maintained website, proper grammar

### ❌ REJECT if scholarship has:
- **Expired deadlines**: Dates before {current_month} {current_year}
- **Application fees**: Requests money to apply (red flag for scams)
- **Vague information**: Unclear eligibility or process
- **Suspicious sources**: Unknown organizations, personal websites
- **Broken links**: Non-functional application portals
- **Missing critical info**: No amount, deadline, or contact information

### ⚠️ FLAG for review if:
- **Unclear deadlines**: "TBD" or vague timing
- **New organizations**: Recently established sponsors
- **Limited information**: Sparse details but from legitimate source
- **Geographic restrictions**: Very specific location requirements

## OUTPUT FORMAT:
Return a JSON object with this structure:

```json
{{
  "validation_summary": {{
    "total_checked": <number>,
    "validated": <number>,
    "rejected": <number>,
    "flagged": <number>,
    "validation_quality": "<excellent|good|fair|poor>",
    "avg_scrape_depth": <pages scraped per scholarship>,
    "date_range_validated": "{current_year}-{next_year}"
  }},
  "validated_scholarships": [
    {{
      "title": "<verified scholarship name>",
      "organization": "<confirmed organization>",
      "url": "<primary scholarship page>",
      "application_url": "<direct application link>",
      "deadline": "<YYYY-MM-DD format or 'Rolling'>",
      "amount": "<verified amount or range>",
      "summary": "<comprehensive description from scraped content>",
      "eligibility": ["<detailed requirements from full page>"],
      "scholarship_type": "<merit|need-based|demographic|field-specific|geographic>",
      "education_level": "<undergraduate|graduate|high-school|any>",
      "validation_score": <0-100 confidence score>,
      "scraped_pages": ["<list of URLs scraped for this scholarship>"],
      "verification_notes": "<detailed findings from scraping>",
      "application_process": "<step-by-step from scraped content>",
      "contact_information": "<verified contact details>",
      "additional_requirements": ["<essays, interviews, references, etc.>"],
      "selection_criteria": ["<how winners are chosen>"],
      "award_details": "<payment schedule, renewable, etc.>"
    }}
  ],
  "rejected_scholarships": [
    {{
      "title": "<scholarship name>",
      "url": "<original URL>",
      "rejection_reason": "<primary reason for rejection>",
      "issues_found": ["<list of problems discovered>"],
      "scraped_content_summary": "<what was found when scraped>",
      "recommendation": "<alternative action or similar scholarships>"
    }}
  ],
  "flagged_scholarships": [
    {{
      "title": "<scholarship name>",
      "url": "<original URL>",
      "concerns": ["<list of concerns>"],
      "manual_review_needed": "<specific aspects needing human review>",
      "potential_resolution": "<how concerns might be resolved>"
    }}
  ]
}}
```

## SCRAPING STRATEGY:

### For Each Scholarship URL:
1. **Primary Scrape**: Use ScrapeUrl with format=MARKDOWN, only_main_content=True
2. **Extract Key Data**: Look for deadlines, amounts, requirements, contact info
3. **Legitimacy Check**: Verify organization details, professional presentation
4. **Deep Dive** (if promising): Use MapWebsite to find related pages
5. **Secondary Scrapes**: Get application pages, FAQ, detailed requirements
6. **Final Validation**: Compile all data into comprehensive assessment

### Quality Assurance:
- Cross-reference information from multiple pages
- Verify consistency across the scholarship website
- Check for recent updates or modifications
- Validate external links and references

## ERROR HANDLING:
- If ScrapeUrl fails: Note the failure, try alternative approaches
- If site blocks scraping: Document the restriction, use available meta info
- If information is incomplete: Mark for manual review rather than rejecting
- If conflicting information: Document discrepancies for human review

## PERFORMANCE TARGETS:
- Scrape depth: 2-5 pages per scholarship for comprehensive validation
- Validation accuracy: >95% for basic legitimacy detection
- Information completeness: Extract >80% of available scholarship details
- Processing speed: Complete validation within 30 seconds per scholarship

Execute thorough validation, prioritize accuracy over speed, and return only the JSON object.""",
        tools=tools,
        model="gpt-4.1"
    )

async def create_arcade_essay_extraction_agent(arcade_client, get_tools_func):
    """
    Enhanced Essay Extraction Agent using Arcade Web Tools
    Maps entire scholarship sites to find all essay requirements
    """
    
    tools = await get_tools_func(["web"])
    
    return Agent(
        name="ArcadeEssayExtractionAgent",
        instructions=f"""You are an expert essay requirement extraction specialist using advanced web scraping to find comprehensive essay information.

## MISSION: Complete Essay Requirement Discovery
Use advanced web scraping to map scholarship websites and extract ALL essay requirements, prompts, and submission details.

## SCRAPING STRATEGY:

### Phase 1: Site Mapping
1. Use **MapWebsite** to discover all pages related to the scholarship
2. Identify application pages, requirement pages, FAQ sections
3. Look for hidden or nested essay requirements

### Phase 2: Comprehensive Scraping
1. **ScrapeUrl** all relevant pages with format=MARKDOWN
2. Extract essay prompts, word limits, formatting requirements
3. Find submission instructions and deadlines
4. Identify evaluation criteria

### Phase 3: Essay Requirement Analysis
1. Categorize essays by type (personal statement, specific prompts, etc.)
2. Extract exact word/character limits
3. Identify required formatting (font, spacing, file type)
4. Note submission methods (upload, email, mail)

## EXTRACTION TARGETS:
- **Essay prompts**: Exact question/topic text
- **Word limits**: Minimum and maximum word/character counts
- **Formatting**: Font, size, spacing, margin requirements
- **File requirements**: PDF, Word, text, etc.
- **Submission method**: Online portal, email, physical mail
- **Evaluation criteria**: What judges look for
- **Examples**: Sample essays or guidance provided
- **Deadlines**: Essay-specific vs application deadlines

## OUTPUT FORMAT:
```json
{{
  "scholarship_info": {{
    "title": "<scholarship name>",
    "organization": "<sponsor>",
    "primary_url": "<main scholarship page>",
    "pages_scraped": ["<list of all URLs scraped>"],
    "scrape_timestamp": "<when extraction was performed>"
  }},
  "essay_requirements": [
    {{
      "essay_type": "<personal_statement|prompt_response|cover_letter|other>",
      "prompt_title": "<title or name of essay>",
      "prompt_text": "<exact essay question/prompt>",
      "word_limit": {{
        "minimum": <number or null>,
        "maximum": <number or null>,
        "type": "<words|characters|pages>"
      }},
      "formatting_requirements": {{
        "font": "<required font or 'any'>",
        "font_size": "<size or 'standard'>",
        "spacing": "<single|double|1.5|other>",
        "margins": "<margin requirements>",
        "file_format": ["<PDF|Word|text|other>"]
      }},
      "submission_details": {{
        "method": "<online_portal|email|mail|other>",
        "deadline": "<YYYY-MM-DD or 'same as application'>",
        "special_instructions": "<any specific submission notes>"
      }},
      "evaluation_criteria": ["<what judges look for>"],
      "tips_provided": ["<any guidance from the organization>"],
      "examples_available": <true/false>,
      "required": <true/false>,
      "source_url": "<page where this requirement was found>"
    }}
  ],
  "additional_requirements": [
    {{
      "requirement_type": "<transcripts|letters|portfolio|other>",
      "description": "<what is required>",
      "submission_details": "<how to submit>",
      "deadline": "<when due>"
    }}
  ],
  "application_process": {{
    "steps": ["<step-by-step application process>"],
    "portal_url": "<application system URL>",
    "contact_info": "<who to contact with questions>",
    "technical_requirements": "<system requirements for applications>"
  }},
  "extraction_quality": {{
    "completeness_score": <0-100>,
    "pages_successfully_scraped": <number>,
    "pages_failed_to_scrape": <number>,
    "information_gaps": ["<any missing information>"]
  }}
}}
```

Use MapWebsite first, then systematically scrape all relevant pages. Return only the JSON object.""",
        tools=tools,
        model="gpt-4.1"
    )

async def create_arcade_scholarship_monitor(arcade_client, get_tools_func):
    """
    Continuous Monitoring Agent using Arcade Tools
    Periodically crawls known scholarship sites for updates
    """
    
    tools = await get_tools_func(["web"])
    
    return Agent(
        name="ArcadeScholarshipMonitor",
        instructions=f"""You are a scholarship monitoring specialist that uses web crawling to detect new opportunities and updates.

## MISSION: Proactive Scholarship Discovery
Monitor known scholarship websites for new opportunities, deadline changes, and updated information.

## MONITORING STRATEGY:

### Target Sites for Regular Monitoring:
1. **University financial aid pages**
2. **Government scholarship portals** (.gov sites)
3. **Professional association websites**
4. **Corporate scholarship programs**
5. **Foundation websites**
6. **Scholarship aggregator sites**

### Monitoring Process:
1. **CrawlWebsite** target sites with max_depth=3, limit=50
2. **Map changes** since last crawl
3. **Identify new scholarships** or updated deadlines
4. **Extract new opportunities** using ScrapeUrl
5. **Alert on significant changes**

## OUTPUT: New Opportunities Discovered
```json
{{
  "monitoring_summary": {{
    "sites_monitored": <number>,
    "new_scholarships_found": <number>,
    "updated_scholarships": <number>,
    "expired_scholarships": <number>,
    "monitoring_date": "<YYYY-MM-DD>"
  }},
  "new_scholarships": [
    {{
      "title": "<scholarship name>",
      "organization": "<sponsor>",
      "url": "<scholarship URL>",
      "discovered_date": "<when found>",
      "deadline": "<application deadline>",
      "amount": "<award amount>",
      "summary": "<brief description>",
      "source_site": "<site where discovered>"
    }}
  ],
  "scholarship_updates": [
    {{
      "title": "<scholarship name>",
      "url": "<scholarship URL>",
      "changes_detected": ["<list of changes>"],
      "new_deadline": "<if deadline changed>",
      "new_amount": "<if amount changed>",
      "update_type": "<deadline_extension|amount_increase|new_cycle|other>"
    }}
  ]
}}
```

Focus on discovering truly new opportunities and meaningful updates.""",
        tools=tools,
        model="gpt-4.1"
    )

# Integration helper functions
async def enhanced_validation_with_arcade(user_id: str, scholarship_candidates: dict, arcade_client):
    """
    Enhanced validation using Arcade Web tools for comprehensive verification
    """
    
    async def get_tools(toolkits):
        from agents_arcade import get_arcade_tools
        return await get_arcade_tools(arcade_client, toolkits)
    
    validation_agent = await create_arcade_validation_agent(arcade_client, get_tools)
    
    # Prepare enhanced prompt with scraping instructions
    candidates_json = json.dumps(scholarship_candidates.get('scholarship_candidates', []), indent=2)
    
    user_prompt = f"""
Perform comprehensive validation of these scholarship candidates using advanced web scraping:

{candidates_json}

Use ScrapeUrl and MapWebsite tools to:
1. Verify each scholarship URL by scraping full page content
2. Extract detailed eligibility, deadlines, and requirements
3. Validate organization legitimacy through site analysis
4. Check for current application status and functional portals

Return validated scholarships with enhanced details from scraped content.
"""
    
    from agents import Runner
    
    result = await Runner.run(
        starting_agent=validation_agent,
        input=user_prompt,
        context={"user_id": user_id}
    )
    
    # Parse the enhanced validation results
    try:
        output = str(result.final_output)
        json_match = re.search(r'```json\s*([^`]*)\s*```', output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        else:
            return json.loads(output)
    except:
        logger.error(f"Failed to parse enhanced validation results for user {user_id}")
        return {"validated_scholarships": [], "rejected_scholarships": []}


async def _record_validation_progress(user_id: str, status: str, **kwargs) -> None:
    """Update validation progress in the database if possible."""
    pool = db_manager.get_pool()
    if not pool:
        return
    try:
        await db_update_search_status(pool, user_id, status, **kwargs)
    except Exception as exc:
        logger.warning(f"Failed to update validation progress for {user_id}: {exc}")


async def validate_candidates_concurrent(user_id: str,
                                         candidates: list,
                                         arcade_client) -> list:
    """Validate multiple candidates concurrently respecting concurrency limits."""
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_VALIDATIONS)

    async def _validate(idx: int, candidate: dict):
        async with semaphore:
            await _record_validation_progress(
                user_id,
                "processing_data",
                validated_count=idx + 1,
                total_candidates=len(candidates),
            )
            return await enhanced_validation_with_arcade(
                user_id, {"scholarship_candidates": [candidate]}, arcade_client
            )

    results = await asyncio.gather(
        *[_validate(i, c) for i, c in enumerate(candidates)], return_exceptions=True
    )

    await _record_validation_progress(user_id, "validation_completed")

    return [r for r in results if not isinstance(r, Exception)]
