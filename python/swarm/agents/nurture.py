from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class NewsletterAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Newsletter agent — weekly market updates for nurture sequences.
Output: {"subject": str, "sections": list, "market_data": dict}
"""

class ReEngageAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Re-engagement — dormant lead revival via personalised touchpoints.
Output: {"lead_id": str, "strategy": str, "message": str, "channel": str}
"""


NURTURE_AGENTS = [
    {"cls": NewsletterAgent, "id": "nur-newsletter", "role": "Newsletter agent — weekly market updates", "tools": ["file"]},
    {"cls": ReEngageAgent,   "id": "nur-re-engage",  "role": "Re-engagement — dormant lead revival",    "tools": ["file"]},
]
