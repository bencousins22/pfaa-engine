from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class EmailComposer(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Email composer — personalised cold outreach sequences.
Output: {"subject": str, "body": str, "follow_up_days": int}
"""

class LinkedInComposer(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: LinkedIn message composer — connection requests and InMail.
Output: {"connection_note": str, "follow_up": str}
"""

class SchedulerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Follow-up scheduler — manages outreach cadence.
Output: {"schedule": [{"day": int, "channel": str, "action": str}]}
"""


OUTREACH_AGENTS = [
    {"cls": EmailComposer,    "id": "out-email",     "role": "Email composer — personalised outreach",        "tools": ["file"]},
    {"cls": LinkedInComposer, "id": "out-linkedin",  "role": "LinkedIn message composer",                     "tools": ["file"]},
    {"cls": SchedulerAgent,   "id": "out-scheduler", "role": "Follow-up scheduler — cadence management",      "tools": ["python"]},
]
