import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

logger = logging.getLogger("treatment_navigator.database")

class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize_pool(self, database_url: str, min_size: int = 5, max_size: int = 20):
        """Initialize the database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=30
            )
            logger.info(f"Database pool initialized with {min_size}-{max_size} connections")
            
            # Create tables if they don't exist - if there's a schema error, reset and recreate
            try:
                await self.create_tables()
            except Exception as e:
                if "referenced in foreign key constraint does not exist" in str(e):
                    logger.warning("Foreign key constraint error detected. Resetting database schema...")
                    await self.reset_database()
                else:
                    raise
            
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    async def close_pool(self):
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)
    
    async def create_tables(self):
        """Create database tables for treatment navigation."""
        async with self.get_connection() as conn:
            # User profiles table (no dependencies)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255),
                    email VARCHAR(255),
                    phone VARCHAR(50),
                    location VARCHAR(255),
                    insurance_provider VARCHAR(255),
                    insurance_id VARCHAR(255),
                    emergency_contact JSONB,
                    medical_history JSONB,
                    preferences JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Treatment facilities table (no dependencies - must be created before referenced tables)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS treatment_facilities (
                    facility_id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    address VARCHAR(500),
                    phone VARCHAR(50),
                    email VARCHAR(255),
                    website VARCHAR(255),
                    facility_type VARCHAR(100),
                    specialties JSONB,
                    insurance_accepted JSONB,
                    operating_hours JSONB,
                    is_operational BOOLEAN DEFAULT true,
                    accepting_patients BOOLEAN DEFAULT true,
                    is_emergency BOOLEAN DEFAULT false,
                    rating DECIMAL(3,2),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Treatment records table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS treatment_records (
                    record_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    facility_id INTEGER REFERENCES treatment_facilities(facility_id),
                    treatment_type VARCHAR(100),
                    status VARCHAR(50),
                    start_date DATE,
                    end_date DATE,
                    notes TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Appointments table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    appointment_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    facility_id INTEGER REFERENCES treatment_facilities(facility_id),
                    appointment_datetime TIMESTAMP,
                    appointment_type VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'scheduled',
                    urgency_level VARCHAR(20) DEFAULT 'routine',
                    notes TEXT,
                    reminder_sent BOOLEAN DEFAULT false,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insurance verification table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS insurance_verifications (
                    verification_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    insurance_provider VARCHAR(255),
                    insurance_id VARCHAR(255),
                    treatment_type VARCHAR(100),
                    coverage_status VARCHAR(50),
                    coverage_details JSONB,
                    verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    metadata JSONB
                )
            """)
            
            # Treatment reminders table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS treatment_reminders (
                    reminder_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    reminder_type VARCHAR(50),
                    title VARCHAR(255),
                    description TEXT,
                    reminder_datetime TIMESTAMP,
                    is_recurring BOOLEAN DEFAULT false,
                    recurrence_pattern VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'active',
                    sent_at TIMESTAMP,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # API usage tracking table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    usage_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    tool_name VARCHAR(100),
                    operation_type VARCHAR(100),
                    api_provider VARCHAR(100),
                    tokens_used INTEGER DEFAULT 0,
                    estimated_cost DECIMAL(10,4) DEFAULT 0.0,
                    pages_scraped INTEGER DEFAULT 0,
                    metadata JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Communication logs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS communication_logs (
                    log_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    facility_id INTEGER REFERENCES treatment_facilities(facility_id),
                    communication_type VARCHAR(50),
                    direction VARCHAR(20),
                    subject VARCHAR(255),
                    message_content TEXT,
                    status VARCHAR(50),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_treatment_records_user_id ON treatment_records(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_appointments_user_id ON appointments(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_appointments_datetime ON appointments(appointment_datetime)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_insurance_verifications_user_id ON insurance_verifications(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_treatment_reminders_user_id ON treatment_reminders(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_user_id ON api_usage(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage(timestamp)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_communication_logs_user_id ON communication_logs(user_id)")
            
            logger.info("Database tables created successfully")

    async def fetch_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile from database."""
        async with self.get_connection() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM user_profiles WHERE user_id = $1",
                    user_id
                )
                if row:
                    return dict(row)
                return None
            except Exception as e:
                logger.error(f"Error fetching profile for user {user_id}: {e}")
                return None

    async def save_profile(self, user_id: str, profile: Dict[str, Any]):
        """Save or update user profile."""
        async with self.get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO user_profiles (
                        user_id, name, email, phone, location, insurance_provider, 
                        insurance_id, emergency_contact, medical_history, preferences, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        location = EXCLUDED.location,
                        insurance_provider = EXCLUDED.insurance_provider,
                        insurance_id = EXCLUDED.insurance_id,
                        emergency_contact = EXCLUDED.emergency_contact,
                        medical_history = EXCLUDED.medical_history,
                        preferences = EXCLUDED.preferences,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    user_id,
                    profile.get('name'),
                    profile.get('email'),
                    profile.get('phone'),
                    profile.get('location'),
                    profile.get('insurance_provider'),
                    profile.get('insurance_id'),
                    json.dumps(profile.get('emergency_contact', {})),
                    json.dumps(profile.get('medical_history', {})),
                    json.dumps(profile.get('preferences', {}))
                )
                logger.info(f"Profile saved for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving profile for user {user_id}: {e}")
                raise

    async def save_treatments(self, user_id: str, treatments: List[Dict[str, Any]]):
        """Save treatment records for a user."""
        async with self.get_connection() as conn:
            try:
                for treatment in treatments:
                    await conn.execute("""
                        INSERT INTO treatment_records (
                            user_id, facility_id, treatment_type, status, start_date, 
                            end_date, notes, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                        user_id,
                        treatment.get('facility_id'),
                        treatment.get('treatment_type'),
                        treatment.get('status', 'active'),
                        treatment.get('start_date'),
                        treatment.get('end_date'),
                        treatment.get('notes'),
                        json.dumps(treatment.get('metadata', {}))
                    )
                logger.info(f"Saved {len(treatments)} treatment records for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving treatments for user {user_id}: {e}")
                raise

    async def fetch_treatments(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch treatment records for a user."""
        async with self.get_connection() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT tr.*, tf.name as facility_name, tf.address as facility_address
                    FROM treatment_records tr
                    LEFT JOIN treatment_facilities tf ON tr.facility_id = tf.facility_id
                    WHERE tr.user_id = $1
                    ORDER BY tr.created_at DESC
                """, user_id)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error fetching treatments for user {user_id}: {e}")
                return []

    async def save_appointments(self, user_id: str, appointments: List[Dict[str, Any]]):
        """Save appointments for a user."""
        async with self.get_connection() as conn:
            try:
                for appointment in appointments:
                    await conn.execute("""
                        INSERT INTO appointments (
                            user_id, facility_id, appointment_datetime, appointment_type,
                            status, urgency_level, notes, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                        user_id,
                        appointment.get('facility_id'),
                        appointment.get('appointment_datetime'),
                        appointment.get('appointment_type'),
                        appointment.get('status', 'scheduled'),
                        appointment.get('urgency_level', 'routine'),
                        appointment.get('notes'),
                        json.dumps(appointment.get('metadata', {}))
                    )
                logger.info(f"Saved {len(appointments)} appointments for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving appointments for user {user_id}: {e}")
                raise

    async def fetch_appointments(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch appointments for a user."""
        async with self.get_connection() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT a.*, tf.name as facility_name, tf.address as facility_address, tf.phone as facility_phone
                    FROM appointments a
                    LEFT JOIN treatment_facilities tf ON a.facility_id = tf.facility_id
                    WHERE a.user_id = $1
                    ORDER BY a.appointment_datetime ASC
                """, user_id)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error fetching appointments for user {user_id}: {e}")
                return []

    async def save_treatment_data(self, user_id: str, data: Dict[str, Any]):
        """Save general treatment data."""
        # This can be used for various treatment-related data storage
        pass

    async def get_treatment_data(self, user_id: str) -> Dict[str, Any]:
        """Get general treatment data."""
        # This can be used for various treatment-related data retrieval
        return {}

    async def update_treatment_status(self, user_id: str, status: str, **kwargs):
        """Update treatment status."""
        # Implementation for updating treatment status
        pass

    async def get_treatment_status(self, user_id: str):
        """Get treatment status."""
        # Implementation for getting treatment status
        return {}

    async def track_api_usage(self, user_id: str, tool_name: str, operation_type: str, 
                             api_provider: str, tokens_used: int = 0, estimated_cost: float = 0.0, 
                             pages_scraped: int = 0, metadata: dict = None):
        """Track API usage for billing and monitoring."""
        async with self.get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO api_usage (
                        user_id, tool_name, operation_type, api_provider,
                        tokens_used, estimated_cost, pages_scraped, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    user_id, tool_name, operation_type, api_provider,
                    tokens_used, estimated_cost, pages_scraped,
                    json.dumps(metadata or {})
                )
            except Exception as e:
                logger.error(f"Error tracking API usage for user {user_id}: {e}")

    async def get_user_usage_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get user usage statistics."""
        async with self.get_connection() as conn:
            try:
                cutoff_date = datetime.now() - timedelta(days=days)
                
                # Get total usage stats
                row = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_requests,
                        SUM(tokens_used) as total_tokens,
                        SUM(estimated_cost) as total_cost,
                        SUM(pages_scraped) as total_pages
                    FROM api_usage 
                    WHERE user_id = $1 AND timestamp >= $2
                """, user_id, cutoff_date)
                
                stats = dict(row) if row else {}
                
                # Get usage by tool
                tool_stats = await conn.fetch("""
                    SELECT 
                        tool_name,
                        COUNT(*) as requests,
                        SUM(tokens_used) as tokens,
                        SUM(estimated_cost) as cost
                    FROM api_usage 
                    WHERE user_id = $1 AND timestamp >= $2
                    GROUP BY tool_name
                    ORDER BY requests DESC
                """, user_id, cutoff_date)
                
                stats['by_tool'] = [dict(row) for row in tool_stats]
                return stats
                
            except Exception as e:
                logger.error(f"Error getting usage stats for user {user_id}: {e}")
                return {}

    async def save_insurance_verification(self, user_id: str, verification_data: Dict[str, Any]):
        """Save insurance verification results."""
        async with self.get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO insurance_verifications (
                        user_id, insurance_provider, insurance_id, treatment_type,
                        coverage_status, coverage_details, expires_at, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    user_id,
                    verification_data.get('insurance_provider'),
                    verification_data.get('insurance_id'),
                    verification_data.get('treatment_type'),
                    verification_data.get('coverage_status'),
                    json.dumps(verification_data.get('coverage_details', {})),
                    verification_data.get('expires_at'),
                    json.dumps(verification_data.get('metadata', {}))
                )
                logger.info(f"Insurance verification saved for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving insurance verification for user {user_id}: {e}")
                raise

    async def save_treatment_reminder(self, user_id: str, reminder_data: Dict[str, Any]):
        """Save treatment reminder."""
        async with self.get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO treatment_reminders (
                        user_id, reminder_type, title, description, reminder_datetime,
                        is_recurring, recurrence_pattern, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    user_id,
                    reminder_data.get('reminder_type'),
                    reminder_data.get('title'),
                    reminder_data.get('description'),
                    reminder_data.get('reminder_datetime'),
                    reminder_data.get('is_recurring', False),
                    reminder_data.get('recurrence_pattern'),
                    json.dumps(reminder_data.get('metadata', {}))
                )
                logger.info(f"Treatment reminder saved for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving treatment reminder for user {user_id}: {e}")
                raise

    async def get_upcoming_reminders(self, user_id: str, hours_ahead: int = 24) -> List[Dict[str, Any]]:
        """Get upcoming reminders for a user."""
        async with self.get_connection() as conn:
            try:
                cutoff_time = datetime.now() + timedelta(hours=hours_ahead)
                rows = await conn.fetch("""
                    SELECT * FROM treatment_reminders 
                    WHERE user_id = $1 
                    AND reminder_datetime <= $2 
                    AND status = 'active'
                    AND sent_at IS NULL
                    ORDER BY reminder_datetime ASC
                """, user_id, cutoff_time)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error getting upcoming reminders for user {user_id}: {e}")
                return []

    async def reset_database(self):
        """Drop all tables and recreate them - useful for development."""
        async with self.get_connection() as conn:
            logger.info("Dropping all existing tables...")
            
            # Drop tables in reverse dependency order
            drop_tables = [
                "communication_logs",
                "api_usage", 
                "treatment_reminders",
                "insurance_verifications",
                "appointments",
                "treatment_records",
                "treatment_facilities",
                "user_profiles"
            ]
            
            for table in drop_tables:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    logger.info(f"Dropped table: {table}")
                except Exception as e:
                    logger.warning(f"Error dropping table {table}: {e}")
            
            logger.info("All tables dropped. Creating fresh schema...")
            await self.create_tables()

# Global database manager instance
db_manager = DatabaseManager()

# Convenience functions for backward compatibility
async def fetch_profile(user_id: str) -> Optional[Dict[str, Any]]:
    return await db_manager.fetch_profile(user_id)

async def save_profile(user_id: str, profile: Dict[str, Any]):
    await db_manager.save_profile(user_id, profile)

async def save_treatments(user_id: str, treatments: List[Dict[str, Any]]):
    await db_manager.save_treatments(user_id, treatments)

async def fetch_treatments(user_id: str) -> List[Dict[str, Any]]:
    return await db_manager.fetch_treatments(user_id)

async def save_appointments(user_id: str, appointments: List[Dict[str, Any]]):
    await db_manager.save_appointments(user_id, appointments)

async def fetch_appointments(user_id: str) -> List[Dict[str, Any]]:
    return await db_manager.fetch_appointments(user_id)

async def save_treatment_data(user_id: str, data: Dict[str, Any]):
    await db_manager.save_treatment_data(user_id, data)

async def get_treatment_data(user_id: str) -> Dict[str, Any]:
    return await db_manager.get_treatment_data(user_id)

async def update_treatment_status(user_id: str, status: str, **kwargs):
    await db_manager.update_treatment_status(user_id, status, **kwargs)

async def get_treatment_status(user_id: str):
    return await db_manager.get_treatment_status(user_id)

async def track_api_usage(user_id: str, tool_name: str, operation_type: str, 
                         api_provider: str, tokens_used: int = 0, estimated_cost: float = 0.0, 
                         pages_scraped: int = 0, metadata: dict = None):
    await db_manager.track_api_usage(user_id, tool_name, operation_type, api_provider, 
                                   tokens_used, estimated_cost, pages_scraped, metadata)

async def get_user_usage_stats(user_id: str, days: int = 30) -> Dict[str, Any]:
    return await db_manager.get_user_usage_stats(user_id, days)
