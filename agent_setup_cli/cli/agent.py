import typer
from rich.console import Console
import os

lazy import tempfile
lazy import subprocess

app = typer.Typer()
console = Console()

@app.command()
def setup(name: str):
    """Setup a new agent automation system using Claude Code"""
    console.print(f"\n🤖 [bold cyan]Agent Setup Automation System[/bold cyan]")
    console.print(f"[bold green]Preparing configuration for target agent:[/bold green] {name}\n")
    
    from agent_setup_cli.ai.client import ClaudeCodeClient
    client = ClaudeCodeClient()
    if not client.is_available():
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY environment variable is not set.")
        console.print("Please export ANTHROPIC_API_KEY='your_key' to use Claude Code automation.")
        raise typer.Exit(1)
    
    with console.status("[yellow]Consulting Claude Code for the optimal setup script...[/yellow]", spinner="dots"):
        config = {
            "target": name,
            "objective": "Establish automated workflow process",
            "environment": "Linux Debian/Ubuntu",
            "tooling": ["xterm.js", "python3", "git"]
        }
        script_reply = client.setup_agent(name, config)
    
    console.print("\n[bold magenta]Claude generated setup strategy:[/bold magenta]")
    console.print(script_reply, highlight=True)
    
    if typer.confirm("\nDo you want to automatically execute this setup script now?"):
        script_content = script_reply
        if "```bash" in script_content:
            script_content = script_content.split("```bash")[1].split("```")[0].strip()
        elif "```sh" in script_content:
            script_content = script_content.split("```sh")[1].split("```")[0].strip()
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script_content)
            temp_path = f.name
            
        os.chmod(temp_path, 0o755)
        console.print("\n[bold yellow]Executing...[/bold yellow]")
        subprocess.run(["/bin/bash", temp_path])
        os.remove(temp_path)
        console.print("\n[bold green]✔ Agent Setup Completed successfully![/bold green]")
    else:
        console.print("\n[blue]ℹ Setup deferred by user.[/blue]")
