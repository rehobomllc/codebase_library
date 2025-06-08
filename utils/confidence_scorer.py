import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Constants for Scoring ---
# Weights for different factors (summing to 1.0 or normalized later)
WEIGHTS = {
    "gpa": 0.15,
    "major_field": 0.20,
    "academic_level": 0.10,
    "location": 0.05,
    "demographics": 0.10,
    "keywords_description": 0.15,
    "application_complexity": -0.05, # Negative weight if too complex
    "deadline_urgency": 0.05, # Small positive for moderate urgency, negative for too urgent/past
    "data_quality": 0.10,
    "historical_success": 0.05, # Placeholder
}

# Thresholds and parameters
GPA_TOLERANCE = 0.2  # e.g., if user GPA is 3.3 and req is 3.5, it's within tolerance
URGENT_DEADLINE_DAYS = 7
VERY_URGENT_DEADLINE_DAYS = 2
IDEAL_DEADLINE_RANGE_DAYS = (15, 90) # Sweet spot for deadlines

# --- Dataclasses for Inputs and Outputs ---

@dataclass
class UserProfileInput:
    user_id: str
    gpa: Optional[float] = None
    major: Optional[str] = None
    academic_level: Optional[str] = None # e.g., "Undergraduate", "Postgraduate"
    location_state: Optional[str] = None
    location_country: Optional[str] = None
    demographics: List[str] = field(default_factory=list) # e.g., ["first-generation", "female_in_stem"]
    interests_keywords: List[str] = field(default_factory=list) # Keywords from user profile/merits
    preferred_complexity: Optional[str] = "medium" # "low", "medium", "high"
    # Add other relevant fields from your user profile schema

@dataclass
class ScholarshipDataInput:
    scholarship_id: str
    name: str
    min_gpa: Optional[float] = None
    eligible_majors: List[str] = field(default_factory=list)
    eligible_academic_levels: List[str] = field(default_factory=list)
    eligible_locations_state: List[str] = field(default_factory=list)
    eligible_locations_country: List[str] = field(default_factory=list)
    demographic_specific: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    description: Optional[str] = ""
    application_complexity_estimate: Optional[str] = "medium" # "low", "medium", "high" (e.g. based on num_essays)
    deadline: Optional[str] = None # ISO format string: "YYYY-MM-DD"
    award_amount: Optional[str] = None # Store as string to handle ranges like "$1,000 - $5,000"
    url: Optional[str] = None
    # Add other relevant fields from your scholarship data schema

@dataclass
class FactorScore:
    factor_name: str
    score: float  # 0.0 to 1.0
    reason: str
    weight: float
    is_concern: bool = False
    is_positive_match: bool = False

@dataclass
class MatchDetails:
    overall_score: float = 0.0
    factor_scores: List[FactorScore] = field(default_factory=list)

@dataclass
class ConfidenceResult:
    user_id: str
    scholarship_id: str
    scholarship_name: str
    confidence_score: float # Overall score (0-100)
    summary_explanation: str
    matching_criteria_details: List[str] # Positive matches
    potential_concerns: List[str] # Negative points or warnings
    suggested_actions: List[str] # What user can do
    raw_match_details: MatchDetails # For debugging or more detailed display


class ScholarshipConfidenceScorer:
    def __init__(self, user_profile: UserProfileInput, scholarship_data: ScholarshipDataInput, historical_data: Optional[Dict] = None):
        self.user_profile = user_profile
        self.scholarship_data = scholarship_data
        self.historical_data = historical_data if historical_data else {} # For future use
        self.match_details = MatchDetails()
        self.raw_factor_values = {} # To store intermediate values before weighting

        if not user_profile or not scholarship_data:
            raise ValueError("User profile and scholarship data must be provided.")
        logger.info(f"Scorer initialized for user {user_profile.user_id} and scholarship {scholarship_data.scholarship_id} ('{scholarship_data.name}')")

    def _add_factor_score(self, name: str, score: float, reason: str, is_concern: bool = False, is_positive: bool = False):
        weight = WEIGHTS.get(name, 0.0)
        self.match_details.factor_scores.append(
            FactorScore(factor_name=name, score=score, reason=reason, weight=weight, is_concern=is_concern, is_positive_match=is_positive)
        )
        self.raw_factor_values[name] = score # Store raw unweighted score for this factor

    def _score_gpa(self):
        user_gpa = self.user_profile.gpa
        scholarship_min_gpa = self.scholarship_data.min_gpa
        score = 0.5  # Neutral score if no GPA info
        reason = "GPA match: Not applicable or information missing."
        is_positive = False
        is_concern = False

        if user_gpa is not None and scholarship_min_gpa is not None:
            if user_gpa >= scholarship_min_gpa:
                score = 1.0
                reason = f"GPA match: Your GPA ({user_gpa}) meets or exceeds the minimum requirement ({scholarship_min_gpa})."
                is_positive = True
            elif user_gpa >= scholarship_min_gpa - GPA_TOLERANCE:
                score = 0.6
                reason = f"GPA consideration: Your GPA ({user_gpa}) is slightly below the minimum ({scholarship_min_gpa}) but may still be considered."
                is_concern = True
            else:
                score = 0.1
                reason = f"GPA mismatch: Your GPA ({user_gpa}) is below the minimum requirement ({scholarship_min_gpa})."
                is_concern = True
        elif scholarship_min_gpa is not None and user_gpa is None:
            score = 0.3
            reason = "GPA requirement: Scholarship specifies a minimum GPA, but your GPA is not in your profile."
            is_concern = True
        elif user_gpa is not None and scholarship_min_gpa is None:
            score = 0.7 # Slightly positive if user has GPA but scholarship doesn't specify
            reason = "GPA match: No minimum GPA specified by the scholarship; your GPA is recorded."
            is_positive = True
        
        self._add_factor_score("gpa", score, reason, is_concern, is_positive)

    def _text_list_match_score(self, user_items: List[str], scholarship_items: List[str]) -> Tuple[float, List[str]]:
        if not scholarship_items: # Scholarship is open to all in this category
            return 0.7, [] # Slightly positive, no specific restriction
        if not user_items: # User has not specified, scholarship has
            return 0.3, [] # Low score, user needs to specify

        user_set = {item.lower().strip() for item in user_items if item}
        scholarship_set = {item.lower().strip() for item in scholarship_items if item}
        
        intersection = user_set.intersection(scholarship_set)
        if intersection:
            return 1.0, list(intersection)
        
        # Partial match (e.g., "Computer Science" vs "Science and Engineering") - simple for now
        for u_item in user_set:
            for s_item in scholarship_set:
                if u_item in s_item or s_item in u_item:
                    return 0.65, [f"Partial match: '{u_item}' related to '{s_item}'"]
        return 0.1, [] # No match

    def _score_major_field(self):
        score, matches = self._text_list_match_score(
            [self.user_profile.major] if self.user_profile.major else [],
            self.scholarship_data.eligible_majors
        )
        reason = "Major/Field: Scholarship is open to all majors."
        is_positive = score >= 0.7
        is_concern = score < 0.5 and bool(self.scholarship_data.eligible_majors)

        if matches:
            reason = f"Major/Field match: Your major aligns with eligible fields ({', '.join(matches)})."
        elif self.scholarship_data.eligible_majors:
            reason = f"Major/Field mismatch: Your major may not align with eligible fields ({', '.join(self.scholarship_data.eligible_majors)})."
        elif not self.scholarship_data.eligible_majors and self.user_profile.major:
             reason = "Major/Field: Scholarship is open to all majors; your major is recorded."

        self._add_factor_score("major_field", score, reason, is_concern, is_positive)

    def _score_academic_level(self):
        score, matches = self._text_list_match_score(
            [self.user_profile.academic_level] if self.user_profile.academic_level else [],
            self.scholarship_data.eligible_academic_levels
        )
        reason = "Academic Level: Scholarship is open to all academic levels."
        is_positive = score >= 0.7
        is_concern = score < 0.5 and bool(self.scholarship_data.eligible_academic_levels)

        if matches:
            reason = f"Academic Level match: Your level ({', '.join(matches)}) is eligible."
        elif self.scholarship_data.eligible_academic_levels:
            reason = f"Academic Level mismatch: Your level may not align with eligible levels ({', '.join(self.scholarship_data.eligible_academic_levels)})."
        elif not self.scholarship_data.eligible_academic_levels and self.user_profile.academic_level:
            reason = "Academic Level: Scholarship is open to all levels; your level is recorded."

        self._add_factor_score("academic_level", score, reason, is_concern, is_positive)

    def _score_location(self):
        # This is simplified. Real location matching can be complex (city, region, specific institutions).
        # For now, just state-level.
        user_locs = [self.user_profile.location_state] if self.user_profile.location_state else []
        score, matches = self._text_list_match_score(user_locs, self.scholarship_data.eligible_locations_state)
        
        reason = "Location: No specific location requirements or match."
        is_positive = score >= 0.7
        is_concern = score < 0.5 and bool(self.scholarship_data.eligible_locations_state)

        if matches:
            reason = f"Location match: Your state ({', '.join(matches)}) is eligible."
        elif self.scholarship_data.eligible_locations_state:
            reason = f"Location mismatch: Your state may not be eligible ({', '.join(self.scholarship_data.eligible_locations_state)})."
        elif not self.scholarship_data.eligible_locations_state and self.user_profile.location_state:
            reason = "Location: Scholarship has no state restrictions; your location is noted."

        self._add_factor_score("location", score, reason, is_concern, is_positive)

    def _score_demographics(self):
        score, matches = self._text_list_match_score(
            self.user_profile.demographics,
            self.scholarship_data.demographic_specific
        )
        reason = "Demographics: Scholarship is not specific, or no demographic match found."
        is_positive = score >= 0.7
        is_concern = score < 0.5 and bool(self.scholarship_data.demographic_specific) and bool(self.user_profile.demographics)

        if matches:
            reason = f"Demographic match: Aligns with your profile on ({', '.join(matches)})."
        elif self.scholarship_data.demographic_specific and not self.user_profile.demographics:
            reason = f"Demographics: Scholarship has specific criteria ({', '.join(self.scholarship_data.demographic_specific)}), but your demographic info is not in profile."
            is_concern = True # User needs to update profile
        elif self.scholarship_data.demographic_specific and self.user_profile.demographics:
             reason = f"Demographics: Your profile may not match specific criteria ({', '.join(self.scholarship_data.demographic_specific)})."
        
        self._add_factor_score("demographics", score, reason, is_concern, is_positive)

    def _score_keywords_and_description(self):
        user_keywords = {kw.lower().strip() for kw in self.user_profile.interests_keywords if kw}
        scholarship_kws = {kw.lower().strip() for kw in self.scholarship_data.keywords if kw}
        
        # Also consider words from description
        description_words = set()
        if self.scholarship_data.description:
            description_words = {word.lower().strip(".,!?;:") for word in self.scholarship_data.description.split() if len(word) > 3}
        
        scholarship_all_terms = scholarship_kws.union(description_words)
        
        if not scholarship_all_terms and not user_keywords:
            self._add_factor_score("keywords_description", 0.5, "Keywords/Description: Insufficient information from both profile and scholarship for keyword matching.", False, False)
            return
        if not scholarship_all_terms and user_keywords:
            self._add_factor_score("keywords_description", 0.6, "Keywords/Description: Scholarship has no specific keywords; your interests are noted.", False, True)
            return
        if not user_keywords and scholarship_all_terms:
            self._add_factor_score("keywords_description", 0.3, "Keywords/Description: Scholarship has keywords, but your interests are not specified in profile.", True, False)
            return

        common_keywords = user_keywords.intersection(scholarship_all_terms)
        
        score = 0.1
        reason = "Keywords/Description: Low relevance based on keywords and description."
        is_positive = False
        is_concern = True

        if common_keywords:
            num_common = len(common_keywords)
            # Simple scoring: more common keywords = better score
            if num_common >= 3: score = 1.0
            elif num_common == 2: score = 0.8
            elif num_common == 1: score = 0.6
            reason = f"Keywords/Description match: Found {num_common} matching terms ({', '.join(list(common_keywords)[:3])})."
            is_positive = True
            is_concern = False
        
        self._add_factor_score("keywords_description", score, reason, is_concern, is_positive)

    def _score_application_complexity(self):
        # Heuristic: "low", "medium", "high"
        complexity_map = {"low": 0, "medium": 1, "high": 2}
        user_pref_val = complexity_map.get(self.user_profile.preferred_complexity, 1)
        scholarship_comp_val = complexity_map.get(self.scholarship_data.application_complexity_estimate, 1)

        diff = abs(user_pref_val - scholarship_comp_val)
        score = 1.0
        reason = "Application Complexity: Aligns with your preference."
        is_positive = True
        is_concern = False

        if diff == 1: # One level off
            score = 0.7
            reason = f"Application Complexity: Scholarship complexity ({self.scholarship_data.application_complexity_estimate}) is different from your preference ({self.user_profile.preferred_complexity})."
            is_concern = True
            is_positive = False
        elif diff == 2: # Two levels off
            score = 0.3
            reason = f"Application Complexity: Scholarship complexity ({self.scholarship_data.application_complexity_estimate}) significantly differs from your preference ({self.user_profile.preferred_complexity})."
            is_concern = True
            is_positive = False
        
        # This factor has a negative weight, so a high score (1.0) means low complexity penalty.
        self._add_factor_score("application_complexity", score, reason, is_concern, is_positive)


    def _score_deadline_urgency(self):
        deadline_str = self.scholarship_data.deadline
        score = 0.5 # Neutral if no deadline
        reason = "Deadline: No deadline specified or unable to parse."
        is_positive = False
        is_concern = False

        if deadline_str:
            try:
                deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d")
                today = datetime.now()
                days_until = (deadline_date - today).days

                if days_until < 0:
                    score = 0.0
                    reason = f"Deadline: Expired on {deadline_str} ({abs(days_until)} days ago)."
                    is_concern = True
                elif days_until <= VERY_URGENT_DEADLINE_DAYS:
                    score = 0.3 # Low score because it's very urgent, might be too late
                    reason = f"Deadline: Extremely urgent! Due in {days_until} day(s) ({deadline_str}). Immediate action required."
                    is_concern = True
                elif days_until <= URGENT_DEADLINE_DAYS:
                    score = 0.6
                    reason = f"Deadline: Urgent! Due in {days_until} days ({deadline_str}). Prompt action recommended."
                    is_concern = True
                elif IDEAL_DEADLINE_RANGE_DAYS[0] <= days_until <= IDEAL_DEADLINE_RANGE_DAYS[1]:
                    score = 1.0
                    reason = f"Deadline: Good timing. Due in {days_until} days ({deadline_str})."
                    is_positive = True
                elif days_until > IDEAL_DEADLINE_RANGE_DAYS[1]:
                    score = 0.8
                    reason = f"Deadline: Plenty of time. Due in {days_until} days ({deadline_str})."
                    is_positive = True
                else: # days_until > URGENT_DEADLINE_DAYS but < IDEAL_DEADLINE_RANGE_DAYS[0]
                    score = 0.7
                    reason = f"Deadline: Approaching. Due in {days_until} days ({deadline_str})."
                    is_positive = True

            except ValueError:
                reason = f"Deadline: Invalid date format ('{deadline_str}')."
                score = 0.2
                is_concern = True
        
        self._add_factor_score("deadline_urgency", score, reason, is_concern, is_positive)

    def _score_data_quality(self):
        # Simple check: award amount, deadline, and description present?
        num_present_fields = 0
        max_fields = 3
        reasons = []

        if self.scholarship_data.award_amount and self.scholarship_data.award_amount.lower() not in ["varies", "not specified", "n/a", ""]:
            num_present_fields += 1
        else:
            reasons.append("Award amount is missing or vague.")
        
        if self.scholarship_data.deadline:
            num_present_fields += 1
        else:
            reasons.append("Deadline is missing.")

        if self.scholarship_data.description and len(self.scholarship_data.description) > 20: # Arbitrary length for "decent" description
            num_present_fields += 1
        else:
            reasons.append("Description is very short or missing.")
        
        score = 0.2 + (0.8 * (num_present_fields / max_fields)) # Base score of 0.2
        reason = f"Data Quality: {num_present_fields}/{max_fields} key fields (amount, deadline, description) are well-defined. "
        if reasons:
            reason += "Issues: " + " ".join(reasons)
        
        is_concern = score < 0.6
        is_positive = score >= 0.8
        self._add_factor_score("data_quality", score, reason, is_concern, is_positive)

    def _score_historical_success(self):
        # Placeholder: In a real system, this would query a DB or use ML model
        # For now, assume neutral
        score = 0.5
        reason = "Historical Success: Data not available for this factor."
        self._add_factor_score("historical_success", score, reason)

    def calculate_confidence_score(self) -> float:
        logger.info(f"Calculating confidence score for S:{self.scholarship_data.scholarship_id} U:{self.user_profile.user_id}")
        self.match_details.factor_scores = [] # Reset previous calculations if any
        self.raw_factor_values = {}

        self._score_gpa()
        self._score_major_field()
        self._score_academic_level()
        self._score_location()
        self._score_demographics()
        self._score_keywords_and_description()
        self._score_application_complexity()
        self._score_deadline_urgency()
        self._score_data_quality()
        self._score_historical_success() # Placeholder

        total_weighted_score = 0
        total_weight = 0
        
        for factor in self.match_details.factor_scores:
            total_weighted_score += factor.score * factor.weight
            total_weight += factor.weight
            logger.debug(f"Factor: {factor.factor_name}, Raw Score: {factor.score:.2f}, Weight: {factor.weight:.2f}, Weighted: {factor.score * factor.weight:.2f}, Reason: {factor.reason}")

        if total_weight == 0: # Should not happen if WEIGHTS are defined
            overall_score_normalized = 0.0
        else:
            # Normalize the score to be out of 100
            overall_score_normalized = (total_weighted_score / total_weight) * 100
        
        self.match_details.overall_score = round(max(0, min(overall_score_normalized, 100)), 2) # Ensure 0-100 range
        logger.info(f"Overall confidence score: {self.match_details.overall_score:.2f}%")
        return self.match_details.overall_score

    def generate_match_explanation(self) -> str:
        if not self.match_details.factor_scores:
            self.calculate_confidence_score() # Ensure scores are calculated

        score = self.match_details.overall_score
        
        if score >= 80:
            level = "very strong"
        elif score >= 65:
            level = "strong"
        elif score >= 50:
            level = "moderate"
        elif score >= 35:
            level = "potential"
        else:
            level = "less likely"

        explanation = f"This scholarship appears to be a {level} match ({score:.1f}%) for you. "
        
        positive_highlights = [fs.reason for fs in self.match_details.factor_scores if fs.is_positive_match and fs.score * fs.weight > 0.03] # Highlight significant positive factors
        if positive_highlights:
            explanation += "Key strengths include: " + "; ".join(positive_highlights[:2]) + ". " # Show top 2

        concern_highlights = [fs.reason for fs in self.match_details.factor_scores if fs.is_concern and fs.score * fs.weight < -0.02 or (fs.score < 0.4 and fs.weight > 0.05)] # Highlight significant concerns
        if concern_highlights:
            explanation += "Points to consider: " + "; ".join(concern_highlights[:2]) + ". "
        
        if score < 50 and not concern_highlights: # Low score but no obvious major concern flagged
             explanation += "Several smaller factors contribute to a lower overall match score. "

        return explanation.strip()

    def get_matching_criteria(self) -> List[str]:
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
        
        return [fs.reason for fs in self.match_details.factor_scores if fs.is_positive_match and fs.score >= 0.7]

    def identify_potential_concerns(self) -> List[str]:
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
        
        concerns = [fs.reason for fs in self.match_details.factor_scores if fs.is_concern and fs.score < 0.6]
        
        # Add a general concern if data quality is low
        data_quality_factor = next((fs for fs in self.match_details.factor_scores if fs.factor_name == "data_quality"), None)
        if data_quality_factor and data_quality_factor.score < 0.5:
            concerns.append("The information available for this scholarship is limited, which may affect match accuracy.")
            
        return concerns

    def suggest_improvements_or_actions(self) -> List[str]:
        if not self.match_details.factor_scores:
            self.calculate_confidence_score()
            
        suggestions = []
        # Based on GPA
        gpa_factor = next((fs for fs in self.match_details.factor_scores if fs.factor_name == "gpa"), None)
        if gpa_factor and gpa_factor.is_concern:
            if "your GPA is not in your profile" in gpa_factor.reason:
                suggestions.append("Consider adding your GPA to your profile for more accurate matching.")
            elif "slightly below" in gpa_factor.reason:
                 suggestions.append("While your GPA is slightly below the minimum, some scholarships offer flexibility. It might be worth applying if other criteria are strong.")
        
        # Based on missing profile info for specific scholarship criteria
        for factor_name in ["major_field", "academic_level", "location", "demographics"]:
            factor = next((fs for fs in self.match_details.factor_scores if fs.factor_name == factor_name), None)
            profile_attr = getattr(self.user_profile, factor_name.split('_')[0] if factor_name != "major_field" else "major", None) # Simplified mapping
            
            if factor and factor.is_concern and not profile_attr: # If it's a concern because profile info is missing
                 if f"your {factor_name.replace('_', ' ')} is not in your profile" in factor.reason or "not specified in profile" in factor.reason:
                    suggestions.append(f"Adding your {factor_name.replace('_', ' ')} to your profile could improve match accuracy.")

        # Based on deadline
        deadline_factor = next((fs for fs in self.match_details.factor_scores if fs.factor_name == "deadline_urgency"), None)
        if deadline_factor and deadline_factor.is_concern and "Extremely urgent" in deadline_factor.reason:
            suggestions.append("This scholarship deadline is very soon. Prioritize this application if you intend to apply.")
        elif deadline_factor and deadline_factor.is_concern and "Urgent!" in deadline_factor.reason:
            suggestions.append("The deadline is approaching quickly. Plan your application process soon.")

        if not suggestions and self.match_details.overall_score >= 50:
            suggestions.append("This looks like a reasonable match. Review the scholarship details and consider applying.")
        elif not suggestions and self.match_details.overall_score < 50:
            suggestions.append("This may not be the strongest match. Focus on scholarships with higher alignment if available.")
            
        if self.scholarship_data.url:
            suggestions.append(f"Always verify details on the official scholarship page: {self.scholarship_data.url}")
        else:
            suggestions.append("Official scholarship URL is missing; try to find it to verify details.")

        return list(set(suggestions)) # Remove duplicates

    def get_full_confidence_analysis(self) -> ConfidenceResult:
        """
        Performs all scoring and analysis, returning a comprehensive result.
        This is the primary method to call after initializing the scorer.
        """
        final_score = self.calculate_confidence_score() # This populates self.match_details
        
        return ConfidenceResult(
            user_id=self.user_profile.user_id,
            scholarship_id=self.scholarship_data.scholarship_id,
            scholarship_name=self.scholarship_data.name,
            confidence_score=final_score,
            summary_explanation=self.generate_match_explanation(),
            matching_criteria_details=self.get_matching_criteria(),
            potential_concerns=self.identify_potential_concerns(),
            suggested_actions=self.suggest_improvements_or_actions(),
            raw_match_details=self.match_details
        )

# --- Example Usage (for testing) ---
if __name__ == "__main__":
    # Sample User Profile
    sample_user = UserProfileInput(
        user_id="user123",
        gpa=3.8,
        major="Computer Science",
        academic_level="Undergraduate",
        location_state="California",
        demographics=["first-generation", "hispanic"],
        interests_keywords=["AI", "machine learning", "software development", "robotics"],
        preferred_complexity="medium"
    )

    # Sample Scholarship Data
    strong_match_scholarship = ScholarshipDataInput(
        scholarship_id="sch001",
        name="Tech Innovators Scholarship",
        min_gpa=3.5,
        eligible_majors=["Computer Science", "Software Engineering", "AI"],
        eligible_academic_levels=["Undergraduate"],
        eligible_locations_state=["California", "New York"],
        demographic_specific=["first-generation"],
        keywords=["AI", "innovation", "technology", "coding"],
        description="A scholarship for innovative undergraduate students in tech fields, especially those passionate about AI.",
        application_complexity_estimate="medium",
        deadline=(datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d"), # Due in 60 days
        award_amount="$5,000",
        url="http://example.com/techinnovators"
    )

    weak_match_scholarship = ScholarshipDataInput(
        scholarship_id="sch002",
        name="Arts & Humanities Grant",
        min_gpa=3.0,
        eligible_majors=["History", "Literature", "Philosophy"],
        eligible_academic_levels=["Postgraduate"],
        keywords=["arts", "humanities", "research", "writing"],
        description="A grant for postgraduate students pursuing research in arts and humanities.",
        application_complexity_estimate="high",
        deadline=(datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"), # Due in 10 days
        award_amount="$2,000",
        url="http://example.com/artsgrant"
    )
    
    missing_info_scholarship = ScholarshipDataInput(
        scholarship_id="sch003",
        name="General Study Award",
        # min_gpa=None, # Missing GPA
        eligible_majors=[], # Open to all
        eligible_academic_levels=["Undergraduate", "Postgraduate"],
        keywords=["general", "study", "academic"],
        description="A general award for students.",
        # deadline=None, # Missing deadline
        award_amount=None, # Missing amount
        url="http://example.com/generalaward"
    )

    logger.info("--- Scoring Strong Match ---")
    scorer1 = ScholarshipConfidenceScorer(sample_user, strong_match_scholarship)
    result1 = scorer1.get_full_confidence_analysis()
    print(f"Scholarship: {result1.scholarship_name}")
    print(f"Confidence Score: {result1.confidence_score:.2f}%")
    print(f"Explanation: {result1.summary_explanation}")
    print(f"Matching Criteria: {result1.matching_criteria_details}")
    print(f"Potential Concerns: {result1.potential_concerns}")
    print(f"Suggested Actions: {result1.suggested_actions}\n")
    # print(f"Raw Details: {result1.raw_match_details}\n")


    logger.info("--- Scoring Weak Match ---")
    scorer2 = ScholarshipConfidenceScorer(sample_user, weak_match_scholarship)
    result2 = scorer2.get_full_confidence_analysis()
    print(f"Scholarship: {result2.scholarship_name}")
    print(f"Confidence Score: {result2.confidence_score:.2f}%")
    print(f"Explanation: {result2.summary_explanation}")
    print(f"Matching Criteria: {result2.matching_criteria_details}")
    print(f"Potential Concerns: {result2.potential_concerns}")
    print(f"Suggested Actions: {result2.suggested_actions}\n")

    logger.info("--- Scoring Missing Info Match ---")
    scorer3 = ScholarshipConfidenceScorer(sample_user, missing_info_scholarship)
    result3 = scorer3.get_full_confidence_analysis()
    print(f"Scholarship: {result3.scholarship_name}")
    print(f"Confidence Score: {result3.confidence_score:.2f}%")
    print(f"Explanation: {result3.summary_explanation}")
    print(f"Matching Criteria: {result3.matching_criteria_details}")
    print(f"Potential Concerns: {result3.potential_concerns}")
    print(f"Suggested Actions: {result3.suggested_actions}\n")

    # Test case: User with missing GPA
    sample_user_no_gpa = UserProfileInput(
        user_id="user_no_gpa",
        major="Biology",
        academic_level="Undergraduate"
    )
    scholarship_with_gpa_req = ScholarshipDataInput(
        scholarship_id="sch_gpa_req",
        name="Bio Scholars",
        min_gpa=3.2
    )
    logger.info("--- Scoring User with No GPA vs Scholarship with GPA Req ---")
    scorer4 = ScholarshipConfidenceScorer(sample_user_no_gpa, scholarship_with_gpa_req)
    result4 = scorer4.get_full_confidence_analysis()
    print(f"Scholarship: {result4.scholarship_name}")
    print(f"Confidence Score: {result4.confidence_score:.2f}%")
    print(f"Explanation: {result4.summary_explanation}")
    print(f"Potential Concerns: {result4.potential_concerns}")
    print(f"Suggested Actions: {result4.suggested_actions}\n")
