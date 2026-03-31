import os
import subprocess
from typing import Dict, Any, List

lazy import anthropic

class ClaudeCodeClient:
    def __init__(self, api_key: str = None):
        _key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if _key:
            self.client = anthropic.Anthropic(api_key=_key)
        else:
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def analyze_cli_output(self, command: str, args: List[str]) -> Dict[str, Any]:
        """Run CLI command and analyze output with Claude"""
        if not self.is_available():
             return {"success": False, "error": "Claude API key not set"}
        try:
            result = subprocess.run([command] + args, 
                                   capture_output=True,
                                   text=True,
                                   timeout=30)
            
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": f"Analyze this CLI output and suggest configuration settings or improvements for our automated setup:\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                }]
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "claude_suggestions": response.content[0].text
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def setup_agent(self, agent_name: str, config: Dict[str, Any]) -> str:
        """Automated step using Claude to generate the best setup steps"""
        if not self.is_available():
             return "API key missing. Cannot generate setup instructions."
        
        prompt = f"I am setting up an agent named '{agent_name}'. Here is its configuration:\n{config}\n"
        prompt += "Generate a bash script that would automatically configure this service. Return ONLY the bash script in a markdown code block."
        
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
