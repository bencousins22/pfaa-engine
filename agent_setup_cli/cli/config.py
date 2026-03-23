import typer
app = typer.Typer()

@app.command()
def set(key: str, value: str):
    """Set configuration value"""
    print(f"Setting {key}={value}")
