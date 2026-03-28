from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_base import PFAAAgent


class ComplianceChecker(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Compliance checker — real estate law and regulatory rules.
Output: {"compliant": bool, "issues": list, "recommendations": list}
"""

class CRMSyncAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: CRM sync — pushes results to HubSpot/Pipedrive.
Output: {"synced_records": int, "errors": list, "status": str}
"""

class AuditLoggerAgent(PFAAAgent):
    def build_system_prompt(self) -> str:
        return super().build_system_prompt() + """
SPECIALISATION: Audit logger — creates immutable activity trail.
Output: {"entries": int, "log_path": str, "hash_chain_valid": bool}
"""


OPERATIONS_AGENTS = [
    {"cls": ComplianceChecker, "id": "ops-compliance", "role": "Compliance checker — real estate law",      "tools": ["python", "fetch"]},
    {"cls": CRMSyncAgent,      "id": "ops-crm-sync",  "role": "CRM sync — HubSpot/Pipedrive push",        "tools": ["fetch", "python"]},
    {"cls": AuditLoggerAgent,  "id": "ops-audit",      "role": "Audit logger — immutable activity trail",   "tools": ["file"]},
]
