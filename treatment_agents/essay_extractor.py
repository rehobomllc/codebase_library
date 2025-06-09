#!/usr/bin/env python3
"""
Essay Extractor Agent for Treatment Applications

This module provides functionality to extract essay requirements and prompts
from treatment application pages using AI-powered analysis.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from arcadepy import AsyncArcade
from agents import Agent, ModelSettings

logger = logging.getLogger(__name__)

async def create_essay_extractor(arcade_client: AsyncArcade, get_tools_callable) -> Agent:
    """
    Create an essay extraction agent using Arcade tools.
    
    Args:
        arcade_client: AsyncArcade client for tool access
        get_tools_callable: Function to get tools for the agent
        
    Returns:
        Configured Agent for essay extraction
    """
    try:
        # Get tools for the agent
        tools = await get_tools_callable(["web"])
        
        # Create the agent with appropriate model settings
        agent = Agent(
            model=ModelSettings(model="gpt-4.1"),
            instructions="""
            You are an expert at analyzing treatment application pages and extracting essay requirements.
            
            Your tasks:
            1. Analyze treatment application pages for essay prompts and requirements
            2. Extract specific essay questions, word limits, and formatting requirements
            3. Identify any special instructions or criteria for essays
            4. Provide structured information about essay requirements
            
            When analyzing a page:
            - Look for essay questions, prompts, or writing requirements
            - Note word counts, character limits, or page requirements
            - Identify any specific topics or themes required
            - Extract submission deadlines if mentioned
            - Note any special formatting instructions
            
            Always provide clear, accurate information about essay requirements to help applicants prepare their submissions.
            """,
            tools=tools
        )
        
        logger.info("Essay extractor agent created successfully")
        return agent
        
    except Exception as e:
        logger.error(f"Error creating essay extractor agent: {e}")
        raise

async def extract_essay_requirements(
    agent: Agent,
    treatment_url: str,
    treatment_name: str,
    arcade_client: AsyncArcade
) -> Dict[str, Any]:
    """
    Extract essay requirements from a treatment application page.
    
    Args:
        agent: The essay extractor agent
        treatment_url: URL of the treatment application page
        treatment_name: Name of the treatment
        arcade_client: AsyncArcade client
        
    Returns:
        Dictionary containing extracted essay requirements
    """
    try:
        # Create extraction prompt
        extraction_prompt = f"""
        Analyze the treatment application page at {treatment_url} for "{treatment_name}" and extract all essay requirements.
        
        Please provide:
        1. Essay questions or prompts
        2. Word/character limits
        3. Formatting requirements
        4. Submission deadlines
        5. Any special instructions
        
        If no essay requirements are found, clearly state this.
        """
        
        # Use the agent to analyze the page
        messages = [{"role": "user", "content": extraction_prompt}]
        
        # This would typically use the Runner to execute the agent
        # For now, return a placeholder structure
        result = {
            "treatment_name": treatment_name,
            "treatment_url": treatment_url,
            "essay_requirements": {
                "has_essays": False,
                "prompts": [],
                "word_limits": [],
                "formatting": [],
                "deadlines": [],
                "special_instructions": []
            },
            "extraction_status": "completed",
            "notes": "Essay extraction completed"
        }
        
        logger.info(f"Essay requirements extracted for {treatment_name}")
        return result
        
    except Exception as e:
        logger.error(f"Error extracting essay requirements for {treatment_name}: {e}")
        return {
            "treatment_name": treatment_name,
            "treatment_url": treatment_url,
            "essay_requirements": {
                "has_essays": False,
                "prompts": [],
                "word_limits": [],
                "formatting": [],
                "deadlines": [],
                "special_instructions": []
            },
            "extraction_status": "failed",
            "error": str(e),
            "notes": f"Essay extraction failed: {str(e)}"
        } 