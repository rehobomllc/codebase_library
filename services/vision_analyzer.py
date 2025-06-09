#!/usr/bin/env python3
"""
AI-powered vision analysis service using OpenAI's Responses API with gpt-4o

This module provides functions to:
1. Analyze medical documents and extract key information
2. Read prescription labels and extract medication details
3. Process treatment forms and extract patient information
4. Analyze insurance cards and extract coverage details
5. Handle image uploads and provide structured JSON responses

@file purpose: Provides vision analysis capabilities for treatment-related documents
"""

import asyncio
import hashlib
import json
import os
import base64
import mimetypes
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TreatmentVisionAnalyzer:
    """
    Vision analyzer for treatment-related documents using OpenAI's Responses API
    """
    
    def __init__(self):
        """Initialize the vision analyzer with OpenAI configuration"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for vision analysis")
            
        self.base_url = "https://api.openai.com/v1"
        self.model = os.getenv('VISION_MODEL', 'gpt-4o')
        self.max_output_tokens = int(os.getenv('VISION_MAX_OUTPUT_TOKENS', '1000'))
        self.cache = {}  # Simple in-memory cache for repeated analyses
        
        # Initialize HTTP client with proper headers
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=60.0
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    def _generate_cache_key(self, image_data: bytes, analysis_type: str) -> str:
        """Generate a cache key from image data and analysis type"""
        content_hash = hashlib.md5(image_data + analysis_type.encode()).hexdigest()
        return f"vision_{analysis_type}_{content_hash}"
    
    def _encode_image_to_base64(self, image_data: bytes, mime_type: str) -> str:
        """Encode image data to base64 data URL"""
        base64_data = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{base64_data}"
    
    async def analyze_medical_document(
        self, 
        image_data: bytes, 
        mime_type: str,
        document_type: str = "medical_report",
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze medical documents like test results, doctor notes, or medical reports
        
        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            document_type: Type of document (medical_report, lab_results, doctor_notes, etc.)
            additional_context: Additional context for analysis
            
        Returns:
            Dictionary with extracted medical information
        """
        cache_key = self._generate_cache_key(image_data, f"medical_{document_type}")
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        image_url = self._encode_image_to_base64(image_data, mime_type)
        
        system_prompt = """You are a medical document analysis expert. Extract key information from medical documents accurately and format as structured JSON. Focus on patient safety and accuracy."""
        
        context_text = f" Additional context: {additional_context}" if additional_context else ""
        
        user_prompt = f"""
        Analyze this {document_type.replace('_', ' ')} and extract the following information:{context_text}

        Please provide a structured JSON response with these fields:
        {{
            "document_type": "type of medical document",
            "patient_name": "patient name if visible",
            "date_of_service": "date when service was provided",
            "healthcare_provider": "name of doctor/clinic/hospital",
            "primary_findings": ["list of main findings or diagnoses"],
            "medications_mentioned": ["any medications listed"],
            "test_results": ["any test results with values"],
            "recommendations": ["treatment recommendations or next steps"],
            "important_dates": ["any important dates mentioned"],
            "contact_information": ["phone numbers, addresses if visible"],
            "insurance_information": "any insurance details mentioned",
            "confidence_score": 0.95,
            "requires_human_review": false,
            "notes": "any additional relevant information"
        }}

        If any field is not clearly visible or applicable, use null. For confidence_score, rate how confident you are in the extraction (0.0-1.0). Set requires_human_review to true if the document contains critical information that should be verified by a human.
        """
        
        try:
            result = await self._make_responses_api_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url
            )
            
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            return self._generate_error_response(f"Error analyzing medical document: {str(e)}")
    
    async def analyze_prescription_label(
        self, 
        image_data: bytes, 
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Analyze prescription labels to extract medication information
        
        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            
        Returns:
            Dictionary with extracted prescription information
        """
        cache_key = self._generate_cache_key(image_data, "prescription")
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        image_url = self._encode_image_to_base64(image_data, mime_type)
        
        system_prompt = """You are a pharmacy expert specialized in reading prescription labels. Extract medication information accurately for patient safety. Always double-check dosage and medication names."""
        
        user_prompt = """
        Analyze this prescription label and extract the medication information:

        Please provide a structured JSON response with these fields:
        {
            "medication_name": "exact medication name including brand/generic",
            "dosage_strength": "strength/concentration (e.g., 10mg, 250ml)",
            "dosage_instructions": "how to take the medication",
            "quantity_prescribed": "total quantity in the bottle/package",
            "refills_remaining": "number of refills left",
            "prescribing_doctor": "name of prescribing physician",
            "pharmacy_name": "name of the dispensing pharmacy",
            "pharmacy_phone": "pharmacy contact number",
            "prescription_date": "date prescription was filled",
            "expiration_date": "medication expiration date",
            "patient_name": "patient name on label",
            "rx_number": "prescription reference number",
            "ndc_number": "NDC number if visible",
            "warnings": ["any warning labels or special instructions"],
            "confidence_score": 0.95,
            "requires_verification": false,
            "notes": "any additional important information"
        }

        If any field is not clearly visible, use null. Set requires_verification to true if any critical medication information is unclear or if this appears to be a controlled substance. Be extremely careful with medication names and dosages.
        """
        
        try:
            result = await self._make_responses_api_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url
            )
            
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            return self._generate_error_response(f"Error analyzing prescription label: {str(e)}")
    
    async def analyze_insurance_card(
        self, 
        image_data: bytes, 
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Analyze insurance cards to extract coverage information
        
        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            
        Returns:
            Dictionary with extracted insurance information
        """
        cache_key = self._generate_cache_key(image_data, "insurance_card")
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        image_url = self._encode_image_to_base64(image_data, mime_type)
        
        system_prompt = """You are an insurance verification specialist. Extract insurance information accurately to help with treatment coverage verification."""
        
        user_prompt = """
        Analyze this insurance card and extract the coverage information:

        Please provide a structured JSON response with these fields:
        {
            "insurance_company": "name of insurance provider",
            "plan_name": "specific plan or product name",
            "member_name": "name of the insured member",
            "member_id": "member/subscriber ID number",
            "group_number": "group or employer number",
            "plan_type": "type of plan (HMO, PPO, EPO, etc.)",
            "effective_date": "when coverage started",
            "copay_amounts": {
                "primary_care": "PCP copay amount",
                "specialist": "specialist copay amount",
                "emergency_room": "ER copay amount"
            },
            "deductible_info": "deductible amounts if visible",
            "customer_service_phone": "insurance company phone number",
            "provider_phone": "provider services phone",
            "website": "insurance company website",
            "rx_coverage": "prescription coverage details",
            "network_info": "in-network provider information",
            "confidence_score": 0.95,
            "card_front_or_back": "front or back of card",
            "notes": "any additional coverage details"
        }

        If any field is not clearly visible, use null. Look carefully for all phone numbers, copay amounts, and coverage details that might be useful for treatment verification.
        """
        
        try:
            result = await self._make_responses_api_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url
            )
            
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            return self._generate_error_response(f"Error analyzing insurance card: {str(e)}")
    
    async def analyze_treatment_form(
        self, 
        image_data: bytes, 
        mime_type: str,
        form_type: str = "intake_form"
    ) -> Dict[str, Any]:
        """
        Analyze treatment forms to extract patient information
        
        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            form_type: Type of form (intake_form, consent_form, etc.)
            
        Returns:
            Dictionary with extracted form information
        """
        cache_key = self._generate_cache_key(image_data, f"form_{form_type}")
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        image_url = self._encode_image_to_base64(image_data, mime_type)
        
        system_prompt = """You are a medical forms processing expert. Extract information from treatment forms accurately while respecting patient privacy and healthcare regulations."""
        
        user_prompt = f"""
        Analyze this {form_type.replace('_', ' ')} and extract the relevant information:

        Please provide a structured JSON response with these fields:
        {{
            "form_type": "type of form being analyzed",
            "patient_demographics": {{
                "name": "patient full name",
                "date_of_birth": "DOB",
                "address": "patient address",
                "phone": "contact number",
                "email": "email address",
                "emergency_contact": "emergency contact info"
            }},
            "medical_history": ["any medical history mentioned"],
            "current_medications": ["medications currently taking"],
            "allergies": ["known allergies"],
            "symptoms": ["current symptoms or complaints"],
            "insurance_info": "insurance information if present",
            "treatment_requested": "type of treatment being sought",
            "physician_information": "referring or treating physician",
            "appointment_preferences": "any scheduling preferences",
            "completed_sections": ["which sections appear filled out"],
            "missing_information": ["what information still needs to be completed"],
            "signatures_present": "whether form appears signed",
            "confidence_score": 0.95,
            "requires_completion": false,
            "notes": "additional relevant details"
        }}

        If any field is not visible or applicable, use null. Set requires_completion to true if the form appears incomplete or needs additional information.
        """
        
        try:
            result = await self._make_responses_api_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url
            )
            
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            return self._generate_error_response(f"Error analyzing treatment form: {str(e)}")
    
    async def _make_responses_api_call(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        image_url: str
    ) -> Dict[str, Any]:
        """
        Make a call to OpenAI's Responses API with image input
        
        Args:
            system_prompt: System message for the AI
            user_prompt: User message with analysis instructions
            image_url: Base64 encoded image data URL
            
        Returns:
            Parsed JSON response from the AI
        """
        request_payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image_url": image_url}
                    ]
                }
            ],
            "instructions": system_prompt,
            "max_output_tokens": self.max_output_tokens,
            "temperature": 0.1,  # Low temperature for consistent, accurate extractions
            "text": {
                "format": {
                    "type": "json_object"
                }
            }
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/responses",
                json=request_payload
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Extract the text content from the response
            if (response_data.get("output") and 
                len(response_data["output"]) > 0 and 
                response_data["output"][0].get("content") and
                len(response_data["output"][0]["content"]) > 0):
                
                content_text = response_data["output"][0]["content"][0].get("text", "")
                
                # Parse JSON response
                try:
                    parsed_result = json.loads(content_text)
                    # Add metadata from the API response
                    parsed_result["_metadata"] = {
                        "response_id": response_data.get("id"),
                        "model_used": response_data.get("model"),
                        "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
                        "analyzed_at": datetime.utcnow().isoformat(),
                    }
                    return parsed_result
                except json.JSONDecodeError as e:
                    return self._generate_error_response(f"Failed to parse AI response as JSON: {str(e)}")
            else:
                return self._generate_error_response("No content in AI response")
                
        except httpx.HTTPStatusError as e:
            error_detail = f"HTTP {e.response.status_code}: {e.response.text}"
            return self._generate_error_response(f"API request failed: {error_detail}")
        except Exception as e:
            return self._generate_error_response(f"Unexpected error in API call: {str(e)}")
    
    def _generate_error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate a standardized error response"""
        return {
            "error": True,
            "error_message": error_message,
            "confidence_score": 0.0,
            "analyzed_at": datetime.utcnow().isoformat(),
            "requires_human_review": True
        }

# Global analyzer instance
vision_analyzer = TreatmentVisionAnalyzer()

async def analyze_medical_document_file(
    image_data: bytes, 
    mime_type: str,
    document_type: str = "medical_report",
    additional_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze a medical document image file
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        document_type: Type of document
        additional_context: Additional context for analysis
        
    Returns:
        Analysis results dictionary
    """
    return await vision_analyzer.analyze_medical_document(
        image_data, mime_type, document_type, additional_context
    )

async def analyze_prescription_label_file(
    image_data: bytes, 
    mime_type: str
) -> Dict[str, Any]:
    """
    Analyze a prescription label image file
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        
    Returns:
        Analysis results dictionary
    """
    return await vision_analyzer.analyze_prescription_label(image_data, mime_type)

async def analyze_insurance_card_file(
    image_data: bytes, 
    mime_type: str
) -> Dict[str, Any]:
    """
    Analyze an insurance card image file
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        
    Returns:
        Analysis results dictionary
    """
    return await vision_analyzer.analyze_insurance_card(image_data, mime_type)

async def analyze_treatment_form_file(
    image_data: bytes, 
    mime_type: str,
    form_type: str = "intake_form"
) -> Dict[str, Any]:
    """
    Analyze a treatment form image file
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        form_type: Type of form
        
    Returns:
        Analysis results dictionary
    """
    return await vision_analyzer.analyze_treatment_form(image_data, mime_type, form_type)

async def close_vision_analyzer():
    """Close the vision analyzer HTTP client"""
    await vision_analyzer.close() 