import typer
app = typer.Typer()

@app.command()
def install(name: str):
    """Install a plugin"""
    print(f"Installing plugin {name}...")
