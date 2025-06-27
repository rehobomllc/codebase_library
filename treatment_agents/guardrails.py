# Treatment Navigator Guardrails - DISABLED
# All guardrails removed for simplified operation

import logging
from typing import List

logger = logging.getLogger(__name__)

# Empty guardrail lists - all guardrails disabled
TREATMENT_INPUT_GUARDRAILS: List = []
TREATMENT_OUTPUT_GUARDRAILS: List = []
CRISIS_FOCUSED_GUARDRAILS: List = []

logger.info("All guardrails disabled - operating in simplified mode") 