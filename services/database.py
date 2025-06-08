import asyncpg
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any, Set
import logging
import re

logger = logging.getLogger(__name__)

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Import AI summarizer
try:
    from .ai_summarizer import summarize_scholarship_batch
    AI_SUMMARIZATION_ENABLED = True
except ImportError as e:
    logger.warning(f"AI summarization not available: {e}")
    AI_SUMMARIZATION_ENABLED = False

DB_URL = os.getenv("DATABASE_URL")
print("DEBUG: DB_URL at startup:", DB_URL)

# Global flags to track table initialization
_scholarships_table_verified = False
_essays_table_verified = False 
_failed_scrapes_table_verified = False
_api_usage_table_verified = False
_master_scholarships_table_verified = False

# Add this mapping dictionary after the imports but before any functions
SCHOLARSHIP_CATEGORY_MAPPINGS = {
    # STEM categories
    'stem': {
        'keywords': ['engineering', 'computer', 'science', 'technology', 'math', 'stem', 'coding', 'programming', 
                    'physics', 'chemistry', 'biology', 'medical', 'pre-med', 'nursing', 'data', 'cyber', 
                    'robotics', 'artificial intelligence', 'machine learning', 'biomedical'],
        'majors': ['computer science', 'engineering', 'mathematics', 'physics', 'chemistry', 'biology', 
                  'data science', 'information technology', 'cybersecurity', 'pre-med', 'nursing'],
        'icon': '🔬',
        'display_name': 'STEM'
    },
    
    # Business & Finance
    'business': {
        'keywords': ['business', 'finance', 'accounting', 'marketing', 'management', 'economics', 'entrepreneurship',
                    'mba', 'commerce', 'trade', 'investment', 'banking', 'consulting'],
        'majors': ['business', 'finance', 'accounting', 'marketing', 'economics', 'management'],
        'icon': '💼',
        'display_name': 'Business'
    },
    
    # Arts & Humanities
    'arts': {
        'keywords': ['art', 'music', 'theatre', 'drama', 'painting', 'sculpture', 'design', 'creative', 'film',
                    'photography', 'dance', 'literature', 'writing', 'journalism', 'media', 'humanities'],
        'majors': ['art', 'music', 'theatre', 'english', 'journalism', 'media studies', 'creative writing',
                  'film studies', 'photography', 'graphic design'],
        'icon': '🎨',
        'display_name': 'Arts & Humanities'
    },
    
    # Athletics & Sports
    'athletics': {
        'keywords': ['athletic', 'sports', 'football', 'basketball', 'soccer', 'track', 'field', 'swimming',
                    'tennis', 'baseball', 'volleyball', 'golf', 'wrestling', 'fitness', 'recreation'],
        'majors': ['sports management', 'kinesiology', 'exercise science', 'sports medicine'],
        'icon': '⚽',
        'display_name': 'Athletics'
    },
    
    # Community Service & Leadership
    'leadership': {
        'keywords': ['leadership', 'volunteer', 'community', 'service', 'civic', 'social justice', 'activism',
                    'nonprofit', 'outreach', 'mentoring', 'tutoring', 'charity'],
        'majors': ['social work', 'public administration', 'nonprofit management'],
        'icon': '🤝',
        'display_name': 'Leadership & Service'
    },
    
    # Merit-based Academic
    'academic_merit': {
        'keywords': ['merit', 'academic', 'honor', 'dean', 'gpa', 'achievement', 'excellence', 'scholar',
                    'honor roll', 'valedictorian', 'salutatorian', 'top student'],
        'majors': [],  # Merit spans all majors
        'icon': '🏆',
        'display_name': 'Academic Merit'
    },
    
    # Need-based
    'need_based': {
        'keywords': ['need', 'financial need', 'low income', 'economically disadvantaged', 'pell grant',
                    'first generation', 'first-gen'],
        'majors': [],
        'icon': '🎓',
        'display_name': 'Need-Based'
    },
    
    # Diversity & Inclusion
    'diversity': {
        'keywords': ['minority', 'diversity', 'inclusion', 'underrepresented', 'women', 'hispanic', 'latino',
                    'african american', 'native american', 'asian', 'lgbtq', 'first generation'],
        'majors': [],
        'icon': '🌈',
        'display_name': 'Diversity & Inclusion'
    }
}

def categorize_scholarship_by_content(scholarship_name: str, description: str, eligibility_criteria: List[str]) -> List[Dict[str, str]]:
    """
    Categorize a scholarship based on its content and return category tags
    """
    categories = []
    content_text = f"{scholarship_name} {description} {' '.join(eligibility_criteria or [])}".lower()
    
    for category_key, category_data in SCHOLARSHIP_CATEGORY_MAPPINGS.items():
        # Check if any keywords match
        keyword_matches = [kw for kw in category_data['keywords'] if kw in content_text]
        
        if keyword_matches:
            categories.append({
                'type': 'category',
                'value': category_data['display_name'],
                'icon': category_data['icon'],
                'matched_keywords': keyword_matches[:2]  # Show up to 2 matching keywords
            })
    
    return categories

def get_user_category_preferences(user_profile: Dict[str, Any]) -> Set[str]:
    """
    Extract user's category preferences from their profile
    """
    user_categories = set()
    
    # From scholarship_types selected in onboarding
    scholarship_types = user_profile.get('scholarship_types', [])
    if isinstance(scholarship_types, str):
        scholarship_types = [scholarship_types]
        
    for scholarship_type in scholarship_types:
        scholarship_type_lower = scholarship_type.lower()
        if 'merit' in scholarship_type_lower:
            user_categories.add('academic_merit')
        elif 'need' in scholarship_type_lower:
            user_categories.add('need_based')
        elif 'field' in scholarship_type_lower or 'specific' in scholarship_type_lower:
            # Map to user's field of study
            user_major = user_profile.get('major', '').lower()
            for category_key, category_data in SCHOLARSHIP_CATEGORY_MAPPINGS.items():
                if any(major in user_major for major in category_data['majors']):
                    user_categories.add(category_key)
                    break
    
    # From major/field of study
    user_major = user_profile.get('major', '').lower()
    for category_key, category_data in SCHOLARSHIP_CATEGORY_MAPPINGS.items():
        if any(major in user_major for major in category_data['majors']):
            user_categories.add(category_key)
    
    # From merits/personal qualities
    user_merits = user_profile.get('merits', [])
    if isinstance(user_merits, str):
        user_merits = [user_merits]
        
    for merit in user_merits:
        merit_lower = merit.lower()
        if any(keyword in merit_lower for keyword in SCHOLARSHIP_CATEGORY_MAPPINGS['diversity']['keywords']):
            user_categories.add('diversity')
        elif any(keyword in merit_lower for keyword in SCHOLARSHIP_CATEGORY_MAPPINGS['leadership']['keywords']):
            user_categories.add('leadership')
        elif any(keyword in merit_lower for keyword in SCHOLARSHIP_CATEGORY_MAPPINGS['athletics']['keywords']):
            user_categories.add('athletics')
        elif any(keyword in merit_lower for keyword in SCHOLARSHIP_CATEGORY_MAPPINGS['academic_merit']['keywords']):
            user_categories.add('academic_merit')
    
    # From interests
    user_interests = user_profile.get('interests', [])
    if isinstance(user_interests, str):
        user_interests = [user_interests]
        
    for interest in user_interests:
        interest_lower = interest.lower()
        for category_key, category_data in SCHOLARSHIP_CATEGORY_MAPPINGS.items():
            if any(keyword in interest_lower for keyword in category_data['keywords']):
                user_categories.add(category_key)
    
    return user_categories

class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize_pool(self, db_url: str, min_size=2, max_size=10, command_timeout=30):
        """Initialize the connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                db_url, 
                min_size=min_size, 
                max_size=max_size,
                command_timeout=command_timeout
            )
            logger.info("Database pool initialized successfully")
            
            # Ensure all tables exist
            await self._ensure_all_tables()
            
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    async def _ensure_all_tables(self):
        """Ensure all necessary tables exist"""
        if self.pool:
            await _ensure_users_table(self.pool)
            await _ensure_master_scholarships_table(self.pool)
            await _ensure_scholarships_table(self.pool) 
            await _ensure_essays_table(self.pool)
            await _ensure_failed_scrapes_table(self.pool)
            await _ensure_api_usage_table(self.pool)

    async def close_pool(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")

    def get_pool(self) -> Optional[asyncpg.Pool]:
        return self.pool

# Global database manager instance
db_manager = DatabaseManager()

async def get_conn():
    """Get database connection from pool"""
    pool = db_manager.get_pool()
    if not pool:
        raise RuntimeError("Database pool not initialized. Call db_manager.initialize_pool() first.")
    return pool

async def fetch_profile(pool: asyncpg.Pool, user_id: str) -> Optional[Dict[str, Any]]:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT profile FROM profiles_jsonb WHERE user_id=$1", user_id)
    if not row:
        return None
    profile = row["profile"]
    if isinstance(profile, dict):
        return profile
    elif isinstance(profile, str):
        return json.loads(profile)
    else:
        # fallback for other types (e.g., asyncpg Record)
        return dict(profile)

async def save_profile(pool: asyncpg.Pool, user_id: str, profile: Dict[str, Any]):
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure user exists in users table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                user_id
            )
            # Ensure profiles_jsonb table exists
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles_jsonb (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    profile JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await conn.execute(
                """INSERT INTO profiles_jsonb (user_id, profile, updated_at)
                   VALUES ($1, $2, now())
                   ON CONFLICT (user_id) DO UPDATE SET profile=$2, updated_at=now()""",
                user_id, json.dumps(profile)
            )

# --------------------------------------------------------------------------
# Internal helper: ensure tables exist
# --------------------------------------------------------------------------

async def _ensure_users_table(pool: asyncpg.Pool):
    """Ensure users table exists"""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                profile JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

async def _ensure_master_scholarships_table(pool: asyncpg.Pool):
    """Create a global repository for all scholarship data"""
    global _master_scholarships_table_verified
    if _master_scholarships_table_verified:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized for _ensure_master_scholarships_table.")
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Enable pg_trgm extension for similarity search
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS master_scholarships (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    deadline DATE,
                    amount_text TEXT,  -- "Up to $5,000", "$1000", etc.
                    amount_numeric INTEGER, -- Parsed numeric value for filtering
                    description TEXT,
                    location TEXT,
                    academic_levels TEXT[], -- ["undergraduate", "graduate"]
                    application_url TEXT,
                    eligibility_criteria TEXT[],
                    source TEXT DEFAULT 'csv_import',
                    data_quality_score INTEGER DEFAULT 5, -- 1-10 scale
                    is_verified BOOLEAN DEFAULT FALSE,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    search_vector TSVECTOR, -- For full-text search
                    metadata JSONB DEFAULT '{}',
                    UNIQUE(name)
                );
            """)
            
            # Performance indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_amount 
                ON master_scholarships(amount_numeric DESC);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_search 
                ON master_scholarships USING GIN(search_vector);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_location 
                ON master_scholarships USING GIN(location gin_trgm_ops);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_name_search 
                ON master_scholarships USING GIN(name gin_trgm_ops);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_quality 
                ON master_scholarships(data_quality_score DESC, last_updated DESC);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_master_scholarships_deadline_simple
                ON master_scholarships(deadline);
            """)
    
    _master_scholarships_table_verified = True
    logger.info("Master scholarships table verified/created")

async def search_master_scholarships(
    pool: asyncpg.Pool, 
    user_profile: Dict[str, Any],
    limit: int = 50,
    current_only: bool = True
) -> List[Dict[str, Any]]:
    """Search master scholarship database with user-specific filtering and detailed relevance scoring"""
    await _ensure_master_scholarships_table(pool)
    
    # Get user's category preferences for enhanced matching
    user_preferred_categories = get_user_category_preferences(user_profile)
    
    # Store user criteria for match tracking
    user_academic_level = user_profile.get('academic_level', '').lower()
    user_major = user_profile.get('major', '')
    user_location = user_profile.get('location', '')
    user_interests = user_profile.get('interests', [])
    user_gpa = user_profile.get('gpa')
    
    # Build dynamic query based on user profile
    conditions = []
    params = []
    param_count = 0
    
    # Date filtering (current scholarships only by default)
    if current_only:
        param_count += 1
        conditions.append(f"(deadline IS NULL OR deadline >= ${param_count})")
        params.append(datetime.now().date())
    
    # Academic level filtering
    academic_level_match = False
    if user_academic_level:
        level_mapping = {
            'undergraduate': 'undergraduate',
            'graduate': 'graduate', 
            'high school': 'high_school',
            'postgraduate': 'graduate'
        }
        mapped_level = level_mapping.get(user_academic_level, user_academic_level)
        param_count += 1
        conditions.append(f"${param_count} = ANY(academic_levels)")
        params.append(mapped_level)
        academic_level_match = True
    
    # Enhanced location filtering
    from .location_utils import get_enhanced_user_location_info, create_location_filter_clause
    
    user_location_info = get_enhanced_user_location_info(user_profile)
    location_match = False
    
    if user_location_info.get('primary_state'):
        location_clause, location_params = create_location_filter_clause(user_location_info, param_count)
        conditions.append(location_clause)
        params.extend(location_params)
        param_count += len(location_params)
        location_match = True
    elif user_location:
        # Fallback to original logic if enhanced parsing fails
        param_count += 1
        conditions.append(f"(location ILIKE ${param_count} OR location ILIKE '%No Geographic%' OR location ILIKE '%nationwide%')")
        params.append(f"%{user_location}%")
        location_match = True
    
    # Build search terms for text search
    search_terms = []
    if user_major:
        search_terms.append(user_major)
    if user_interests:
        if isinstance(user_interests, list):
            search_terms.extend(user_interests)
        else:
            search_terms.append(str(user_interests))
    
    search_query = ' '.join(search_terms) if search_terms else 'scholarship'
    param_count += 1
    params.append(search_query)
    
    # Combine conditions
    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    
    final_query = f"""
        SELECT 
            name, 
            deadline, 
            amount_text, 
            amount_numeric, 
            description, 
            location, 
            academic_levels, 
            application_url, 
            data_quality_score,
            eligibility_criteria,
            CASE 
                WHEN search_vector IS NOT NULL THEN ts_rank(search_vector, plainto_tsquery(${param_count}))
                ELSE 0
            END as relevance_score
        FROM master_scholarships
        WHERE {where_clause}
        ORDER BY relevance_score DESC, amount_numeric DESC NULLS LAST, data_quality_score DESC
        LIMIT ${param_count + 1}
    """
    
    params.append(limit)
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(final_query, *params)
    
    scholarships = []
    for row in rows:
        # Calculate detailed match reasons and relevance tags
        match_reasons = []
        relevance_tags = []
        
        # Academic level matching
        if academic_level_match and user_academic_level:
            if any(level.lower() in user_academic_level for level in (row['academic_levels'] or [])):
                match_reasons.append(f"Academic level: {user_academic_level.title()}")
                relevance_tags.append({"type": "academic_level", "value": user_academic_level.title(), "icon": "🎓"})
        
        # Enhanced location matching
        if location_match:
            from .location_utils import calculate_location_match_score
            
            user_state = user_location_info.get('primary_state', '')
            user_university = user_location_info.get('university', '')
            scholarship_location = row['location'] or ''
            
            match_score, reason, tags = calculate_location_match_score(
                user_state, user_university, scholarship_location
            )
            
            if match_score > 0.5:  # Only show meaningful matches
                match_reasons.append(reason)
                for tag in tags:
                    relevance_tags.append({"type": "location", "value": tag, "icon": "📍"})
        
        # Major/field matching
        if user_major:
            description_text = (row['description'] or '').lower()
            name_text = (row['name'] or '').lower()
            major_lower = user_major.lower()
            
            if major_lower in description_text or major_lower in name_text:
                match_reasons.append(f"Field of study: {user_major}")
                relevance_tags.append({"type": "major", "value": user_major, "icon": "📚"})
        
        # Interest matching
        if user_interests:
            interests_list = user_interests if isinstance(user_interests, list) else [user_interests]
            description_text = (row['description'] or '').lower()
            name_text = (row['name'] or '').lower()
            
            matched_interests = []
            for interest in interests_list:
                if interest.lower() in description_text or interest.lower() in name_text:
                    matched_interests.append(interest)
            
            if matched_interests:
                for interest in matched_interests[:2]:  # Limit to 2 interests to avoid clutter
                    match_reasons.append(f"Interest: {interest}")
                    relevance_tags.append({"type": "interest", "value": interest, "icon": "💡"})
        
        # GPA requirements (if available in description)
        if user_gpa:
            description_text = (row['description'] or '').lower()
            # Look for GPA requirements in description
            import re
            gpa_patterns = [r'(\d\.\d+)\s*gpa', r'gpa.*?(\d\.\d+)', r'(\d\.\d+)\s*grade']
            for pattern in gpa_patterns:
                matches = re.findall(pattern, description_text)
                if matches:
                    try:
                        required_gpa = float(matches[0])
                        if user_gpa >= required_gpa:
                            match_reasons.append(f"GPA requirement met: {required_gpa}")
                            relevance_tags.append({"type": "gpa", "value": f"≥{required_gpa} GPA", "icon": "📊"})
                        break
                    except (ValueError, IndexError):
                        continue
        
        # Demographic matching
        user_demographics = user_profile.get('demographics', [])
        if user_demographics:
            demographics_list = user_demographics if isinstance(user_demographics, list) else [user_demographics]
            description_text = (row['description'] or '').lower()
            name_text = (row['name'] or '').lower()
            scholarship_eligibility_criteria = [str(crit).lower() for crit in (row['eligibility_criteria'] or [])]

            matched_demographics = []
            for demographic_item_original in demographics_list:
                demographic_item = demographic_item_original.lower()
                found_in_eligibility = any(demographic_item in crit_text for crit_text in scholarship_eligibility_criteria)
                if demographic_item in description_text or demographic_item in name_text or found_in_eligibility:
                    if demographic_item_original not in matched_demographics:
                        matched_demographics.append(demographic_item_original)
            
            if matched_demographics:
                for demographic_item_original in matched_demographics[:2]:
                    match_reasons.append(f"Demographic: {demographic_item_original.title()}")
                    relevance_tags.append({"type": "demographic", "value": demographic_item_original.title(), "icon": "👥"})

        # Merit matching
        user_merits = user_profile.get('merits', [])
        if user_merits:
            merits_list = user_merits if isinstance(user_merits, list) else [user_merits]
            description_text = (row['description'] or '').lower()
            name_text = (row['name'] or '').lower()
            scholarship_eligibility_criteria = [str(crit).lower() for crit in (row['eligibility_criteria'] or [])]

            matched_merits = []
            for merit_item_original in merits_list:
                merit_item = merit_item_original.lower()
                found_in_eligibility = any(merit_item in crit_text for crit_text in scholarship_eligibility_criteria)
                if merit_item in description_text or merit_item in name_text or found_in_eligibility:
                    if merit_item_original not in matched_merits:
                        matched_merits.append(merit_item_original)
            
            if matched_merits:
                for merit_item_original in matched_merits[:2]:
                    match_reasons.append(f"Merit: {merit_item_original.title()}")
                    relevance_tags.append({"type": "merit", "value": merit_item_original.title(), "icon": "🌟"})

        # NEW: Category-based matching using onboarding profile alignment
        scholarship_categories = categorize_scholarship_by_content(
            row['name'] or '', 
            row['description'] or '', 
            row['eligibility_criteria'] or []
        )
        
        # Check if scholarship categories match user preferences
        for category_tag in scholarship_categories:
            category_key = None
            for key, data in SCHOLARSHIP_CATEGORY_MAPPINGS.items():
                if data['display_name'] == category_tag['value']:
                    category_key = key
                    break
            
            if category_key and category_key in user_preferred_categories:
                match_reasons.append(f"Category match: {category_tag['value']}")
                relevance_tags.append({
                    "type": "category_match",
                    "value": category_tag['value'],
                    "icon": category_tag['icon']
                })
                
        # Add all category tags (even non-matching ones) for transparency
        for category_tag in scholarship_categories[:3]:  # Limit to 3 categories
            # Only add if not already added as a match
            if not any(tag.get('value') == category_tag['value'] and tag.get('type') == 'category_match' 
                      for tag in relevance_tags):
                relevance_tags.append({
                    "type": "scholarship_category",
                    "value": category_tag['value'],
                    "icon": category_tag['icon']
                })

        # Amount range tags
        if row['amount_numeric']:
            amount = row['amount_numeric']
            if amount >= 10000:
                relevance_tags.append({"type": "amount", "value": "High Value ($10K+)", "icon": "💰"})
            elif amount >= 5000:
                relevance_tags.append({"type": "amount", "value": "Mid Value ($5K+)", "icon": "💵"})
            elif amount >= 1000:
                relevance_tags.append({"type": "amount", "value": "Merit Award ($1K+)", "icon": "💴"})
        
        # Deadline urgency
        if row['deadline']:
            deadline_date = row['deadline']
            days_until = (deadline_date - datetime.now().date()).days
            
            if days_until <= 30:
                relevance_tags.append({"type": "deadline", "value": f"{days_until} days left", "icon": "⏰"})
            elif days_until <= 90:
                relevance_tags.append({"type": "deadline", "value": "Apply soon", "icon": "📅"})
        
        # Quality score
        quality_score = row['data_quality_score'] or 0
        if quality_score >= 80:
            relevance_tags.append({"type": "quality", "value": "Verified Info", "icon": "✅"})
        
        # Calculate overall relevance score with category matching bonus
        base_relevance = float(row['relevance_score']) if row['relevance_score'] else 0
        match_bonus = len(match_reasons) * 0.1  # Bonus for each match criteria
        
        # Extra bonus for category matches (these align with user's onboarding choices)
        category_match_bonus = len([tag for tag in relevance_tags if tag.get('type') == 'category_match']) * 0.15
        
        final_relevance = min(1.0, base_relevance + match_bonus + category_match_bonus)
        
        scholarship = {
            'name': row['name'],
            'deadline': row['deadline'].isoformat() if row['deadline'] else None,
            'amount': row['amount_text'],
            'amount_numeric': row['amount_numeric'],
            'description': row['description'],
            'location': row['location'],
            'academic_levels': row['academic_levels'],
            'url': row['application_url'],
            'data_quality_score': row['data_quality_score'],
            'eligibility_criteria_debug': row['eligibility_criteria'],
            'relevance_score': final_relevance,
            'source': 'master_database',
            'match_reasons': match_reasons,
            'relevance_tags': relevance_tags,
            'user_criteria_matched': {
                'academic_level': user_academic_level,
                'major': user_major,
                'location': user_location,
                'interests': user_interests,
                'gpa': user_gpa,
                'preferred_categories': list(user_preferred_categories)
            }
        }
        scholarships.append(scholarship)
    
    logger.info(f"Found {len(scholarships)} scholarships from master database with enhanced category-based relevance scoring")
    return scholarships

async def get_master_scholarships_stats(pool: asyncpg.Pool) -> Dict[str, Any]:
    """Get statistics about the master scholarships database"""
    await _ensure_master_scholarships_table(pool)
    
    async with pool.acquire() as conn:
        # Total count
        total_count = await conn.fetchval("SELECT COUNT(*) FROM master_scholarships")
        
        # Current scholarships (not expired)
        current_count = await conn.fetchval("""
            SELECT COUNT(*) FROM master_scholarships 
            WHERE deadline IS NULL OR deadline >= CURRENT_DATE
        """)
        
        # Amount statistics
        amount_stats = await conn.fetchrow("""
            SELECT 
                AVG(amount_numeric) as avg_amount,
                MAX(amount_numeric) as max_amount,
                MIN(amount_numeric) as min_amount
            FROM master_scholarships 
            WHERE amount_numeric IS NOT NULL
        """)
        
        # Academic level distribution
        level_stats = await conn.fetch("""
            SELECT unnest(academic_levels) as level, COUNT(*) as count
            FROM master_scholarships 
            GROUP BY unnest(academic_levels)
            ORDER BY count DESC
        """)
        
    return {
        'total_scholarships': total_count,
        'current_scholarships': current_count,
        'expired_scholarships': total_count - current_count,
        'average_amount': float(amount_stats['avg_amount']) if amount_stats['avg_amount'] else 0,
        'max_amount': amount_stats['max_amount'],
        'min_amount': amount_stats['min_amount'],
        'academic_level_distribution': {row['level']: row['count'] for row in level_stats}
    }

async def _ensure_scholarships_table(pool: asyncpg.Pool):
    global _scholarships_table_verified
    if _scholarships_table_verified:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized for _ensure_scholarships_table.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scholarships_ranked (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    scholarship JSONB NOT NULL,
                    score REAL DEFAULT 0,
                    rationale TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    validation_metadata JSONB DEFAULT '{}',
                    scrape_quality_score INTEGER DEFAULT 0,
                    last_validated TIMESTAMP WITH TIME ZONE,
                    validation_agent_version TEXT DEFAULT 'v1',
                    pages_scraped INTEGER DEFAULT 0,
                    validation_confidence REAL DEFAULT 0.0,
                    application_portal_verified BOOLEAN DEFAULT FALSE,
                    essay_requirements_extracted BOOLEAN DEFAULT FALSE
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scholarships_ranked_user_id
                    ON scholarships_ranked(user_id);
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scholarships_validation_quality
                    ON scholarships_ranked(scrape_quality_score DESC, validation_confidence DESC);
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scholarships_last_validated
                    ON scholarships_ranked(last_validated DESC);
                """
            )
    _scholarships_table_verified = True


async def _ensure_essays_table(pool: asyncpg.Pool):
    global _essays_table_verified
    if _essays_table_verified:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized for _ensure_essays_table.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS essays (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    scholarship_pk TEXT NOT NULL,
                    essay_prompt JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_essays_user_id
                    ON essays(user_id);
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_essays_scholarship_pk
                    ON essays(scholarship_pk);
                """
            )
    _essays_table_verified = True


async def _ensure_failed_scrapes_table(pool: asyncpg.Pool):
    global _failed_scrapes_table_verified
    if _failed_scrapes_table_verified:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized for _ensure_failed_scrapes_table.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failed_scrapes (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    scholarship_pk TEXT NOT NULL,
                    scholarship_name TEXT,
                    url TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_failed_scrapes_user_id
                    ON failed_scrapes(user_id);
                """
            )
    _failed_scrapes_table_verified = True


async def _ensure_api_usage_table(pool: asyncpg.Pool):
    global _api_usage_table_verified
    if _api_usage_table_verified: # Corrected to use the global flag
        return
    if not pool:
        raise RuntimeError("Database pool not initialized for _ensure_api_usage_table.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    tool_name TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    api_provider TEXT NOT NULL,
                    tokens_used INTEGER DEFAULT 0,
                    estimated_cost REAL DEFAULT 0.0,
                    pages_scraped INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}'
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_usage_user_date
                    ON api_usage(user_id, created_at DESC);
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_usage_cost_tracking
                    ON api_usage(api_provider, operation_type, created_at DESC);
                """
            )
    _api_usage_table_verified = True # Corrected to set the global flag


async def save_scholarships(pool: asyncpg.Pool, user_id: str, scholarships_json: List[Dict[str, Any]]):
    if not scholarships_json:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized.")

    await _ensure_scholarships_table(pool)

    # Apply AI summarization if enabled
    if AI_SUMMARIZATION_ENABLED and scholarships_json:
        try:
            print(f"🤖 Generating AI summaries for {len(scholarships_json)} scholarships...")
            scholarships_json = await summarize_scholarship_batch(scholarships_json)
            print(f"✅ AI summarization completed")
        except Exception as e:
            print(f"⚠️ AI summarization failed, continuing with original text: {e}")

    # Clear existing scholarships for this user first
    delete_sql = "DELETE FROM scholarships_ranked WHERE user_id = $1"
    insert_sql = (
        "INSERT INTO scholarships_ranked (user_id, scholarship, score, rationale) "
        "VALUES ($1, $2, $3, $4)"
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            # First, delete existing scholarships for this user
            await conn.execute(delete_sql, user_id)
            
            # Then insert the new scholarships (now with AI summaries)
            for s in scholarships_json:
                if not isinstance(s, dict):
                    try:
                        s = json.loads(str(s))
                    except Exception:
                        print(f"Skipping malformed scholarship entry for user {user_id}: {s}")
                        continue
                await conn.execute(
                    insert_sql,
                    user_id,
                    json.dumps(s),
                    float(s.get("score", 0) or 0),
                    s.get("rationale", ""),
                )

async def fetch_scholarships(pool: asyncpg.Pool, user_id: str) -> List[Dict[str, Any]]:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_scholarships_table(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT scholarship, score, rationale FROM scholarships_ranked WHERE user_id=$1 ORDER BY score DESC, created_at ASC",
            user_id,
        )
    scholarships = []
    for row in rows:
        s_raw = row["scholarship"]
        try:
            if isinstance(s_raw, dict):
                s_dict = s_raw
            elif isinstance(s_raw, str):
                s_dict = json.loads(s_raw)
            else:
                s_dict = dict(s_raw)
            if "score" not in s_dict and row["score"] is not None:
                s_dict["score"] = row["score"]
            if "rationale" not in s_dict and row["rationale"] is not None:
                s_dict["rationale"] = row["rationale"]
            scholarships.append(s_dict)
        except Exception as e:
            print(f"Error processing scholarship row for user {user_id}: {e}. Raw data: {s_raw}")
    return scholarships

async def save_essays(pool: asyncpg.Pool, user_id: str, essay_prompts_for_one_scholarship: list):
    if not essay_prompts_for_one_scholarship:
        return
    if not pool:
        raise RuntimeError("Database pool not initialized.")

    first_prompt = essay_prompts_for_one_scholarship[0]
    if not isinstance(first_prompt, dict) or "scholarship_pk" not in first_prompt:
        print(f"ERROR: Malformed first essay prompt, cannot determine scholarship_pk for user {user_id}: {first_prompt}")
        return
    scholarship_pk = first_prompt["scholarship_pk"]
    
    await _ensure_essays_table(pool)
    
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                for prompt_data in essay_prompts_for_one_scholarship:
                    if not isinstance(prompt_data, dict):
                        print(f"WARNING: Skipping malformed essay prompt for user {user_id}: {prompt_data}")
                        continue
                    existing = await conn.fetchrow(
                        """SELECT id FROM essays 
                           WHERE user_id=$1 AND scholarship_pk=$2 AND essay_prompt->>'prompt_text'=$3""",
                        user_id, scholarship_pk, prompt_data.get('prompt_text', '')
                    )
                    if not existing:
                        await conn.execute(
                            """INSERT INTO essays (user_id, scholarship_pk, essay_prompt) 
                               VALUES ($1, $2, $3)""",
                            user_id, scholarship_pk, json.dumps(prompt_data)
                        )
            print(f"Saved/Updated {len(essay_prompts_for_one_scholarship)} essay prompts for user {user_id}, scholarship_pk {scholarship_pk} to Postgres.")
        except Exception as e:
            print(f"Error in save_essays for user {user_id}, scholarship_pk {scholarship_pk}: {e}")

async def fetch_essays(pool: asyncpg.Pool, user_id: str) -> List[Dict[str, Any]]:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_essays_table(pool)
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """SELECT essay_prompt FROM essays 
                   WHERE user_id=$1 
                   ORDER BY created_at ASC""",
                user_id
            )
            all_prompts_for_user = []
            for row in rows:
                try:
                    prompt_data = row['essay_prompt']
                    if isinstance(prompt_data, dict):
                        all_prompts_for_user.append(prompt_data)
                    elif isinstance(prompt_data, str):
                        parsed_prompt = json.loads(prompt_data)
                        all_prompts_for_user.append(parsed_prompt)
                    else:
                        print(f"WARNING: Unexpected essay prompt format for user {user_id}: {type(prompt_data)}")
                except json.JSONDecodeError as e:
                    print(f"ERROR: Failed to decode essay prompt JSON for user {user_id}: {e}")
            return all_prompts_for_user
        except Exception as e:
            print(f"Error fetching essays for user {user_id}: {e}")
            return []

async def save_failed_scrape(pool: asyncpg.Pool, user_id: str, scholarship_pk: str, url: str, scholarship_name: str, error_message: str):
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_failed_scrapes_table(pool)
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO failed_scrapes (user_id, scholarship_pk, scholarship_name, url, error_message) 
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, scholarship_pk, scholarship_name, url, error_message
            )
            print(f"Logged failed scrape for user {user_id}, scholarship_pk {scholarship_pk}: {error_message}")
        except Exception as e:
            print(f"Error saving failed scrape for user {user_id}, scholarship_pk {scholarship_pk}: {e}")

async def save_active_crawl(pool: asyncpg.Pool, user_id: str, crawl_id: str):
    current_profile = await fetch_profile(pool, user_id) or {}
    current_profile['active_search_crawl_id'] = crawl_id
    current_profile['scholarship_search_status'] = 'crawling'
    await save_profile(pool, user_id, current_profile)

async def get_active_crawl(pool: asyncpg.Pool, user_id: str) -> Optional[str]:
    profile = await fetch_profile(pool, user_id)
    if profile:
        return profile.get('active_search_crawl_id')
    return None

async def update_search_status(pool: asyncpg.Pool, user_id: str, status: str, **kwargs):
    current_profile = await fetch_profile(pool, user_id) or {}
    current_profile['scholarship_search_status'] = status
    for key, value in kwargs.items():
        current_profile[key] = value
    await save_profile(pool, user_id, current_profile)

async def get_search_status(pool: asyncpg.Pool, user_id: str) -> str:
    profile = await fetch_profile(pool, user_id)
    if profile:
        return profile.get('scholarship_search_status', 'not_started')
    return 'not_started'

async def fetch_failed_scrapes(pool: asyncpg.Pool, user_id: str) -> List[Dict[str, Any]]:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_failed_scrapes_table(pool)
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """SELECT scholarship_pk, scholarship_name, url, error_message, created_at 
                   FROM failed_scrapes 
                   WHERE user_id=$1 
                   ORDER BY created_at DESC""",
                user_id
            )
            failed_scrapes = []
            for row in rows:
                failed_scrapes.append({
                    'scholarship_pk': row['scholarship_pk'],
                    'scholarship_name': row['scholarship_name'],
                    'url': row['url'],
                    'error_message': row['error_message'],
                    'timestamp': row['created_at'].isoformat() if row['created_at'] else None
                })
            return failed_scrapes
        except Exception as e:
            print(f"Error fetching failed scrapes for user {user_id}: {e}")
            return []

async def clear_user_essays(pool: asyncpg.Pool, user_id: str) -> int:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_essays_table(pool)
    async with pool.acquire() as conn:
        try:
            # Corrected: fetchval returns the value of the first column of the first row.
            # For COUNT(*), it's an integer.
            result = await conn.execute(
                "DELETE FROM essays WHERE user_id=$1", user_id
            )
            # The result of DELETE is a string like 'DELETE N'
            deleted_count_str = result.split(" ")[1]
            deleted_count = int(deleted_count_str) if deleted_count_str.isdigit() else 0
            print(f"Cleared {deleted_count} essays for user {user_id}")
            return deleted_count
        except Exception as e:
            print(f"Error clearing essays for user {user_id}: {e}")
            return 0

async def get_essays_count(pool: asyncpg.Pool, user_id: str) -> int:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_essays_table(pool)
    async with pool.acquire() as conn:
        try:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM essays WHERE user_id=$1",
                user_id
            )
            return count or 0
        except Exception as e:
            print(f"Error getting essays count for user {user_id}: {e}")
            return 0

async def init_essay_extraction_progress(pool: asyncpg.Pool, user_id: str, total_scholarships: int):
    current_profile = await fetch_profile(pool, user_id) or {}
    current_profile['essay_extraction'] = {
        'status': 'starting',
        'total_scholarships': total_scholarships,
        'completed': 0,
        'failed': 0,
        'in_progress': 0,
        'started_at': datetime.now().isoformat(),
        'last_updated': datetime.now().isoformat(),
        'extraction_sessions': {}
    }
    await save_profile(pool, user_id, current_profile)

async def update_essay_extraction_progress(pool: asyncpg.Pool, user_id: str, scholarship_pk: str, status: str, **kwargs):
    current_profile = await fetch_profile(pool, user_id) or {}
    if 'essay_extraction' not in current_profile:
        current_profile['essay_extraction'] = {
            'status': 'in_progress', 'total_scholarships': 1, 'completed': 0,
            'failed': 0, 'in_progress': 0, 'started_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(), 'extraction_sessions': {}
        }
    extraction_info = current_profile['essay_extraction']
    
    # Get old status for counter adjustment
    old_individual_status = extraction_info.get('extraction_sessions', {}).get(scholarship_pk, {}).get('status')

    extraction_info.setdefault('extraction_sessions', {})[scholarship_pk] = {
        'status': status, 'updated_at': datetime.now().isoformat(), **kwargs
    }

    # Adjust counters based on old and new status
    if old_individual_status:
        if old_individual_status == 'in_progress': extraction_info['in_progress'] = max(0, extraction_info.get('in_progress', 0) - 1)
        elif old_individual_status == 'completed': extraction_info['completed'] = max(0, extraction_info.get('completed', 0) - 1)
        elif old_individual_status == 'failed': extraction_info['failed'] = max(0, extraction_info.get('failed', 0) - 1)

    if status == 'in_progress': extraction_info['in_progress'] = extraction_info.get('in_progress', 0) + 1
    elif status == 'completed': extraction_info['completed'] = extraction_info.get('completed', 0) + 1
    elif status == 'failed': extraction_info['failed'] = extraction_info.get('failed', 0) + 1
    
    total = extraction_info.get('total_scholarships', 0)
    completed = extraction_info.get('completed', 0)
    failed = extraction_info.get('failed', 0)
    
    if completed + failed >= total:
        extraction_info['status'] = 'completed'
        extraction_info['finished_at'] = datetime.now().isoformat()
    elif extraction_info.get('in_progress', 0) > 0 or completed + failed < total:
        extraction_info['status'] = 'in_progress'
    
    extraction_info['last_updated'] = datetime.now().isoformat()
    await save_profile(pool, user_id, current_profile)

async def get_essay_extraction_progress(pool: asyncpg.Pool, user_id: str) -> Optional[Dict[str, Any]]:
    profile = await fetch_profile(pool, user_id)
    if profile and 'essay_extraction' in profile:
        return profile['essay_extraction']
    return None

async def clear_essay_extraction_progress(pool: asyncpg.Pool, user_id: str):
    current_profile = await fetch_profile(pool, user_id) or {}
    if 'essay_extraction' in current_profile:
        del current_profile['essay_extraction']
        await save_profile(pool, user_id, current_profile)

async def track_api_usage(pool: asyncpg.Pool, user_id: str, tool_name: str, operation_type: str, 
                         api_provider: str, tokens_used: int = 0, 
                         estimated_cost: float = 0.0, pages_scraped: int = 0,
                         metadata: Optional[dict] = None):
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_api_usage_table(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage 
            (user_id, tool_name, operation_type, api_provider, tokens_used, 
             estimated_cost, pages_scraped, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user_id, tool_name, operation_type, api_provider, tokens_used,
            estimated_cost, pages_scraped, json.dumps(metadata or {})
        )

async def get_user_usage_stats(pool: asyncpg.Pool, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
    if not pool:
        raise RuntimeError("Database pool not initialized.")
    await _ensure_api_usage_table(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                api_provider,
                operation_type,
                COUNT(*) as request_count,
                SUM(tokens_used) as total_tokens,
                SUM(estimated_cost) as total_cost,
                SUM(pages_scraped) as total_pages_scraped
            FROM api_usage 
            WHERE user_id = $1 
            AND created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
            GROUP BY api_provider, operation_type
            ORDER BY total_cost DESC
            """ % days, # Use % formatting for interval as asyncpg doesn't support $ for interval units directly
            user_id
        )
    return [dict(row) for row in rows]
