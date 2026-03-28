from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class FitScorerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: ICP fit scoring. Factors: asset class, geography, price band, zoning.
Output: {"lead_id": str, "fit_score": float, "factors": dict}
"""

class TimingScorerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Detect buy/sell timing signals. Price reductions, DOM trends, owner distress.
Output: {"urgency": "high"|"medium"|"low", "signals": list, "recommended_action": str}
"""

class ValueScorerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Estimate deal value and commission.
Output: {"estimated_value": float, "commission_pct": float, "estimated_commission": float}
"""


SCORING_AGENTS = [
    {"cls": FitScorerAgent,    "id": "scr-fit",    "role": "ICP fit scorer",              "tools": ["python", "memory_recall"]},
    {"cls": TimingScorerAgent,  "id": "scr-timing", "role": "Buy/sell timing detector",    "tools": ["python", "memory_recall"]},
    {"cls": ValueScorerAgent,   "id": "scr-value",  "role": "Deal value + commission est", "tools": ["python"]},
]
