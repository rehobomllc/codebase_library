# Treatment Navigator Guardrails
# Implements safety, crisis detection, and privacy guardrails for mental health applications

import logging
from typing import Any, List
from pydantic import BaseModel

from agents import (
    Agent, 
    Runner,
    RunContextWrapper,
    TResponseInputItem,
    GuardrailFunctionOutput,
    InputGuardrail,
    OutputGuardrail,
    input_guardrail,
    output_guardrail,
    ModelSettings
)

logger = logging.getLogger(__name__)

# ============================================================================
# GUARDRAIL OUTPUT MODELS
# ============================================================================

class CrisisDetectionOutput(BaseModel):
    """Output model for crisis detection guardrail"""
    is_crisis: bool
    crisis_type: str  # "suicide", "self_harm", "violence", "emergency", "none"
    urgency_level: int  # 1-5 scale, 5 being immediate emergency
    reasoning: str
    recommended_resources: List[str]

class PrivacyCheckOutput(BaseModel):
    """Output model for privacy/PII detection guardrail"""
    contains_pii: bool
    pii_types_found: List[str]  # "ssn", "medical_id", "phone", "email", "address", etc.
    reasoning: str
    sanitized_version: str

class TopicRelevanceOutput(BaseModel):
    """Output model for topic relevance guardrail"""
    is_relevant: bool
    topic_category: str  # "treatment", "mental_health", "substance_use", "off_topic"
    reasoning: str

# ============================================================================
# GUARDRAIL AGENTS
# ============================================================================

# Crisis Detection Agent - Uses a smaller, faster model for quick screening
crisis_detection_agent = Agent(
    name="Crisis Detection Guardrail",
    instructions="""You are a specialized crisis detection system for mental health applications.

CRITICAL MISSION: Detect if user input indicates ANY mental health or substance use crisis requiring immediate intervention.

CRISIS INDICATORS TO DETECT:
🚨 IMMEDIATE EMERGENCY (Level 5):
- Suicide plans, methods, or imminent intent
- Active self-harm or threats to harm others
- Overdose or medical emergency
- Psychotic episode with danger

🔴 URGENT CRISIS (Level 4):
- Suicidal ideation with means/plan
- Recent self-harm or substance overdose
- Severe mental health deterioration
- Domestic violence or abuse situations

⚠️ MODERATE CONCERN (Level 3):
- Suicidal thoughts without immediate plan
- Substance use escalation
- Severe depression or anxiety symptoms
- Risk factors accumulating

KEYWORDS/PHRASES TO WATCH FOR:
- "kill myself", "end my life", "suicide", "overdose"
- "hurt myself", "self-harm", "cutting"  
- "can't go on", "want to die", "no point"
- "emergency", "crisis", "help me"
- "drinking too much", "using more", "can't stop"

RESPONSE REQUIREMENTS:
- Be extremely sensitive to context and subtext
- Even subtle crisis indicators should trigger alerts
- Better to over-detect than miss a crisis
- Provide specific crisis resources in recommended_resources

RECOMMENDED RESOURCES FOR CRISIS:
- "National Suicide Prevention Lifeline: 988"
- "Crisis Text Line: Text HOME to 741741"
- "Emergency Services: 911"
- "SAMHSA National Helpline: 1-800-662-4357"
- "National Domestic Violence Hotline: 1-800-799-7233"

Always err on the side of safety - if uncertain, mark as crisis and recommend professional help.""",
    output_type=CrisisDetectionOutput,
    model="gpt-4o-mini",  # Fast model for quick crisis screening
    model_settings=ModelSettings(temperature=0.1)  # Low temperature for consistent detection
)

# Privacy Protection Agent
privacy_protection_agent = Agent(
    name="Privacy Protection Guardrail", 
    instructions="""You are a privacy protection system that detects and sanitizes PII in mental health communications.

DETECT THESE PII TYPES:
- Social Security Numbers (SSN)
- Medical/Insurance ID numbers
- Phone numbers
- Email addresses
- Physical addresses
- Full names (first and last together)
- Dates of birth
- Medical record numbers
- Prescription details with specific dosages

SANITIZATION RULES:
- Replace SSNs with "***-**-****"
- Replace phone numbers with "***-***-****" 
- Replace emails with "***@***.com"
- Replace addresses with "*** [City], [State]"
- Keep first names, mask last names as "***"
- Replace specific medical details with general terms

BE CAREFUL NOT TO OVER-SANITIZE:
- Keep treatment types (e.g., "therapy", "counseling")
- Keep general locations (city names are OK)
- Keep general timeframes ("last month", "recently")
- Keep symptoms and conditions (for treatment matching)

Return sanitized version that maintains therapeutic context while protecting privacy.""",
    output_type=PrivacyCheckOutput,
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0.2)
)

# Topic Relevance Agent
topic_relevance_agent = Agent(
    name="Topic Relevance Guardrail",
    instructions="""You determine if user input is relevant to mental health and substance use treatment navigation.

RELEVANT TOPICS:
✅ Mental Health Treatment:
- Therapy, counseling, psychiatric services
- Depression, anxiety, PTSD, bipolar, etc.
- Mental health medications, psychiatrists
- Inpatient/outpatient mental health care

✅ Substance Use Treatment:
- Addiction treatment, detox, rehab
- Alcoholism, drug addiction recovery
- MAT (Medication-Assisted Treatment)
- Support groups, sobriety programs

✅ Treatment Navigation:
- Finding treatment facilities
- Insurance coverage questions
- Appointment scheduling
- Treatment planning and preparation

❌ OFF-TOPIC (mark as irrelevant):
- General medical questions unrelated to mental health
- Academic homework or research projects
- General life advice not related to treatment
- Technical support for non-health applications
- Commercial/sales inquiries

EDGE CASES (mark as relevant):
- Crisis situations (always relevant)
- Family/relationship issues affecting mental health
- Work/school stress requiring treatment
- Trauma and recovery-related topics

Be liberal in marking things as relevant if they could reasonably relate to mental health treatment.""",
    output_type=TopicRelevanceOutput,
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0.2)
)

# ============================================================================
# GUARDRAIL FUNCTIONS
# ============================================================================

@input_guardrail
async def crisis_detection_guardrail(
    ctx: RunContextWrapper[Any], 
    agent: Agent, 
    input: str | List[TResponseInputItem]
) -> GuardrailFunctionOutput:
    """
    Critical guardrail that detects mental health/substance use crises.
    Triggers immediate escalation for any crisis indicators.
    """
    try:
        # Convert input to string for analysis
        if isinstance(input, list):
            input_text = " ".join([
                item.get("content", "") if isinstance(item, dict) else str(item) 
                for item in input
            ])
        else:
            input_text = str(input)

        result = await Runner.run(
            crisis_detection_agent, 
            input_text, 
            context=ctx.context
        )
        
        crisis_output = result.final_output
        
        # Log crisis detection for monitoring
        if crisis_output.is_crisis:
            logger.critical(
                f"CRISIS DETECTED - Level {crisis_output.urgency_level}: {crisis_output.crisis_type}"
                f" | Reasoning: {crisis_output.reasoning}"
            )
        
        return GuardrailFunctionOutput(
            output_info={
                "crisis_detected": crisis_output.is_crisis,
                "crisis_type": crisis_output.crisis_type,
                "urgency_level": crisis_output.urgency_level,
                "recommended_resources": crisis_output.recommended_resources,
                "reasoning": crisis_output.reasoning
            },
            tripwire_triggered=crisis_output.urgency_level >= 4  # Trigger on urgent/emergency
        )
        
    except Exception as e:
        logger.error(f"Crisis detection guardrail failed: {e}")
        # On failure, err on side of caution - assume potential crisis
        return GuardrailFunctionOutput(
            output_info={"error": str(e), "assumed_crisis": True},
            tripwire_triggered=True
        )

@input_guardrail 
async def privacy_protection_guardrail(
    ctx: RunContextWrapper[Any],
    agent: Agent,
    input: str | List[TResponseInputItem]  
) -> GuardrailFunctionOutput:
    """
    Detects and flags PII in user input for privacy protection.
    Provides sanitized version while preserving therapeutic context.
    """
    try:
        # Convert input to string for analysis
        if isinstance(input, list):
            input_text = " ".join([
                item.get("content", "") if isinstance(item, dict) else str(item)
                for item in input
            ])
        else:
            input_text = str(input)

        result = await Runner.run(
            privacy_protection_agent,
            input_text,
            context=ctx.context
        )
        
        privacy_output = result.final_output
        
        # Log PII detection for compliance monitoring
        if privacy_output.contains_pii:
            logger.warning(
                f"PII DETECTED: {privacy_output.pii_types_found} | "
                f"Reasoning: {privacy_output.reasoning}"
            )
        
        return GuardrailFunctionOutput(
            output_info={
                "pii_detected": privacy_output.contains_pii,
                "pii_types": privacy_output.pii_types_found,
                "sanitized_version": privacy_output.sanitized_version,
                "reasoning": privacy_output.reasoning
            },
            tripwire_triggered=False  # PII detection doesn't stop processing, just logs
        )
        
    except Exception as e:
        logger.error(f"Privacy protection guardrail failed: {e}")
        return GuardrailFunctionOutput(
            output_info={"error": str(e)},
            tripwire_triggered=False
        )

@input_guardrail
async def topic_relevance_guardrail(
    ctx: RunContextWrapper[Any],
    agent: Agent, 
    input: str | List[TResponseInputItem]
) -> GuardrailFunctionOutput:
    """
    Ensures user input is relevant to mental health/substance use treatment.
    Helps prevent misuse of treatment navigation resources.
    """
    try:
        # Convert input to string for analysis  
        if isinstance(input, list):
            input_text = " ".join([
                item.get("content", "") if isinstance(item, dict) else str(item)
                for item in input
            ])
        else:
            input_text = str(input)

        result = await Runner.run(
            topic_relevance_agent,
            input_text,
            context=ctx.context
        )
        
        relevance_output = result.final_output
        
        # Log off-topic requests for monitoring
        if not relevance_output.is_relevant:
            logger.info(
                f"OFF-TOPIC REQUEST: Category: {relevance_output.topic_category} | "
                f"Reasoning: {relevance_output.reasoning}"
            )
        
        return GuardrailFunctionOutput(
            output_info={
                "is_relevant": relevance_output.is_relevant,
                "topic_category": relevance_output.topic_category,
                "reasoning": relevance_output.reasoning
            },
            tripwire_triggered=not relevance_output.is_relevant  # Stop processing off-topic requests
        )
        
    except Exception as e:
        logger.error(f"Topic relevance guardrail failed: {e}")
        # On failure, assume relevant to avoid blocking legitimate requests
        return GuardrailFunctionOutput(
            output_info={"error": str(e), "assumed_relevant": True},
            tripwire_triggered=False
        )

# ============================================================================
# OUTPUT GUARDRAILS
# ============================================================================

@output_guardrail
async def response_safety_guardrail(
    ctx: RunContextWrapper[Any],
    agent: Agent,
    output: Any
) -> GuardrailFunctionOutput:
    """
    Ensures agent output is safe and appropriate for mental health context.
    Checks for medical advice, inappropriate responses, or harmful content.
    """
    try:
        # Extract text from output
        if hasattr(output, 'response'):
            output_text = output.response
        elif hasattr(output, 'content'):
            output_text = output.content
        else:
            output_text = str(output)

        # Simple safety checks (could be enhanced with another agent)
        safety_issues = []
        
        # Check for medical advice red flags
        medical_advice_keywords = [
            "diagnose", "prescribe", "medication dosage", "medical advice",
            "stop taking", "increase dose", "decrease dose"
        ]
        
        if any(keyword in output_text.lower() for keyword in medical_advice_keywords):
            safety_issues.append("potential_medical_advice")
        
        # Check for crisis response adequacy
        if "crisis" in output_text.lower() or "emergency" in output_text.lower():
            if "988" not in output_text and "911" not in output_text:
                safety_issues.append("inadequate_crisis_response")
        
        return GuardrailFunctionOutput(
            output_info={
                "safety_issues": safety_issues,
                "output_text_length": len(output_text)
            },
            tripwire_triggered=len(safety_issues) > 0
        )
        
    except Exception as e:
        logger.error(f"Response safety guardrail failed: {e}")
        return GuardrailFunctionOutput(
            output_info={"error": str(e)},
            tripwire_triggered=False
        )

# ============================================================================
# GUARDRAIL COLLECTIONS FOR EASY APPLICATION
# ============================================================================

# Standard input guardrails for treatment navigator
TREATMENT_INPUT_GUARDRAILS = [
    InputGuardrail(guardrail_function=crisis_detection_guardrail, name="crisis_detection"),
    InputGuardrail(guardrail_function=privacy_protection_guardrail, name="privacy_protection"),
    InputGuardrail(guardrail_function=topic_relevance_guardrail, name="topic_relevance")
]

# Standard output guardrails for treatment navigator  
TREATMENT_OUTPUT_GUARDRAILS = [
    OutputGuardrail(guardrail_function=response_safety_guardrail, name="response_safety")
]

# Crisis-focused guardrails (for crisis-sensitive agents)
CRISIS_FOCUSED_GUARDRAILS = [
    InputGuardrail(guardrail_function=crisis_detection_guardrail, name="crisis_detection"),
    InputGuardrail(guardrail_function=privacy_protection_guardrail, name="privacy_protection")
] 