from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class CompanyEnricher(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Company enricher — fetches ABN, ACN, financials, directors.
Output: {"company": str, "abn": str, "directors": list, "revenue_est": float}
"""

class ContactEnricher(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Contact enricher — finds decision maker emails + LinkedIn profiles.
Output: {"contacts": [{"name": str, "title": str, "email": str, "linkedin": str}]}
"""

class PropertyEnricher(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Property enricher — recent sales, zoning, council data.
Output: {"address": str, "zoning": str, "last_sale": dict, "council_plans": list}
"""


ENRICHMENT_AGENTS = [
    {"cls": CompanyEnricher,  "id": "enr-company",  "role": "Company enricher — ABN, financials, directors", "tools": ["fetch"]},
    {"cls": ContactEnricher,  "id": "enr-contact",  "role": "Contact enricher — emails, LinkedIn",           "tools": ["fetch"]},
    {"cls": PropertyEnricher, "id": "enr-property", "role": "Property enricher — sales, zoning, council",    "tools": ["fetch", "python"]},
]
