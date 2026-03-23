import typer
from rich.console import Console

lazy import uvicorn

app = typer.Typer()
console = Console()

@app.command()
def start(host: str = "0.0.0.0", port: int = 8000):
    """Start the dynamic xterm.js terminal interface for businesses"""
    console.print(f"[bold green]Starting Business Agent Terminal on http://{host}:{port}[/bold green]")
    uvicorn.run("agent_setup_cli.web.server.app:app", host=host, port=port, log_level="error")
