#!/usr/bin/env python3
"""
Treatment Confidence Scorer

Analyzes how well a treatment option matches a patient's profile and needs.
Provides confidence scores and recommendations for treatment decisions.

@file purpose: Treatment matching and confidence scoring for healthcare decisions
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import re

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Constants for Treatment Scoring ---
# Weights for different factors (normalized to sum to 1.0)
TREATMENT_WEIGHTS = {
    "condition_match": 0.25,        # How well treatment addresses patient's condition
    "age_eligibility": 0.15,        # Age requirements and suitability
    "location_accessibility": 0.15, # Geographic accessibility and distance
    "insurance_coverage": 0.20,     # Insurance compatibility and coverage
    "treatment_type_match": 0.10,   # Type of treatment vs patient preferences
    "provider_quality": 0.05,       # Provider ratings and credentials
    "cost_affordability": 0.10,     # Treatment costs vs patient's budget
}

# Treatment-specific parameters
PREFERRED_DISTANCE_MILES = 50    # Ideal distance for treatment
MAX_REASONABLE_DISTANCE_MILES = 200  # Maximum reasonable travel distance
AGE_TOLERANCE_YEARS = 2          # Flexibility for age requirements
COST_CONCERN_THRESHOLD = 5000    # Dollar amount that raises affordability concerns

# Treatment urgency levels
URGENCY_LEVELS = {
    "emergency": {"priority": 1, "wait_time_days": 0},
    "urgent": {"priority": 2, "wait_time_days": 7},
    "routine": {"priority": 3, "wait_time_days": 30},
    "elective": {"priority": 4, "wait_time_days": 90}
}

# --- Dataclasses for Treatment Inputs and Outputs ---

@dataclass
class PatientProfileInput:
    """Patient profile information for treatment matching"""
    user_id: str
    age: Optional[int] = None
    primary_condition: Optional[str] = None
    secondary_conditions: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    insurance_provider: Optional[str] = None
    insurance_plan_type: Optional[str] = None  # HMO, PPO, EPO, etc.
    location_zip: Optional[str] = None
    location_state: Optional[str] = None
    max_travel_distance: Optional[int] = 100  # miles
    budget_max: Optional[float] = None
    treatment_urgency: str = "routine"  # emergency, urgent, routine, elective
    preferred_treatment_types: List[str] = field(default_factory=list)
    mobility_limitations: List[str] = field(default_factory=list)
    language_preferences: List[str] = field(default_factory=list)

@dataclass
class TreatmentDataInput:
    """Treatment option information for matching"""
    treatment_id: str
    name: str
    provider_name: str
    treatment_types: List[str] = field(default_factory=list)
    conditions_treated: List[str] = field(default_factory=list)
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    location_address: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_zip: Optional[str] = None
    distance_miles: Optional[float] = None
    accepted_insurance: List[str] = field(default_factory=list)
    estimated_cost: Optional[str] = None  # "$500 - $2000" or "Covered by insurance"
    wait_time_days: Optional[int] = None
    provider_rating: Optional[float] = None  # 1.0 - 5.0
    specialty_certifications: List[str] = field(default_factory=list)
    languages_spoken: List[str] = field(default_factory=list)
    accessibility_features: List[str] = field(default_factory=list)
    description: Optional[str] = ""
    website_url: Optional[str] = None
    phone_number: Optional[str] = None

@dataclass
class FactorScore:
    """Individual scoring factor with reasoning"""
    factor_name: str
    score: float  # 0.0 to 1.0
    reason: str
    weight: float
    is_concern: bool = False
    is_positive_match: bool = False
    confidence_level: str = "medium"  # low, medium, high

@dataclass
class MatchDetails:
    """Detailed matching analysis"""
    overall_score: float = 0.0
    factor_scores: List[FactorScore] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)
    strong_matches: List[str] = field(default_factory=list)

@dataclass
class TreatmentConfidenceResult:
    """Comprehensive treatment confidence analysis result"""
    user_id: str
    treatment_id: str
    treatment_name: str
    provider_name: str
    confidence_score: float  # 0-100
    match_level: str  # "excellent", "good", "fair", "poor"
    summary_explanation: str
    key_strengths: List[str]
    potential_concerns: List[str]
    recommended_actions: List[str]
    urgency_assessment: str
    raw_match_details: MatchDetails

class TreatmentConfidenceScorer:
    """
    Analyzes treatment options against patient profiles to generate confidence scores
    """
    
    def __init__(self, patient_profile: PatientProfileInput, treatment_data: TreatmentDataInput):
        self.patient_profile = patient_profile
        self.treatment_data = treatment_data
        self.match_details = MatchDetails()
        self.raw_factor_values = {}

        if not patient_profile or not treatment_data:
            raise ValueError("Patient profile and treatment data must be provided.")
        
        logger.info(f"Treatment scorer initialized for patient {patient_profile.user_id} and treatment {treatment_data.treatment_id}")

    def _add_factor_score(self, name: str, score: float, reason: str, 
                         is_concern: bool = False, is_positive: bool = False,
                         confidence_level: str = "medium"):
        """Add a factor score to the analysis"""
        weight = TREATMENT_WEIGHTS.get(name, 0.0)
        self.match_details.factor_scores.append(
            FactorScore(
                factor_name=name, 
                score=score, 
                reason=reason, 
                weight=weight,
                is_concern=is_concern, 
                is_positive_match=is_positive,
                confidence_level=confidence_level
            )
        )
        self.raw_factor_values[name] = score

    def _text_list_match_score(self, patient_items: List[str], treatment_items: List[str]) -> Tuple[float, List[str]]:
        """Calculate match score between two lists of text items"""
        if not treatment_items:  # Treatment is open to all
            return 0.7, []
        if not patient_items:  # Patient has not specified
            return 0.3, []

        patient_set = {item.lower().strip() for item in patient_items if item}
        treatment_set = {item.lower().strip() for item in treatment_items if item}
        
        # Exact matches
        intersection = patient_set.intersection(treatment_set)
        if intersection:
            return 1.0, list(intersection)
        
        # Partial matches (substring matching)
        partial_matches = []
        for p_item in patient_set:
            for t_item in treatment_set:
                if p_item in t_item or t_item in p_item:
                    partial_matches.append(f"'{p_item}' ~ '{t_item}'")
                    return 0.65, partial_matches
        
        return 0.1, []  # No match found

    def _score_condition_match(self):
        """Score how well the treatment addresses the patient's conditions"""
        patient_conditions = [self.patient_profile.primary_condition] if self.patient_profile.primary_condition else []
        patient_conditions.extend(self.patient_profile.secondary_conditions)
        
        score, matches = self._text_list_match_score(patient_conditions, self.treatment_data.conditions_treated)
        
        is_positive = score >= 0.7
        is_concern = score < 0.5 and bool(self.treatment_data.conditions_treated)
        confidence_level = "high" if score >= 0.9 else "medium" if score >= 0.6 else "low"
        
        if matches:
            reason = f"Condition match: Treatment addresses your conditions ({', '.join(matches[:3])})."
        elif self.treatment_data.conditions_treated and patient_conditions:
            reason = f"Limited condition match: Treatment may not directly address your specific conditions."
        elif not self.treatment_data.conditions_treated:
            reason = "Condition match: Treatment scope not specified - may be general care."
        else:
            reason = "Condition match: Your medical conditions not specified in profile."
            is_concern = True

        self._add_factor_score("condition_match", score, reason, is_concern, is_positive, confidence_level)

    def _score_age_eligibility(self):
        """Score age eligibility and appropriateness"""
        patient_age = self.patient_profile.age
        min_age = self.treatment_data.min_age
        max_age = self.treatment_data.max_age
        
        score = 0.5  # Neutral if no age info
        reason = "Age eligibility: No age restrictions specified."
        is_positive = False
        is_concern = False
        confidence_level = "medium"

        if patient_age is not None:
            if min_age is not None and max_age is not None:
                if min_age <= patient_age <= max_age:
                    score = 1.0
                    reason = f"Age eligibility: Perfect match (age {patient_age}, range {min_age}-{max_age})."
                    is_positive = True
                    confidence_level = "high"
                elif patient_age < min_age:
                    if min_age - patient_age <= AGE_TOLERANCE_YEARS:
                        score = 0.6
                        reason = f"Age consideration: Slightly below minimum age ({patient_age} vs {min_age}), but may still be eligible."
                    else:
                        score = 0.1
                        reason = f"Age restriction: Below minimum age requirement ({patient_age} vs {min_age})."
                        is_concern = True
                        confidence_level = "low"
                elif patient_age > max_age:
                    if patient_age - max_age <= AGE_TOLERANCE_YEARS:
                        score = 0.6
                        reason = f"Age consideration: Slightly above maximum age ({patient_age} vs {max_age}), but may still be eligible."
                    else:
                        score = 0.1
                        reason = f"Age restriction: Above maximum age requirement ({patient_age} vs {max_age})."
                        is_concern = True
                        confidence_level = "low"
            elif min_age is not None:
                if patient_age >= min_age:
                    score = 0.9
                    reason = f"Age eligibility: Meets minimum age requirement ({patient_age} >= {min_age})."
                    is_positive = True
                else:
                    score = 0.2
                    reason = f"Age restriction: Below minimum age ({patient_age} vs {min_age})."
                    is_concern = True
                    confidence_level = "low"
            elif max_age is not None:
                if patient_age <= max_age:
                    score = 0.9
                    reason = f"Age eligibility: Within maximum age limit ({patient_age} <= {max_age})."
                    is_positive = True
                else:
                    score = 0.2
                    reason = f"Age restriction: Above maximum age ({patient_age} vs {max_age})."
                    is_concern = True
                    confidence_level = "low"
            else:
                score = 0.8
                reason = f"Age eligibility: No age restrictions (patient age {patient_age})."
                is_positive = True
        else:
            if min_age is not None or max_age is not None:
                score = 0.3
                reason = "Age eligibility: Treatment has age requirements, but your age is not in profile."
                is_concern = True
                confidence_level = "low"

        self._add_factor_score("age_eligibility", score, reason, is_concern, is_positive, confidence_level)

    def _score_location_accessibility(self):
        """Score location and accessibility factors"""
        distance = self.treatment_data.distance_miles
        max_travel = self.patient_profile.max_travel_distance or PREFERRED_DISTANCE_MILES
        
        score = 0.5  # Neutral if no location info
        reason = "Location: Distance information not available."
        is_positive = False
        is_concern = False
        confidence_level = "medium"

        if distance is not None:
            if distance <= PREFERRED_DISTANCE_MILES:
                score = 1.0
                reason = f"Location: Excellent - within {distance:.1f} miles (preferred range)."
                is_positive = True
                confidence_level = "high"
            elif distance <= max_travel:
                score = 0.7
                reason = f"Location: Good - {distance:.1f} miles (within your travel preference of {max_travel} miles)."
                is_positive = True
            elif distance <= MAX_REASONABLE_DISTANCE_MILES:
                score = 0.4
                reason = f"Location: Manageable - {distance:.1f} miles (requires significant travel)."
                is_concern = True
            else:
                score = 0.1
                reason = f"Location: Very distant - {distance:.1f} miles (may be impractical)."
                is_concern = True
                confidence_level = "low"

        # Check accessibility features if patient has mobility limitations
        if self.patient_profile.mobility_limitations and self.treatment_data.accessibility_features:
            accessibility_match = len(set(self.patient_profile.mobility_limitations) & 
                                   set(self.treatment_data.accessibility_features))
            if accessibility_match > 0:
                score = min(1.0, score + 0.1)  # Bonus for accessibility
                reason += f" Accessibility features available for your needs."
                is_positive = True

        self._add_factor_score("location_accessibility", score, reason, is_concern, is_positive, confidence_level)

    def _score_insurance_coverage(self):
        """Score insurance compatibility and coverage"""
        patient_insurance = self.patient_profile.insurance_provider
        accepted_insurance = self.treatment_data.accepted_insurance
        
        score = 0.5  # Neutral baseline
        reason = "Insurance: Coverage information not available."
        is_positive = False
        is_concern = False
        confidence_level = "medium"

        if patient_insurance and accepted_insurance:
            # Check for exact matches
            if patient_insurance.lower() in [ins.lower() for ins in accepted_insurance]:
                score = 1.0
                reason = f"Insurance: Excellent - your insurance ({patient_insurance}) is accepted."
                is_positive = True
                confidence_level = "high"
            else:
                # Check for partial matches (e.g., "Blue Cross" in "Blue Cross Blue Shield")
                partial_match = any(patient_insurance.lower() in ins.lower() or 
                                  ins.lower() in patient_insurance.lower() 
                                  for ins in accepted_insurance)
                if partial_match:
                    score = 0.7
                    reason = f"Insurance: Likely covered - similar plan to accepted insurance."
                    is_positive = True
                else:
                    score = 0.2
                    reason = f"Insurance: May not be covered - your insurance ({patient_insurance}) not listed in accepted plans."
                    is_concern = True
                    confidence_level = "low"
        elif not patient_insurance and accepted_insurance:
            score = 0.3
            reason = "Insurance: Treatment accepts specific insurance, but your plan is not specified."
            is_concern = True
        elif patient_insurance and not accepted_insurance:
            score = 0.6
            reason = "Insurance: Treatment's accepted insurance not specified - contact provider to verify."
        elif "medicare" in self.treatment_data.description.lower() if self.treatment_data.description else False:
            score = 0.8
            reason = "Insurance: Appears to accept Medicare based on description."
            is_positive = True

        self._add_factor_score("insurance_coverage", score, reason, is_concern, is_positive, confidence_level)

    def _score_treatment_type_match(self):
        """Score how well treatment types match patient preferences"""
        patient_prefs = self.patient_profile.preferred_treatment_types
        treatment_types = self.treatment_data.treatment_types
        
        score, matches = self._text_list_match_score(patient_prefs, treatment_types)
        
        is_positive = score >= 0.7
        is_concern = score < 0.4 and bool(patient_prefs)
        confidence_level = "high" if score >= 0.8 else "medium"
        
        if matches:
            reason = f"Treatment type: Matches your preferences ({', '.join(matches[:2])})."
        elif not patient_prefs:
            score = 0.7  # Neutral-positive if no preferences specified
            reason = "Treatment type: No specific preferences noted in your profile."
        elif treatment_types:
            reason = f"Treatment type: Available types ({', '.join(treatment_types[:2])}) may not match your preferences."
        else:
            reason = "Treatment type: Treatment approach not clearly specified."

        self._add_factor_score("treatment_type_match", score, reason, is_concern, is_positive, confidence_level)

    def _score_provider_quality(self):
        """Score provider quality and credentials"""
        rating = self.treatment_data.provider_rating
        certifications = self.treatment_data.specialty_certifications
        
        score = 0.5  # Neutral baseline
        reason = "Provider quality: No rating or credential information available."
        is_positive = False
        is_concern = False
        confidence_level = "low"

        if rating is not None:
            if rating >= 4.5:
                score = 1.0
                reason = f"Provider quality: Excellent rating ({rating}/5.0)."
                is_positive = True
                confidence_level = "high"
            elif rating >= 4.0:
                score = 0.8
                reason = f"Provider quality: Very good rating ({rating}/5.0)."
                is_positive = True
                confidence_level = "high"
            elif rating >= 3.5:
                score = 0.6
                reason = f"Provider quality: Good rating ({rating}/5.0)."
                confidence_level = "medium"
            elif rating >= 3.0:
                score = 0.4
                reason = f"Provider quality: Average rating ({rating}/5.0)."
            else:
                score = 0.2
                reason = f"Provider quality: Below average rating ({rating}/5.0)."
                is_concern = True

        # Bonus for certifications
        if certifications:
            score = min(1.0, score + 0.1)
            reason += f" Provider has specialty certifications: {', '.join(certifications[:2])}."
            is_positive = True
            confidence_level = "high"

        self._add_factor_score("provider_quality", score, reason, is_concern, is_positive, confidence_level)

    def _parse_cost_estimate(self, cost_str: str) -> Tuple[Optional[float], Optional[float]]:
        """Parse cost estimate string to get min/max values"""
        if not cost_str:
            return None, None
        
        # Handle "Covered by insurance" or similar
        if any(word in cost_str.lower() for word in ["covered", "free", "no cost"]):
            return 0.0, 0.0
        
        # Extract numbers from cost string
        numbers = re.findall(r'\$?[\d,]+', cost_str.replace(',', ''))
        if not numbers:
            return None, None
        
        # Convert to floats
        try:
            if len(numbers) == 1:
                cost = float(numbers[0].replace('$', '').replace(',', ''))
                return cost, cost
            elif len(numbers) >= 2:
                min_cost = float(numbers[0].replace('$', '').replace(',', ''))
                max_cost = float(numbers[1].replace('$', '').replace(',', ''))
                return min_cost, max_cost
        except ValueError:
            return None, None
        
        return None, None

    def _score_cost_affordability(self):
        """Score treatment cost affordability"""
        cost_str = self.treatment_data.estimated_cost
        patient_budget = self.patient_profile.budget_max
        
        score = 0.5  # Neutral baseline
        reason = "Cost: No cost information available."
        is_positive = False
        is_concern = False
        confidence_level = "low"

        if cost_str:
            min_cost, max_cost = self._parse_cost_estimate(cost_str)
            
            if min_cost == 0 and max_cost == 0:  # Covered by insurance
                score = 1.0
                reason = "Cost: Excellent - covered by insurance or free."
                is_positive = True
                confidence_level = "high"
            elif min_cost is not None and max_cost is not None:
                avg_cost = (min_cost + max_cost) / 2
                
                if patient_budget is not None:
                    if avg_cost <= patient_budget:
                        score = 1.0
                        reason = f"Cost: Within budget - estimated ${avg_cost:,.0f} (budget: ${patient_budget:,.0f})."
                        is_positive = True
                        confidence_level = "high"
                    elif avg_cost <= patient_budget * 1.2:  # 20% over budget
                        score = 0.6
                        reason = f"Cost: Slightly over budget - estimated ${avg_cost:,.0f} (budget: ${patient_budget:,.0f})."
                        is_concern = True
                    else:
                        score = 0.2
                        reason = f"Cost: Significantly over budget - estimated ${avg_cost:,.0f} (budget: ${patient_budget:,.0f})."
                        is_concern = True
                        confidence_level = "low"
                else:
                    # No budget specified, score based on general affordability
                    if avg_cost < 1000:
                        score = 0.8
                        reason = f"Cost: Reasonable - estimated ${avg_cost:,.0f}."
                        is_positive = True
                    elif avg_cost < COST_CONCERN_THRESHOLD:
                        score = 0.6
                        reason = f"Cost: Moderate - estimated ${avg_cost:,.0f}."
                    else:
                        score = 0.3
                        reason = f"Cost: High - estimated ${avg_cost:,.0f}. Consider insurance coverage."
                        is_concern = True

        self._add_factor_score("cost_affordability", score, reason, is_concern, is_positive, confidence_level)

    def calculate_confidence_score(self) -> float:
        """Calculate overall confidence score"""
        logger.info(f"Calculating confidence score for treatment {self.treatment_data.treatment_id}")
        
        # Clear previous calculations
        self.match_details.factor_scores = []
        self.raw_factor_values = {}

        # Score all factors
        self._score_condition_match()
        self._score_age_eligibility()
        self._score_location_accessibility()
        self._score_insurance_coverage()
        self._score_treatment_type_match()
        self._score_provider_quality()
        self._score_cost_affordability()

        # Calculate weighted score
        total_weighted_score = 0
        total_weight = 0
        
        for factor in self.match_details.factor_scores:
            total_weighted_score += factor.score * factor.weight
            total_weight += factor.weight
            logger.debug(f"Factor: {factor.factor_name}, Score: {factor.score:.2f}, Weight: {factor.weight:.2f}")

        if total_weight == 0:
            overall_score_normalized = 0.0
        else:
            overall_score_normalized = (total_weighted_score / total_weight) * 100

        # Ensure score is within 0-100 range
        self.match_details.overall_score = round(max(0, min(overall_score_normalized, 100)), 2)
        
        logger.info(f"Overall confidence score: {self.match_details.overall_score:.2f}%")
        return self.match_details.overall_score

    def _determine_match_level(self, score: float) -> str:
        """Determine match level based on score"""
        if score >= 85:
            return "excellent"
        elif score >= 70:
            return "good"
        elif score >= 50:
            return "fair"
        else:
            return "poor"

    def generate_summary_explanation(self) -> str:
        """Generate a human-readable explanation of the match"""
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()

        score = self.match_details.overall_score
        match_level = self._determine_match_level(score)
        
        explanation = f"This treatment appears to be a {match_level} match ({score:.1f}%) for your needs. "

        # Highlight top positive factors
        positive_factors = [fs for fs in self.match_details.factor_scores 
                          if fs.is_positive_match and fs.score >= 0.7]
        if positive_factors:
            top_positive = sorted(positive_factors, key=lambda x: x.score * x.weight, reverse=True)[:2]
            explanation += "Key strengths: " + "; ".join([f.reason for f in top_positive]) + ". "

        # Highlight concerns
        concerns = [fs for fs in self.match_details.factor_scores 
                   if fs.is_concern and fs.score < 0.5]
        if concerns:
            top_concerns = sorted(concerns, key=lambda x: x.weight, reverse=True)[:2]
            explanation += "Important considerations: " + "; ".join([f.reason for f in top_concerns]) + ". "

        return explanation.strip()

    def get_key_strengths(self) -> List[str]:
        """Get list of key matching strengths"""
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
        
        return [fs.reason for fs in self.match_details.factor_scores 
                if fs.is_positive_match and fs.score >= 0.7]

    def get_potential_concerns(self) -> List[str]:
        """Get list of potential concerns"""
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
        
        concerns = [fs.reason for fs in self.match_details.factor_scores 
                   if fs.is_concern and fs.score < 0.6]
        
        # Add urgency-based concerns
        urgency = self.patient_profile.treatment_urgency
        wait_time = self.treatment_data.wait_time_days
        
        if urgency == "emergency" and wait_time and wait_time > 0:
            concerns.append(f"Wait time of {wait_time} days may be too long for emergency treatment.")
        elif urgency == "urgent" and wait_time and wait_time > 7:
            concerns.append(f"Wait time of {wait_time} days may be longer than ideal for urgent treatment.")

        return concerns

    def get_recommended_actions(self) -> List[str]:
        """Get list of recommended actions"""
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
        
        actions = []
        
        # Insurance-related actions
        insurance_factor = next((fs for fs in self.match_details.factor_scores 
                               if fs.factor_name == "insurance_coverage"), None)
        if insurance_factor and insurance_factor.is_concern:
            actions.append("Contact the provider to verify insurance coverage before scheduling.")
        
        # Cost-related actions
        cost_factor = next((fs for fs in self.match_details.factor_scores 
                          if fs.factor_name == "cost_affordability"), None)
        if cost_factor and cost_factor.is_concern:
            actions.append("Discuss payment options or financial assistance programs with the provider.")
        
        # Location-related actions
        location_factor = next((fs for fs in self.match_details.factor_scores 
                              if fs.factor_name == "location_accessibility"), None)
        if location_factor and location_factor.is_concern:
            actions.append("Consider transportation options or look for closer alternatives.")
        
        # General recommendations
        if self.match_details.overall_score >= 70:
            actions.append("This appears to be a strong match - consider scheduling a consultation.")
        elif self.match_details.overall_score >= 50:
            actions.append("Review the details carefully and contact the provider with any questions.")
        else:
            actions.append("Consider exploring additional treatment options with better alignment.")
        
        if self.treatment_data.website_url:
            actions.append(f"Visit the provider's website for more information: {self.treatment_data.website_url}")
        
        return actions

    def assess_urgency(self) -> str:
        """Assess treatment urgency based on patient needs and wait times"""
        patient_urgency = self.patient_profile.treatment_urgency
        wait_time = self.treatment_data.wait_time_days or 0
        
        if patient_urgency == "emergency":
            if wait_time == 0:
                return "Immediate treatment available - excellent for emergency needs."
            else:
                return f"WARNING: {wait_time} day wait may be too long for emergency treatment."
        elif patient_urgency == "urgent":
            if wait_time <= 7:
                return f"Wait time of {wait_time} days is acceptable for urgent treatment."
            else:
                return f"CONCERN: {wait_time} day wait may be longer than ideal for urgent treatment."
        elif patient_urgency == "routine":
            if wait_time <= 30:
                return f"Wait time of {wait_time} days is reasonable for routine treatment."
            else:
                return f"Longer wait time of {wait_time} days for routine treatment."
        else:  # elective
            return f"Wait time of {wait_time} days for elective treatment - allows for planning."

    def get_full_confidence_analysis(self) -> TreatmentConfidenceResult:
        """
        Perform complete analysis and return comprehensive results
        """
        final_score = self.calculate_confidence_score()
        match_level = self._determine_match_level(final_score)
        
        return TreatmentConfidenceResult(
            user_id=self.patient_profile.user_id,
            treatment_id=self.treatment_data.treatment_id,
            treatment_name=self.treatment_data.name,
            provider_name=self.treatment_data.provider_name,
            confidence_score=final_score,
            match_level=match_level,
            summary_explanation=self.generate_summary_explanation(),
            key_strengths=self.get_key_strengths(),
            potential_concerns=self.get_potential_concerns(),
            recommended_actions=self.get_recommended_actions(),
            urgency_assessment=self.assess_urgency(),
            raw_match_details=self.match_details
        )

# --- Example Usage (for testing) ---
if __name__ == "__main__":
    # Sample Patient Profile
    sample_patient = PatientProfileInput(
        user_id="patient123",
        age=45,
        primary_condition="diabetes",
        secondary_conditions=["hypertension"],
        insurance_provider="Blue Cross Blue Shield",
        insurance_plan_type="PPO",
        location_zip="12345",
        location_state="California",
        max_travel_distance=50,
        budget_max=2000.0,
        treatment_urgency="routine",
        preferred_treatment_types=["endocrinology", "primary care"]
    )

    # Sample Treatment Data - Strong Match
    strong_match_treatment = TreatmentDataInput(
        treatment_id="treat001",
        name="Comprehensive Diabetes Management Program",
        provider_name="Regional Medical Center",
        treatment_types=["endocrinology", "diabetes management"],
        conditions_treated=["diabetes", "hypertension", "metabolic disorders"],
        min_age=18,
        max_age=80,
        location_city="San Francisco",
        location_state="California",
        distance_miles=25.0,
        accepted_insurance=["Blue Cross Blue Shield", "Aetna", "Medicare"],
        estimated_cost="Covered by insurance",
        wait_time_days=14,
        provider_rating=4.8,
        specialty_certifications=["Endocrinology Board Certified"],
        description="Comprehensive diabetes care with personalized treatment plans"
    )

    # Sample Treatment Data - Weak Match
    weak_match_treatment = TreatmentDataInput(
        treatment_id="treat002",
        name="Emergency Surgery Center",
        provider_name="City Hospital",
        treatment_types=["emergency surgery", "trauma care"],
        conditions_treated=["trauma", "emergency conditions"],
        min_age=18,
        location_city="Los Angeles",
        location_state="California", 
        distance_miles=150.0,
        accepted_insurance=["Medicare", "Medicaid"],
        estimated_cost="$15,000 - $50,000",
        wait_time_days=0,
        provider_rating=3.2,
        description="Emergency surgical services"
    )

    print("=== Testing Treatment Confidence Scorer ===\n")
    
    # Test strong match
    print("--- Strong Match Analysis ---")
    scorer1 = TreatmentConfidenceScorer(sample_patient, strong_match_treatment)
    result1 = scorer1.get_full_confidence_analysis()
    
    print(f"Treatment: {result1.treatment_name}")
    print(f"Provider: {result1.provider_name}")
    print(f"Confidence Score: {result1.confidence_score:.1f}% ({result1.match_level})")
    print(f"Summary: {result1.summary_explanation}")
    print(f"Key Strengths: {result1.key_strengths}")
    print(f"Concerns: {result1.potential_concerns}")
    print(f"Recommended Actions: {result1.recommended_actions}")
    print(f"Urgency Assessment: {result1.urgency_assessment}\n")
    
    # Test weak match
    print("--- Weak Match Analysis ---")
    scorer2 = TreatmentConfidenceScorer(sample_patient, weak_match_treatment)
    result2 = scorer2.get_full_confidence_analysis()
    
    print(f"Treatment: {result2.treatment_name}")
    print(f"Provider: {result2.provider_name}")
    print(f"Confidence Score: {result2.confidence_score:.1f}% ({result2.match_level})")
    print(f"Summary: {result2.summary_explanation}")
    print(f"Key Strengths: {result2.key_strengths}")
    print(f"Concerns: {result2.potential_concerns}")
    print(f"Recommended Actions: {result2.recommended_actions}")
    print(f"Urgency Assessment: {result2.urgency_assessment}")
