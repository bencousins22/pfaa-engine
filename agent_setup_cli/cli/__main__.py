import typer
from agent_setup_cli.cli import agent, terminal, config, plugin
from agent_setup_cli.cli.pfaa import app as pfaa_app
from agent_setup_cli.utils.logger import setup_logger

app = typer.Typer(help="Agent Setup Automation CLI — Phase-Fluid Architecture")

app.add_typer(agent.app, name="agent", help="Manage agents")
app.add_typer(terminal.app, name="terminal", help="Terminal settings")
app.add_typer(config.app, name="config", help="Configuration options")
app.add_typer(plugin.app, name="plugin", help="Manage plugins")
app.add_typer(pfaa_app, name="pfaa", help="Phase-Fluid Agent Architecture engine")

@app.callback()
def main(verbose: bool = False):
    """Agent Setup Automation"""
    setup_logger(verbose)

if __name__ == "__main__":
    app()
