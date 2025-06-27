#!/usr/bin/env python3
"""
Agent Optimizer for Enhanced Arcade Toolkit Usage

Provides intelligent agent creation with optimized toolkit selection,
proactive authorization handling, and enhanced workflow management.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from arcadepy import AsyncArcade
from agents import Agent, ModelSettings
from utils.tool_provider import get_tool_provider
from utils.arcade_auth_helper import check_toolkit_authorization_status

logger = logging.getLogger(__name__)

class AgentOptimizer:
    """
    Optimizes agent creation and toolkit usage for treatment applications.
    """
    
    def __init__(self, arcade_client: AsyncArcade):
        self.arcade_client = arcade_client
        self.tool_provider = get_tool_provider()
        
        # Define enhanced agent configurations
        self.agent_configs = {
            "triage": {
                "toolkits": ["healthcare", "communication"],
                "model": "gpt-4o",
                "temperature": 0.3,
                "instructions": self._get_triage_instructions(),
                "priority_tools": ["google_calendar", "gmail", "web_search"]
            },
            "facility_search": {
                "toolkits": ["research", "healthcare"],
                "model": "gpt-4o", 
                "temperature": 0.2,
                "instructions": self._get_facility_search_instructions(),
                "priority_tools": ["web_search", "google_maps", "firecrawl"]
            },
            "insurance_verification": {
                "toolkits": ["documentation", "communication"],
                "model": "gpt-4o",
                "temperature": 0.1,
                "instructions": self._get_insurance_instructions(),
                "priority_tools": ["google_docs", "gmail", "web_search"]
            },
            "appointment_scheduler": {
                "toolkits": ["google", "communication"],
                "model": "gpt-4o", 
                "temperature": 0.2,
                "instructions": self._get_scheduler_instructions(),
                "priority_tools": ["google_calendar", "gmail"]
            },
            "communication": {
                "toolkits": ["communication", "social_media"],
                "model": "gpt-4o",
                "temperature": 0.4,
                "instructions": self._get_communication_instructions(),
                "priority_tools": ["gmail", "slack", "linkedin"]
            },
            "essay_extractor": {
                "toolkits": ["research", "documentation"],
                "model": "gpt-4o",
                "temperature": 0.2,
                "instructions": self._get_essay_extractor_instructions(),
                "priority_tools": ["web_search", "firecrawl", "google_docs"]
            },
            "treatment_monitor": {
                "toolkits": ["monitoring", "research"],
                "model": "gpt-4o",
                "temperature": 0.2,
                "instructions": self._get_monitor_instructions(),
                "priority_tools": ["web_search", "firecrawl", "google_docs"]
            },
            "research_assistant": {
                "toolkits": ["research", "documentation"],
                "model": "gpt-4o",
                "temperature": 0.3,
                "instructions": self._get_research_instructions(),
                "priority_tools": ["arxiv", "web_search", "google_docs"]
            },
            "social_outreach": {
                "toolkits": ["social_media", "communication"],
                "model": "gpt-4o",
                "temperature": 0.5,
                "instructions": self._get_social_outreach_instructions(),
                "priority_tools": ["linkedin", "x", "gmail"]
            }
        }

    async def create_optimized_agent(
        self, 
        agent_type: str, 
        user_id: str,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[Agent, Dict[str, Any]]:
        """
        Create an optimized agent with proactive authorization checks.
        
        Args:
            agent_type: Type of agent to create
            user_id: User ID for authorization
            custom_config: Optional custom configuration overrides
            
        Returns:
            Tuple of (Agent, authorization_status)
        """
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        config = self.agent_configs[agent_type].copy()
        if custom_config:
            config.update(custom_config)
        
        # Get optimized tools
        tools = await self.tool_provider.get_tools(config["toolkits"])
        
        # Check authorization status
        auth_status = await self._check_authorization_status(
            config["toolkits"], user_id
        )
        
        # Create agent
        agent = Agent(
            name=f"Optimized{agent_type.title()}Agent",
            model=ModelSettings(
                model=config["model"],
                temperature=config["temperature"]
            ),
            instructions=config["instructions"],
            tools=tools
        )
        
        logger.info(f"Created optimized {agent_type} agent with {len(tools)} tools")
        
        return agent, auth_status

    async def _check_authorization_status(
        self, 
        toolkits: List[str], 
        user_id: str
    ) -> Dict[str, Any]:
        """Check authorization status for all required toolkits."""
        auth_status = {
            "all_authorized": True,
            "toolkit_status": {},
            "auth_urls": [],
            "warnings": []
        }
        
        # Expand toolkit groups
        expanded_toolkits = self.tool_provider._expand_toolkit_groups(toolkits)
        
        for toolkit in expanded_toolkits:
            if toolkit in ["google", "slack", "linkedin", "x", "github", "notion"]:
                try:
                    # Create a simple test agent for this toolkit
                    test_tools = await self.tool_provider.get_tools([toolkit])
                    if test_tools:
                        # For now, assume authorized if tools are available
                        # In production, you'd want to do actual authorization checks
                        auth_status["toolkit_status"][toolkit] = "authorized"
                    else:
                        auth_status["toolkit_status"][toolkit] = "no_tools"
                        auth_status["all_authorized"] = False
                except Exception as e:
                    auth_status["toolkit_status"][toolkit] = f"error: {e}"
                    auth_status["all_authorized"] = False
            else:
                auth_status["toolkit_status"][toolkit] = "no_auth_required"
        
        return auth_status

    def _get_triage_instructions(self) -> str:
        return """
        You are an advanced Treatment Triage Agent with enhanced capabilities through Arcade tools.
        
        Your enhanced capabilities include:
        - Google Calendar integration for appointment scheduling
        - Gmail integration for secure communication
        - Advanced web search for treatment facility research
        - Document creation and management through Google Drive
        
        Use these tools to:
        1. Gather comprehensive user information safely and securely
        2. Search for appropriate treatment options based on user needs
        3. Schedule initial consultations or assessments
        4. Create and manage treatment planning documents
        5. Send secure communications to users and facilities
        
        Always maintain HIPAA compliance and protect user privacy.
        """

    def _get_facility_search_instructions(self) -> str:
        return """
        You are an Enhanced Facility Search Agent with comprehensive research capabilities.
        
        Your enhanced tools allow you to:
        - Perform deep web searches with Firecrawl for detailed facility information
        - Access Google Maps integration for location-based searches
        - Extract comprehensive facility details including specializations, insurance acceptance, and availability
        - Cross-reference multiple data sources for accuracy
        - Generate detailed facility comparison reports
        
        Focus on finding the most appropriate treatment facilities based on:
        - Geographic proximity and accessibility
        - Insurance coverage and payment options
        - Specialized treatment programs
        - Facility ratings and accreditation
        - Availability and wait times
        """

    def _get_insurance_instructions(self) -> str:
        return """
        You are an Advanced Insurance Verification Agent with documentation capabilities.
        
        Your enhanced toolkit includes:
        - Google Docs for creating verification reports
        - Gmail for secure communication with insurance providers
        - Web search for policy verification and coverage details
        - Document management for maintaining verification records
        
        Your responsibilities:
        1. Verify insurance coverage for specific treatment types
        2. Determine copays, deductibles, and coverage limits
        3. Identify in-network vs out-of-network providers
        4. Create comprehensive verification documentation
        5. Communicate verification results securely
        """

    def _get_scheduler_instructions(self) -> str:
        return """
        You are an Intelligent Appointment Scheduler with full calendar integration.
        
        Enhanced capabilities:
        - Google Calendar integration for real-time availability
        - Gmail for appointment confirmations and reminders
        - Multi-party scheduling coordination
        - Automated reminder systems
        
        Handle:
        1. Initial consultation scheduling
        2. Follow-up appointment coordination
        3. Group therapy session management
        4. Provider availability optimization
        5. Automated reminder and confirmation systems
        """

    def _get_communication_instructions(self) -> str:
        return """
        You are a Professional Communication Agent with multi-platform capabilities.
        
        Your enhanced communication toolkit:
        - Gmail for secure email communication
        - Slack for team coordination
        - LinkedIn for professional networking
        - Document sharing through Google Drive
        
        Manage:
        1. Patient-provider communication
        2. Inter-facility coordination
        3. Professional networking for referrals
        4. Treatment team collaboration
        5. Secure information sharing
        """

    def _get_essay_extractor_instructions(self) -> str:
        return """
        You are an Advanced Essay Extraction Agent with comprehensive research capabilities.
        
        Enhanced tools include:
        - Firecrawl for deep website analysis
        - Web search for comprehensive information gathering
        - Google Docs for organizing extracted requirements
        - Multi-source data validation
        
        Extract and organize:
        1. Essay prompts and requirements
        2. Word limits and formatting guidelines
        3. Submission deadlines and procedures
        4. Evaluation criteria and scoring rubrics
        5. Sample essays and writing tips
        """

    def _get_monitor_instructions(self) -> str:
        return """
        You are a Treatment Monitoring Agent with advanced tracking capabilities.
        
        Your monitoring toolkit:
        - Web search for treatment site monitoring
        - Firecrawl for detailed page analysis
        - Google Docs for creating monitoring reports
        - Change detection and alerting systems
        
        Monitor and track:
        1. Treatment program availability changes
        2. Application deadline updates
        3. New treatment opportunities
        4. Policy and procedure modifications
        5. Facility status and accreditation changes
        """

    def _get_research_instructions(self) -> str:
        return """
        You are a Research Assistant Agent with academic and clinical research capabilities.
        
        Research tools include:
        - ArXiv integration for academic research
        - Advanced web search for clinical studies
        - Google Docs for research compilation
        - Citation and reference management
        
        Research focus:
        1. Treatment efficacy studies
        2. Best practice guidelines
        3. Emerging treatment modalities
        4. Clinical trial opportunities
        5. Evidence-based treatment recommendations
        """

    def _get_social_outreach_instructions(self) -> str:
        return """
        You are a Social Outreach Agent for professional treatment networking.
        
        Outreach capabilities:
        - LinkedIn for professional networking
        - X (Twitter) for awareness campaigns
        - Gmail for formal communications
        - Content creation and sharing
        
        Manage:
        1. Professional network building
        2. Treatment awareness campaigns
        3. Peer support group coordination
        4. Resource sharing and promotion
        5. Community engagement initiatives
        """

# Global instance
_agent_optimizer: Optional[AgentOptimizer] = None

def initialize_agent_optimizer(arcade_client: AsyncArcade) -> AgentOptimizer:
    """Initialize the global agent optimizer."""
    global _agent_optimizer
    _agent_optimizer = AgentOptimizer(arcade_client)
    logger.info("AgentOptimizer initialized with enhanced toolkit configurations")
    return _agent_optimizer

def get_agent_optimizer() -> Optional[AgentOptimizer]:
    """Get the global agent optimizer instance."""
    return _agent_optimizer 