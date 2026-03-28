from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class LeadScannerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Find new CRE prospects. Scan MLS, LoopNet, CoStar, public records.
Output JSON: {"leads": [{"address": str, "type": str, "asking_price": float, "days_on_market": int}]}
"""

class ColdQualifierAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Score raw leads 0-100 against ICP criteria using Python 3.15.
Use match/case for scoring tiers: match score: case s if s>=80: ... case s if s>=60: ...
"""

class DedupAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Detect and merge duplicate leads. Use embedding similarity (cosine > 0.92 = duplicate).
Output: {"merged": int, "retained": list, "duplicates_removed": list}
"""


ACQUISITION_AGENTS = [
    {"cls": LeadScannerAgent,   "id": "acq-scanner",   "role": "Lead scanner — MLS, LoopNet, CoStar discovery",  "tools": ["fetch", "shell", "memory_recall"]},
    {"cls": ColdQualifierAgent, "id": "acq-qualifier",  "role": "Cold qualifier — ICP scoring 0-100",             "tools": ["python", "memory_recall"]},
    {"cls": DedupAgent,         "id": "acq-dedup",      "role": "Deduplication — merge duplicate leads",          "tools": ["file", "python"]},
]
