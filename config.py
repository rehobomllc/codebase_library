import os
from typing import List, Optional
from dotenv import load_dotenv
import ssl
import certifi

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# SSL Configuration for macOS certificate issues
SSL_VERIFY = True
SSL_CERT_FILE = certifi.where()

# Set SSL context
ssl_context = ssl.create_default_context(cafile=SSL_CERT_FILE)
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

class Config:
    """Enhanced configuration management for app with Arcade and OpenAI Agents SDK integration."""

    # --- Core API Keys ---
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ARCADE_API_KEY: Optional[str] = os.getenv("ARCADE_API_KEY")
    FIRECRAWL_API_KEY: Optional[str] = os.getenv("FIRECRAWL_API_KEY") # Required for Arcade Web tools (e.g., crawling)

    # --- Database & Redis ---
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Agent Configuration ---
    DEFAULT_AGENT_MODEL: str = os.getenv("DEFAULT_AGENT_MODEL", "gpt-4.1") # Default model for agents
    
    # --- Vision Configuration ---
    VISION_MODEL: str = os.getenv("VISION_MODEL", "gpt-4o") # Model for vision analysis using Responses API
    MAX_VISION_FILE_SIZE_MB: int = int(os.getenv("MAX_VISION_FILE_SIZE_MB", "20")) # Max file size for image uploads
    SUPPORTED_IMAGE_FORMATS: List[str] = os.getenv("SUPPORTED_IMAGE_FORMATS", "jpg,jpeg,png,gif,webp").split(",")
    VISION_MAX_OUTPUT_TOKENS: int = int(os.getenv("VISION_MAX_OUTPUT_TOKENS", "1000"))
    ENABLE_VISION_ANALYSIS: bool = os.getenv("ENABLE_VISION_ANALYSIS", "true").lower() == "true"

    # --- Enhanced Validation Settings ---
    VALIDATION_AGENT_VERSION: str = os.getenv("VALIDATION_AGENT_VERSION", "v2_arcade")
    MAX_CONCURRENT_VALIDATIONS: int = int(os.getenv("MAX_CONCURRENT_VALIDATIONS", "3"))
    SCRAPE_TIMEOUT_SECONDS: int = int(os.getenv("SCRAPE_TIMEOUT_SECONDS", "30"))
    MAX_PAGES_PER_TREATMENT: int = int(os.getenv("MAX_PAGES_PER_TREATMENT", "5"))

    # --- Cost Management ---
    DAILY_API_COST_LIMIT: float = float(os.getenv("DAILY_API_COST_LIMIT", "10.00"))
    MONTHLY_API_COST_LIMIT: float = float(os.getenv("MONTHLY_API_COST_LIMIT", "100.00"))
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))

    # --- Monitoring Configuration ---
    ENABLE_TREATMENT_MONITORING: bool = os.getenv("ENABLE_TREATMENT_MONITORING", "true").lower() == "true"
    MONITORING_INTERVAL_HOURS: int = int(os.getenv("MONITORING_INTERVAL_HOURS", "24"))
    TARGET_MONITORING_SITES: List[str] = os.getenv(
        "TARGET_MONITORING_SITES",
        "https://www.clinicaltrials.gov,https://www.cdc.gov,https://www.nih.gov"
    ).split(",")

    # --- Performance Settings ---
    ESSAY_EXTRACTION_TIMEOUT: int = int(os.getenv("ESSAY_EXTRACTION_TIMEOUT", "120"))
    VALIDATION_CACHE_TTL: int = int(os.getenv("VALIDATION_CACHE_TTL", "3600")) # In seconds
    MAX_SEARCH_RESULTS_PER_QUERY: int = int(os.getenv("MAX_SEARCH_RESULTS_PER_QUERY", "15"))

    # --- Feature Flags ---
    ENABLE_ARCADE_VALIDATION: bool = os.getenv("ENABLE_ARCADE_VALIDATION", "true").lower() == "true"
    ENABLE_ARCADE_ESSAY_EXTRACTION: bool = os.getenv("ENABLE_ARCADE_ESSAY_EXTRACTION", "true").lower() == "true"
    ENABLE_PROACTIVE_MONITORING: bool = os.getenv("ENABLE_PROACTIVE_MONITORING", "true").lower() == "true"
    ENABLE_COST_TRACKING: bool = os.getenv("ENABLE_COST_TRACKING", "true").lower() == "true"
    # Enables Google integration via Arcade for features like Docs, Calendar, Reminders
    ENABLE_ARCADE_GOOGLE_TOOLS: bool = os.getenv("ENABLE_ARCADE_GOOGLE_TOOLS", "true").lower() == "true"
    
    # Enhanced Arcade Features
    ENABLE_SLACK_INTEGRATION: bool = os.getenv("ENABLE_SLACK_INTEGRATION", "false").lower() == "true"
    ENABLE_LINKEDIN_INTEGRATION: bool = os.getenv("ENABLE_LINKEDIN_INTEGRATION", "false").lower() == "true"
    ENABLE_GITHUB_INTEGRATION: bool = os.getenv("ENABLE_GITHUB_INTEGRATION", "false").lower() == "true"
    ENABLE_NOTION_INTEGRATION: bool = os.getenv("ENABLE_NOTION_INTEGRATION", "false").lower() == "true"
    ENABLE_ARXIV_RESEARCH: bool = os.getenv("ENABLE_ARXIV_RESEARCH", "true").lower() == "true"
    ENABLE_STRIPE_PAYMENT: bool = os.getenv("ENABLE_STRIPE_PAYMENT", "false").lower() == "true"
    ENABLE_X_SOCIAL: bool = os.getenv("ENABLE_X_SOCIAL", "false").lower() == "true"
    
    # Agent Optimization Features
    ENABLE_AGENT_OPTIMIZATION: bool = os.getenv("ENABLE_AGENT_OPTIMIZATION", "true").lower() == "true"
    ENABLE_PROACTIVE_AUTH_CHECKS: bool = os.getenv("ENABLE_PROACTIVE_AUTH_CHECKS", "true").lower() == "true"
    AGENT_TOOL_CACHING: bool = os.getenv("AGENT_TOOL_CACHING", "true").lower() == "true"
    
    # Advanced Toolkit Configuration
    PREFERRED_TOOLKITS: List[str] = os.getenv(
        "PREFERRED_TOOLKITS", 
        "google,web,arxiv"
    ).split(",")
    
    RESTRICTED_TOOLKITS: List[str] = os.getenv(
        "RESTRICTED_TOOLKITS", 
        ""
    ).split(",") if os.getenv("RESTRICTED_TOOLKITS") else []

    # --- Error Handling ---
    MAX_RETRIES_VALIDATION: int = int(os.getenv("MAX_RETRIES_VALIDATION", "2"))
    MAX_RETRIES_EXTRACTION: int = int(os.getenv("MAX_RETRIES_EXTRACTION", "3"))
    GRACEFUL_DEGRADATION: bool = os.getenv("GRACEFUL_DEGRADATION", "true").lower() == "true"

    # --- Debug Settings ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    ENABLE_DETAILED_LOGGING: bool = os.getenv("ENABLE_DETAILED_LOGGING", "false").lower() == "true"
    TRACE_API_CALLS: bool = os.getenv("TRACE_API_CALLS", "false").lower() == "true" # For OpenAI/Arcade tracing

    # --- SSL Configuration for Uvicorn (read from .env, used by app.py) ---
    USE_HTTPS: bool = os.getenv("USE_HTTPS", "false").lower() == "true"
    SSL_CERT_FILE: Optional[str] = os.getenv("SSL_CERT_FILE")
    SSL_KEY_FILE: Optional[str] = os.getenv("SSL_KEY_FILE")
    APP_URL: str = os.getenv("APP_URL", "http://localhost:5000")


    @classmethod
    def validate_configuration(cls) -> List[str]:
        """Validate configuration and return list of missing/invalid settings."""
        errors: List[str] = []

        # Check required API keys
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required for AI agent functionality.")
        if not cls.ARCADE_API_KEY:
            errors.append("ARCADE_API_KEY is required for Arcade tool integration (including Google tools).")

        # FIRECRAWL_API_KEY is needed if Arcade web tools (validation, essay extraction via web) are enabled
        arcade_web_features_enabled = cls.ENABLE_ARCADE_VALIDATION or cls.ENABLE_ARCADE_ESSAY_EXTRACTION
        if arcade_web_features_enabled and not cls.FIRECRAWL_API_KEY:
            errors.append("FIRECRAWL_API_KEY is required when ENABLE_ARCADE_VALIDATION or ENABLE_ARCADE_ESSAY_EXTRACTION is true, as these may use Arcade's web crawling tools.")

        if not cls.DATABASE_URL:
            errors.append("DATABASE_URL is required for storing application data.")

        # Check cost limits
        if cls.DAILY_API_COST_LIMIT <= 0:
            errors.append("DAILY_API_COST_LIMIT must be a positive value.")
        if cls.MONTHLY_API_COST_LIMIT <= 0:
            errors.append("MONTHLY_API_COST_LIMIT must be a positive value.")

        # Check performance settings
        if not (1 <= cls.MAX_CONCURRENT_VALIDATIONS <= 10):
            errors.append("MAX_CONCURRENT_VALIDATIONS should be between 1 and 10 for optimal performance and resource usage.")

        # Check vision configuration
        if cls.ENABLE_VISION_ANALYSIS:
            if cls.MAX_VISION_FILE_SIZE_MB <= 0 or cls.MAX_VISION_FILE_SIZE_MB > 100:
                errors.append("MAX_VISION_FILE_SIZE_MB should be between 1 and 100 MB.")
            if not cls.SUPPORTED_IMAGE_FORMATS:
                errors.append("SUPPORTED_IMAGE_FORMATS cannot be empty when vision analysis is enabled.")
            if cls.VISION_MAX_OUTPUT_TOKENS < 100 or cls.VISION_MAX_OUTPUT_TOKENS > 4000:
                errors.append("VISION_MAX_OUTPUT_TOKENS should be between 100 and 4000.")

        # Check SSL configuration if HTTPS is enabled
        if cls.USE_HTTPS:
            if not cls.SSL_CERT_FILE:
                errors.append("SSL_CERT_FILE is required when USE_HTTPS is true.")
            if not cls.SSL_KEY_FILE:
                errors.append("SSL_KEY_FILE is required when USE_HTTPS is true.")
            if not cls.APP_URL.startswith("https://"):
                errors.append("APP_URL should start with https:// when USE_HTTPS is true.")
        elif not cls.APP_URL.startswith("http://"):
             errors.append("APP_URL should start with http:// when USE_HTTPS is false.")


        return errors

    @classmethod
    def get_arcade_features_status(cls) -> dict:
        """Get status of Arcade-enhanced features."""
        arcade_web_dependent_features_ok = bool(cls.FIRECRAWL_API_KEY) or not (cls.ENABLE_ARCADE_VALIDATION or cls.ENABLE_ARCADE_ESSAY_EXTRACTION)
        google_tools_ok = bool(cls.ARCADE_API_KEY) or not cls.ENABLE_ARCADE_GOOGLE_TOOLS

        return {
            "arcade_api_key_set": bool(cls.ARCADE_API_KEY),
            "firecrawl_api_key_set": bool(cls.FIRECRAWL_API_KEY),
            "validation_enabled": cls.ENABLE_ARCADE_VALIDATION,
            "essay_extraction_enabled": cls.ENABLE_ARCADE_ESSAY_EXTRACTION,
            "google_tools_enabled": cls.ENABLE_ARCADE_GOOGLE_TOOLS,
            "monitoring_enabled": cls.ENABLE_PROACTIVE_MONITORING,
            "cost_tracking_enabled": cls.ENABLE_COST_TRACKING,
            "vision_analysis_enabled": cls.ENABLE_VISION_ANALYSIS,
            "arcade_web_features_operational": arcade_web_dependent_features_ok,
            "arcade_google_tools_operational": google_tools_ok,
            "vision_features_operational": bool(cls.OPENAI_API_KEY) or not cls.ENABLE_VISION_ANALYSIS,
            "overall_configuration_valid": len(cls.validate_configuration()) == 0
        }

# Global configuration instance
config = Config()

# Perform validation on import to give early feedback
CONFIG_ERRORS = config.validate_configuration()
if CONFIG_ERRORS:
    print("CRITICAL CONFIGURATION ERRORS DETECTED:")
    for error in CONFIG_ERRORS:
        print(f"- {error}")
    print("Please fix the .env file and restart the application.")
    # Optionally, raise an exception or sys.exit() in a real application startup
    # For now, just printing to console during development.
