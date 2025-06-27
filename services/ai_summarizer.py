#!/usr/bin/env python3
"""
AI-powered treatment text summarization service using GPT-4.1

This module provides functions to:
1. Summarize lengthy treatment descriptions into concise, readable formats
2. Extract key eligibility criteria and requirements as bullet points
3. Cache results to avoid redundant API calls
4. Handle API failures gracefully with fallbacks

@file purpose: Provides AI summarization capabilities for treatment content
"""

import asyncio
import hashlib
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TreatmentSummarizer:
    def __init__(self):
        """Initialize the AI summarizer with OpenAI client"""
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "gpt-4o"  # Using the new GPT-4.1 model
        self.cache = {}  # Simple in-memory cache
        
    def _generate_cache_key(self, text: str) -> str:
        """Generate a cache key from treatment text"""
        return hashlib.md5(text.encode()).hexdigest()
    
    async def summarize_treatment(self, treatment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarize treatment content using GPT-4.1
        
        Args:
            treatment_data: Dictionary containing treatment information
            
        Returns:
            Dictionary with original data plus AI-generated summary
        """
        try:
            # Extract text content for summarization
            text_content = self._extract_treatment_text(treatment_data)
            
            if not text_content.strip():
                return treatment_data
                
            # Check cache first
            cache_key = self._generate_cache_key(text_content)
            if cache_key in self.cache:
                summary_data = self.cache[cache_key]
            else:
                # Generate AI summary
                summary_data = await self._generate_ai_summary(text_content, treatment_data.get('title', 'Treatment'))
                self.cache[cache_key] = summary_data
            
            # Add AI summary to treatment data
            treatment_data['ai_summary'] = summary_data
            return treatment_data
            
        except Exception as e:
            print(f"Error summarizing treatment: {e}")
            # Return original data if summarization fails
            return treatment_data
    
    def _extract_treatment_text(self, treatment: Dict[str, Any]) -> str:
        """Extract all relevant text content from treatment data"""
        text_parts = []
        
        # Main description
        if treatment.get('description'):
            text_parts.append(f"Description: {treatment['description']}")
        elif treatment.get('summary'):
            text_parts.append(f"Summary: {treatment['summary']}")
            
        # Eligibility criteria
        if treatment.get('eligibility') and isinstance(treatment['eligibility'], list):
            text_parts.append(f"Eligibility: {' '.join(treatment['eligibility'])}")
        elif treatment.get('eligibility_criteria') and isinstance(treatment['eligibility_criteria'], list):
            text_parts.append(f"Criteria: {' '.join(treatment['eligibility_criteria'])}")
            
        # Additional requirements
        if treatment.get('additional_requirements') and isinstance(treatment['additional_requirements'], list):
            text_parts.append(f"Requirements: {' '.join(treatment['additional_requirements'])}")
            
        # Treatment types and conditions
        if treatment.get('treatment_types'):
            types = treatment['treatment_types']
            if isinstance(types, list):
                text_parts.append(f"Treatment Types: {', '.join(types)}")
            else:
                text_parts.append(f"Treatment Types: {types}")
                
        if treatment.get('conditions_treated'):
            conditions = treatment['conditions_treated']
            if isinstance(conditions, list):
                text_parts.append(f"Conditions Treated: {', '.join(conditions)}")
            else:
                text_parts.append(f"Conditions Treated: {conditions}")
        
        return ' | '.join(text_parts)
    
    async def _generate_ai_summary(self, text_content: str, title: str) -> Dict[str, Any]:
        """Generate AI summary using GPT-4.1"""
        
        prompt = f"""
        Summarize the following treatment information into a clean, readable format:

        Treatment: {title}
        Content: {text_content}

        Please provide:
        1. A brief 1-2 sentence overview
        2. Key eligibility requirements as bullet points (max 4-5 points)
        3. Important details as bullet points (max 3-4 points)

        Format your response as JSON with this structure:
        {{
            "overview": "Brief 1-2 sentence summary",
            "eligibility_points": ["Point 1", "Point 2", "Point 3"],
            "key_details": ["Detail 1", "Detail 2", "Detail 3"]
        }}

        Keep each bullet point concise (under 15 words). Focus on the most important and actionable information.
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at summarizing treatment information clearly and concisely. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            summary_data = json.loads(content)
            
            # Validate structure
            required_keys = ['overview', 'eligibility_points', 'key_details']
            if all(key in summary_data for key in required_keys):
                return summary_data
            else:
                raise ValueError("Invalid response structure")
                
        except Exception as e:
            print(f"Error generating AI summary: {e}")
            # Fallback to simple text processing
            return self._generate_fallback_summary(text_content)
    
    def _generate_fallback_summary(self, text_content: str) -> Dict[str, Any]:
        """Generate a simple fallback summary if AI fails"""
        # Simple text processing fallback
        sentences = text_content.split('. ')
        overview = sentences[0] if sentences else "Treatment opportunity available."
        
        return {
            "overview": overview,
            "eligibility_points": ["Check official requirements"],
            "key_details": ["Visit treatment website for full details"]
        }

# Global summarizer instance
summarizer = TreatmentSummarizer()

async def summarize_treatment_batch(treatments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize a batch of treatments concurrently
    
    Args:
        treatments: List of treatment dictionaries
        
    Returns:
        List of treatments with AI summaries added
    """
    tasks = [summarizer.summarize_treatment(treatment) for treatment in treatments]
    return await asyncio.gather(*tasks)

async def summarize_single_treatment(treatment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize a single treatment
    
    Args:
        treatment: Treatment dictionary
        
    Returns:
        Treatment with AI summary added
    """
    return await summarizer.summarize_treatment(treatment) 