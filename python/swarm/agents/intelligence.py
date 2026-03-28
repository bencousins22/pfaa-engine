from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent, AgentContext


class MarketIntelAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Commercial Real Estate market intelligence.
Gather: cap rates by submarket, vacancy rates, absorption, recent comparable sales.
Output structured JSON: {"submarket": str, "cap_rate": float, "vacancy_pct": float, "recent_comps": list}
"""

class NewsMonitorAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Monitor zoning changes, council decisions, infrastructure announcements.
Flag anything that affects CRE values.
Output: {"alerts": [{"type": str, "location": str, "impact": str, "source": str}]}
"""

class PricingAnalystAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: CRE pricing analysis. Run comps, calculate price/sqft, cap rate spread.
Use Python 3.15 for calculations — match/case for property type routing.
Output: {"subject_property": str, "recommended_price": float, "comps": list, "confidence": float}
"""


INTELLIGENCE_AGENTS: list[dict] = [
    {"cls": MarketIntelAgent,    "id": "int-market",  "role": "Market intel — cap rates, vacancy, absorption",       "tools": ["fetch", "python", "memory_recall"]},
    {"cls": NewsMonitorAgent,    "id": "int-news",    "role": "News monitor — zoning changes, council decisions",    "tools": ["fetch", "memory_recall"]},
    {"cls": PricingAnalystAgent, "id": "int-pricing", "role": "Pricing analyst — comp analysis and price recs",      "tools": ["fetch", "python", "memory_recall"]},
]
