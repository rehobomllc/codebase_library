#!/usr/bin/env python3
"""
AI-powered scholarship text summarization service using GPT-4.1

This module provides functions to:
1. Summarize lengthy scholarship descriptions into concise, readable formats
2. Extract key eligibility criteria and requirements as bullet points
3. Cache results to avoid redundant API calls
4. Handle API failures gracefully with fallbacks

@file purpose: Provides AI summarization capabilities for scholarship content
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

class ScholarshipSummarizer:
    def __init__(self):
        """Initialize the AI summarizer with OpenAI client"""
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "gpt-4.1"  # Using the new GPT-4.1 model
        self.cache = {}  # Simple in-memory cache
        
    def _generate_cache_key(self, text: str) -> str:
        """Generate a cache key from scholarship text"""
        return hashlib.md5(text.encode()).hexdigest()
    
    async def summarize_scholarship(self, scholarship_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarize scholarship content using GPT-4.1
        
        Args:
            scholarship_data: Dictionary containing scholarship information
            
        Returns:
            Dictionary with original data plus AI-generated summary
        """
        try:
            # Extract text content for summarization
            text_content = self._extract_scholarship_text(scholarship_data)
            
            if not text_content.strip():
                return scholarship_data
                
            # Check cache first
            cache_key = self._generate_cache_key(text_content)
            if cache_key in self.cache:
                summary_data = self.cache[cache_key]
            else:
                # Generate AI summary
                summary_data = await self._generate_ai_summary(text_content, scholarship_data.get('title', 'Scholarship'))
                self.cache[cache_key] = summary_data
            
            # Add AI summary to scholarship data
            scholarship_data['ai_summary'] = summary_data
            return scholarship_data
            
        except Exception as e:
            print(f"Error summarizing scholarship: {e}")
            # Return original data if summarization fails
            return scholarship_data
    
    def _extract_scholarship_text(self, scholarship: Dict[str, Any]) -> str:
        """Extract all relevant text content from scholarship data"""
        text_parts = []
        
        # Main description
        if scholarship.get('description'):
            text_parts.append(f"Description: {scholarship['description']}")
        elif scholarship.get('summary'):
            text_parts.append(f"Summary: {scholarship['summary']}")
            
        # Eligibility criteria
        if scholarship.get('eligibility') and isinstance(scholarship['eligibility'], list):
            text_parts.append(f"Eligibility: {' '.join(scholarship['eligibility'])}")
        elif scholarship.get('eligibility_criteria') and isinstance(scholarship['eligibility_criteria'], list):
            text_parts.append(f"Criteria: {' '.join(scholarship['eligibility_criteria'])}")
            
        # Additional requirements
        if scholarship.get('additional_requirements') and isinstance(scholarship['additional_requirements'], list):
            text_parts.append(f"Requirements: {' '.join(scholarship['additional_requirements'])}")
            
        # Academic levels and majors
        if scholarship.get('eligible_academic_levels'):
            levels = scholarship['eligible_academic_levels']
            if isinstance(levels, list):
                text_parts.append(f"Academic Levels: {', '.join(levels)}")
            else:
                text_parts.append(f"Academic Levels: {levels}")
                
        if scholarship.get('eligible_majors'):
            majors = scholarship['eligible_majors']
            if isinstance(majors, list):
                text_parts.append(f"Eligible Majors: {', '.join(majors)}")
            else:
                text_parts.append(f"Eligible Majors: {majors}")
        
        return ' | '.join(text_parts)
    
    async def _generate_ai_summary(self, text_content: str, title: str) -> Dict[str, Any]:
        """Generate AI summary using GPT-4.1"""
        
        prompt = f"""
        Summarize the following scholarship information into a clean, readable format:

        Scholarship: {title}
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
                    {"role": "system", "content": "You are an expert at summarizing scholarship information clearly and concisely. Always respond with valid JSON."},
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
        overview = sentences[0] if sentences else "Scholarship opportunity available."
        
        return {
            "overview": overview,
            "eligibility_points": ["Check official requirements"],
            "key_details": ["Visit scholarship website for full details"]
        }

# Global summarizer instance
summarizer = ScholarshipSummarizer()

async def summarize_scholarship_batch(scholarships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize a batch of scholarships concurrently
    
    Args:
        scholarships: List of scholarship dictionaries
        
    Returns:
        List of scholarships with AI summaries added
    """
    tasks = [summarizer.summarize_scholarship(scholarship) for scholarship in scholarships]
    return await asyncio.gather(*tasks)

async def summarize_single_scholarship(scholarship: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize a single scholarship
    
    Args:
        scholarship: Scholarship dictionary
        
    Returns:
        Scholarship with AI summary added
    """
    return await summarizer.summarize_scholarship(scholarship) 