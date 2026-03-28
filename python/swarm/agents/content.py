from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class ListingCopywriter(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Listing copywriter — MLS descriptions.
Output: {"headline": str, "description": str, "highlights": list}
"""

class SocialMediaAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Social media — LinkedIn/Instagram posts for property marketing.
Output: {"platform": str, "post": str, "hashtags": list}
"""

class ReportGenerator(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Client report generator — PDF-ready market reports.
Output: {"title": str, "sections": list, "charts_data": dict}
"""


CONTENT_AGENTS = [
    {"cls": ListingCopywriter, "id": "cnt-listing", "role": "Listing copywriter — MLS descriptions",   "tools": ["file"]},
    {"cls": SocialMediaAgent,  "id": "cnt-social",  "role": "Social media — LinkedIn/Instagram posts",  "tools": ["file"]},
    {"cls": ReportGenerator,   "id": "cnt-report",  "role": "Client report generator",                  "tools": ["file", "python"]},
]
