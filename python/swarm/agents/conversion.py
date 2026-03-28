from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class ProposalWriter(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Proposal writer — creates tailored CRE proposals.
Output: {"proposal_title": str, "sections": list, "call_to_action": str}
"""

class ObjectionHandler(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Objection handler — surfaces rebuttals from memory.
Output: {"objection": str, "rebuttal": str, "evidence": list, "confidence": float}
"""


CONVERSION_AGENTS = [
    {"cls": ProposalWriter,   "id": "con-proposal",  "role": "Proposal writer — tailored CRE proposals",  "tools": ["file"]},
    {"cls": ObjectionHandler, "id": "con-objection", "role": "Objection handler — rebuttals from memory", "tools": ["python"]},
]
