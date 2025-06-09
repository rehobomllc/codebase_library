#!/usr/bin/env python3
"""
Robust JSON Parser for Treatment Search Agent Outputs
Handles various output formats and extracts treatment data reliably
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

def extract_treatments_from_output(output: str) -> List[Dict[str, Any]]:
    """
    Extract treatment data from agent output using multiple parsing strategies.
    
    Args:
        output: Raw output from search agent
        
    Returns:
        List of treatment dictionaries
    """
    if not output or not isinstance(output, str):
        logger.warning("Invalid output provided to parser")
        return []
    
    # Strategy 1: Try to parse as pure JSON
    treatments = try_parse_pure_json(output)
    if treatments:
        logger.info(f"Successfully parsed {len(treatments)} treatments using pure JSON")
        return treatments
    
    # Strategy 2: Extract JSON from markdown code blocks
    treatments = try_parse_json_from_markdown(output)
    if treatments:
        logger.info(f"Successfully parsed {len(treatments)} treatments from markdown JSON")
        return treatments
    
    # Strategy 3: Extract structured JSON object
    treatments = try_parse_structured_json(output)
    if treatments:
        logger.info(f"Successfully parsed {len(treatments)} treatments from structured JSON")
        return treatments
    
    # Strategy 4: Parse markdown-formatted treatments
    treatments = try_parse_markdown_treatments(output)
    if treatments:
        logger.info(f"Successfully parsed {len(treatments)} treatments from markdown format")
        return treatments
    
    # Strategy 5: Parse numbered list format
    treatments = try_parse_numbered_list(output)
    if treatments:
        logger.info(f"Successfully parsed {len(treatments)} treatments from numbered list")
        return treatments
    
    logger.warning("Failed to parse any treatments from output")
    return []

def try_parse_pure_json(output: str) -> List[Dict[str, Any]]:
    """Try to parse output as pure JSON."""
    try:
        # Clean up common issues
        cleaned = output.strip()
        
        # Remove any leading/trailing non-JSON content
        if cleaned.startswith('{') and cleaned.endswith('}'):
            data = json.loads(cleaned)
            return extract_candidates_from_json(data)
        
        # Try parsing as array
        if cleaned.startswith('[') and cleaned.endswith(']'):
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
                
    except json.JSONDecodeError:
        pass
    
    return []

def try_parse_json_from_markdown(output: str) -> List[Dict[str, Any]]:
    """Extract JSON from markdown code blocks."""
    # Look for ```json blocks
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, output, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        try:
            data = json.loads(match)
            candidates = extract_candidates_from_json(data)
            if candidates:
                return candidates
        except json.JSONDecodeError:
            continue
    
    # Look for ``` blocks without json specifier
    code_pattern = r'```\s*(\{.*?\})\s*```'
    matches = re.findall(code_pattern, output, re.DOTALL)
    
    for match in matches:
        try:
            data = json.loads(match)
            candidates = extract_candidates_from_json(data)
            if candidates:
                return candidates
        except json.JSONDecodeError:
            continue
    
    return []

def try_parse_structured_json(output: str) -> List[Dict[str, Any]]:
    """Extract JSON object from mixed content."""
    # Look for JSON object with treatment_candidates
    json_pattern = r'\{[^{}]*"treatment_candidates"[^{}]*\[[^\]]*\][^{}]*\}'
    matches = re.findall(json_pattern, output, re.DOTALL)
    
    for match in matches:
        try:
            # Try to fix common JSON issues
            fixed_json = fix_common_json_issues(match)
            data = json.loads(fixed_json)
            candidates = extract_candidates_from_json(data)
            if candidates:
                return candidates
        except json.JSONDecodeError:
            continue
    
    # Look for any JSON object
    json_pattern = r'\{.*?\}'
    matches = re.findall(json_pattern, output, re.DOTALL)
    
    for match in matches:
        try:
            fixed_json = fix_common_json_issues(match)
            data = json.loads(fixed_json)
            candidates = extract_candidates_from_json(data)
            if candidates:
                return candidates
        except json.JSONDecodeError:
            continue
    
    return []

def try_parse_markdown_treatments(output: str) -> List[Dict[str, Any]]:
    """Parse treatments from markdown format."""
    treatments = []
    
    # Pattern for numbered treatments with markdown formatting
    # Matches: 1. **Treatment Name** or **1. Treatment Name**
    treatment_pattern = r'(?:^|\n)(?:\*\*)?(\d+)\.?\s*\*\*([^*]+)\*\*'
    matches = re.findall(treatment_pattern, output, re.MULTILINE)
    
    if not matches:
        # Try alternative pattern for different numbering styles
        treatment_pattern = r'(?:^|\n)(\d+)\.\s*\*\*([^*]+)\*\*'
        matches = re.findall(treatment_pattern, output, re.MULTILINE)
    
    if not matches:
        # Try pattern without numbers: **Treatment Name**
        treatment_pattern = r'(?:^|\n)\*\*([^*]+(?:treatment|therapy|program)[^*]*)\*\*'
        title_matches = re.findall(treatment_pattern, output, re.MULTILINE | re.IGNORECASE)
        matches = [(str(i+1), title) for i, title in enumerate(title_matches)]
    
    for number, title in matches:
        # Extract details for this treatment
        treatment = extract_treatment_details_from_text(output, title, int(number) if number.isdigit() else 1)
        if treatment:
            treatments.append(treatment)
    
    return treatments

def try_parse_numbered_list(output: str) -> List[Dict[str, Any]]:
    """Parse treatments from numbered list format."""
    treatments = []
    
    # Split by numbered items
    sections = re.split(r'\n\s*\d+\.\s*', output)
    
    for i, section in enumerate(sections[1:], 1):  # Skip first empty section
        treatment = parse_treatment_section(section, i)
        if treatment:
            treatments.append(treatment)
    
    return treatments

def extract_candidates_from_json(data: Union[Dict, List]) -> List[Dict[str, Any]]:
    """Extract treatment candidates from parsed JSON data."""
    if isinstance(data, list):
        return data
    
    if isinstance(data, dict):
        # Look for treatment_candidates key
        if 'treatment_candidates' in data:
            candidates = data['treatment_candidates']
            if isinstance(candidates, list):
                return candidates
        
        # Look for treatments key
        if 'treatments' in data:
            treatments = data['treatments']
            if isinstance(treatments, list):
                return treatments
        
        # If data itself looks like a treatment
        if 'title' in data and ('provider' in data or 'organization' in data):
            return [data]
    
    return []

def extract_treatment_details_from_text(text: str, title: str, number: int) -> Optional[Dict[str, Any]]:
    """Extract treatment details from surrounding text."""
    # Find the section for this treatment
    start_pattern = rf'(?:^|\n)(?:\*\*)?{number}\.?\s*\*\*{re.escape(title)}\*\*'
    next_pattern = rf'(?:^|\n)(?:\*\*)?{number + 1}\.?\s*\*\*'
    
    start_match = re.search(start_pattern, text, re.MULTILINE | re.IGNORECASE)
    if not start_match:
        return None
    
    start_pos = start_match.end()
    
    # Find end position (next treatment or end of text)
    next_match = re.search(next_pattern, text[start_pos:], re.MULTILINE)
    if next_match:
        end_pos = start_pos + next_match.start()
        section = text[start_pos:end_pos]
    else:
        section = text[start_pos:]
    
    # Extract details from section
    treatment = {
        'title': title.strip(),
        'provider': extract_field_from_section(section, ['Provider', 'Organization']),
        'url': extract_url_from_section(section),
        'description': extract_field_from_section(section, ['Description', 'Summary']),
        'estimated_deadline': extract_field_from_section(section, ['Deadline', 'Due Date']),
        'estimated_cost': extract_field_from_section(section, ['Cost', 'Price', 'Fee']),
        'basic_eligibility': extract_field_from_section(section, ['Eligibility', 'Requirements']),
        'relevance_score': 'MEDIUM'
    }
    
    # Clean up None values
    treatment = {k: v for k, v in treatment.items() if v is not None}
    
    return treatment if len(treatment) > 1 else None

def parse_treatment_section(section: str, number: int) -> Optional[Dict[str, Any]]:
    """Parse a single treatment section."""
    lines = section.strip().split('\n')
    if not lines:
        return None
    
    # First line is usually the title
    title = lines[0].strip()
    if title.startswith('**') and title.endswith('**'):
        title = title[2:-2]
    
    treatment = {
        'title': title,
        'provider': extract_field_from_section(section, ['Provider', 'Organization']),
        'url': extract_url_from_section(section),
        'description': extract_field_from_section(section, ['Description', 'Summary']),
        'estimated_deadline': extract_field_from_section(section, ['Deadline', 'Due Date']),
        'estimated_cost': extract_field_from_section(section, ['Cost', 'Price', 'Fee']),
        'basic_eligibility': extract_field_from_section(section, ['Eligibility', 'Requirements']),
        'relevance_score': 'MEDIUM'
    }
    
    # Clean up None values
    treatment = {k: v for k, v in treatment.items() if v is not None}
    
    return treatment if len(treatment) > 1 else None

def extract_field_from_section(section: str, field_names: List[str]) -> Optional[str]:
    """Extract a specific field from a text section."""
    for field_name in field_names:
        # Look for "Field: Value" or "**Field**: Value"
        patterns = [
            rf'\*\*{field_name}\*\*:\s*([^\n]+)',
            rf'{field_name}:\s*([^\n]+)',
            rf'- \*\*{field_name}\*\*:\s*([^\n]+)',
            rf'- {field_name}:\s*([^\n]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Clean up markdown formatting
                value = re.sub(r'\*\*([^*]+)\*\*', r'\1', value)
                value = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', value)  # Remove markdown links
                return value if value else None
    
    return None

def extract_url_from_section(section: str) -> Optional[str]:
    """Extract URL from a text section."""
    # Look for markdown links
    markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(markdown_link_pattern, section)
    if matches:
        return matches[0][1]  # Return URL part
    
    # Look for plain URLs
    url_pattern = r'https?://[^\s)]+(?=\s|$|\))'
    matches = re.findall(url_pattern, section)
    if matches:
        return matches[0]
    
    # Look for URL field
    url_field_pattern = r'(?:\*\*)?URL(?:\*\*)?:\s*(?:\[([^\]]+)\]\(([^)]+)\)|([^\s\n]+))'
    match = re.search(url_field_pattern, section, re.IGNORECASE)
    if match:
        return match.group(2) or match.group(3)
    
    return None

def fix_common_json_issues(json_str: str) -> str:
    """Fix common JSON formatting issues."""
    # Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Fix unescaped quotes in strings
    json_str = re.sub(r'(?<!\\)"(?=.*")', r'\\"', json_str)
    
    # Ensure proper string quoting
    json_str = re.sub(r':\s*([^",\[\]{}]+)(?=\s*[,}])', r': "\1"', json_str)
    
    return json_str

def validate_treatment_data(treatment: Dict[str, Any]) -> bool:
    """Validate that treatment data has minimum required fields."""
    required_fields = ['title']
    return all(field in treatment and treatment[field] for field in required_fields)

def clean_treatment_data(treatments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean and validate treatment data."""
    cleaned = []
    
    for treatment in treatments:
        if validate_treatment_data(treatment):
            # Clean up fields
            for key, value in treatment.items():
                if isinstance(value, str):
                    treatment[key] = value.strip()
            
            cleaned.append(treatment)
        else:
            logger.warning(f"Skipping invalid treatment: {treatment}")
    
    return cleaned

# Main function for easy import
def parse_agent_output(output: str) -> List[Dict[str, Any]]:
    """
    Main function to parse agent output and return clean treatment data.
    
    Args:
        output: Raw output from search agent
        
    Returns:
        List of cleaned treatment dictionaries
    """
    treatments = extract_treatments_from_output(output)
    return clean_treatment_data(treatments) 