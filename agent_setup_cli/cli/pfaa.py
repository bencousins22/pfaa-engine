"""
PFAA CLI Commands — Phase-Fluid Agent Architecture interface.

Exposes the PFAA engine through the Typer CLI:
    agent-setup pfaa status    — Show engine + memory status
    agent-setup pfaa tools     — List available tools
    agent-setup pfaa run       — Execute a tool
    agent-setup pfaa scatter   — Fan-out a tool across N inputs
    agent-setup pfaa bench     — Run benchmarks
    agent-setup pfaa memory    — Show memory status and learned patterns
    agent-setup pfaa ask       — Ask Claude via the bridge
    agent-setup pfaa learn     — Force a learning cycle
"""

from __future__ import annotations

import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

lazy import json

app = typer.Typer()
console = Console()


def _run(coro):
    """Run an async function from sync CLI context."""
    return asyncio.run(coro)


@app.command()
def status():
    """Show PFAA engine status — nucleus, memory, tools."""
    from agent_setup_cli.core.tools import ToolRegistry
    from agent_setup_cli.core.persistence import PersistentMemory

    # Import extended tools to register them
    import agent_setup_cli.core.tools_extended  # noqa: F401

    registry = ToolRegistry.get()
    mem = PersistentMemory()

    table = Table(title="PFAA Engine Status", show_lines=True)
    table.add_column("Component", style="cyan")
    table.add_column("Value", style="green")

    reg_status = registry.status()
    table.add_row("Tools Registered", str(reg_status["tools_registered"]))
    table.add_row("Tool Names", ", ".join(reg_status["tool_names"][:10]) + ("..." if len(reg_status["tool_names"]) > 10 else ""))

    mem_status = mem.status()
    table.add_row("L1 Episodes", str(mem_status["l1_episodes"]))
    table.add_row("L2 Patterns", str(mem_status["l2_patterns"]))
    table.add_row("L3 Strategies", str(mem_status["l3_strategies"]))
    table.add_row("L4 Learning Rate", f"{mem_status['l4_learning_rate']:.3f}")
    table.add_row("L5 Knowledge", str(mem_status["l5_knowledge"]))
    table.add_row("DB Path", mem_status["db_path"])
    table.add_row("DB Size", f"{mem_status['db_size_kb']} KB")

    console.print(table)
    mem.close()


@app.command()
def tools():
    """List all registered PFAA tools."""
    from agent_setup_cli.core.tools import ToolRegistry
    import agent_setup_cli.core.tools_extended  # noqa: F401

    registry = ToolRegistry.get()
    tool_list = registry.list_tools()

    table = Table(title=f"PFAA Tools ({len(tool_list)} registered)")
    table.add_column("Name", style="cyan")
    table.add_column("Phase", style="yellow")
    table.add_column("Isolated", style="red")
    table.add_column("Description", style="white")
    table.add_column("Capabilities", style="dim")

    for t in sorted(tool_list, key=lambda x: x.name):
        table.add_row(
            t.name,
            t.phase.name,
            "✓" if t.isolated else "",
            t.description,
            ", ".join(t.capabilities),
        )

    console.print(table)


@app.command()
def run(
    tool_name: str = typer.Argument(..., help="Tool to execute"),
    args: list[str] = typer.Argument(None, help="Tool arguments"),
):
    """Execute a single PFAA tool."""
    from agent_setup_cli.core.tools import ToolRegistry
    from agent_setup_cli.core.persistence import PersistentMemory
    import agent_setup_cli.core.tools_extended  # noqa: F401

    registry = ToolRegistry.get()
    mem = PersistentMemory()

    tool_entry = registry.get_tool(tool_name)
    if not tool_entry:
        console.print(f"[red]Unknown tool: {tool_name}[/red]")
        console.print("Available tools:")
        for t in registry.list_tools():
            console.print(f"  {t.name}")
        raise typer.Exit(1)

    spec, _ = tool_entry
    parsed_args = tuple(args) if args else ()

    async def _execute():
        result = await registry.execute(tool_name, *parsed_args)
        mem.record(result, tool_name, parsed_args)
        mem.close()
        return result

    result = _run(_execute())

    console.print(Panel(
        json.dumps(result.result, indent=2, default=str),
        title=f"[cyan]{tool_name}[/cyan] ({result.phase_used.name} phase, {result.elapsed_us}μs)",
        border_style="green" if isinstance(result.result, dict) and result.result.get("success") else "red",
    ))


@app.command()
def memory():
    """Show memory status and learned patterns."""
    from agent_setup_cli.core.persistence import PersistentMemory

    mem = PersistentMemory()
    dump = mem.dump()

    # Status
    console.print(Panel(
        json.dumps(mem.status(), indent=2),
        title="Memory Status",
        border_style="cyan",
    ))

    # Patterns
    if dump["patterns"]:
        table = Table(title="L2 — Learned Patterns")
        table.add_column("Tool", style="cyan")
        table.add_column("Avg μs", style="green")
        table.add_column("P95 μs", style="yellow")
        table.add_column("Best Phase", style="magenta")
        table.add_column("Success", style="green")
        table.add_column("Confidence", style="dim")

        for name, p in dump["patterns"].items():
            table.add_row(
                name,
                str(int(p["avg_us"])),
                str(int(p["p95_us"])),
                p["best_phase"],
                f"{p['success_rate']:.0%}",
                f"{p['confidence']:.2f}",
            )
        console.print(table)

    # Strategies
    if dump["strategies"]:
        table = Table(title="L3 — Phase Optimization Strategies")
        table.add_column("Tool", style="cyan")
        table.add_column("Default", style="red")
        table.add_column("Override", style="green")
        table.add_column("Speedup", style="yellow")

        for name, s in dump["strategies"].items():
            table.add_row(name, s["default"], s["override"] or "-", f"{s['speedup']:.1f}x")
        console.print(table)

    # Emergent
    if dump["emergent_knowledge"]:
        console.print("\n[bold magenta]L5 — Emergent Knowledge[/bold magenta]")
        for k in dump["emergent_knowledge"][:10]:
            console.print(f"  [{k['pattern']}] {k['description']} (conf={k['confidence']:.2f})")

    mem.close()


@app.command()
def learn():
    """Force a learning cycle across all memory layers."""
    from agent_setup_cli.core.persistence import PersistentMemory

    mem = PersistentMemory()
    console.print("[yellow]Running learning cycle...[/yellow]")
    mem.force_learn()
    console.print("[green]✓ Learning cycle complete. Memory persisted.[/green]")
    console.print(json.dumps(mem.status(), indent=2))
    mem.close()


@app.command()
def bench():
    """Run PFAA benchmark suite."""
    console.print("[bold cyan]Running PFAA benchmarks...[/bold cyan]\n")
    _run(_run_bench())


async def _run_bench():
    """Import and run benchmark."""
    from agent_setup_cli.core.benchmark import main as bench_main
    await bench_main()


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="Question for Claude"),
    model: str = typer.Option("sonnet", help="Claude model"),
):
    """Ask Claude a question via the PFAA bridge."""
    from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig
    from agent_setup_cli.core.persistence import PersistentMemory

    mem = PersistentMemory()
    bridge = ClaudeBridge(
        config=ClaudeConfig(model=model),
        memory=mem.memory,
    )

    if not bridge.is_available:
        console.print("[red]Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code[/red]")
        raise typer.Exit(1)

    async def _ask():
        with console.status("[yellow]Asking Claude...[/yellow]"):
            result = await bridge.ask(prompt)
        return result

    result = _run(_ask())

    if result.success:
        console.print(Panel(
            result.output,
            title=f"[cyan]Claude ({model})[/cyan] — {result.elapsed_ms:.0f}ms",
            border_style="green",
        ))
    else:
        console.print(f"[red]Error: {result.output}[/red]")

    mem.close()


@app.command()
def scatter(
    tool_name: str = typer.Argument(..., help="Tool to scatter"),
    inputs: list[str] = typer.Argument(..., help="Input values"),
):
    """Fan-out a tool across multiple inputs in parallel."""
    from agent_setup_cli.core.tools import ToolRegistry
    from agent_setup_cli.core.persistence import PersistentMemory
    import agent_setup_cli.core.tools_extended  # noqa: F401

    registry = ToolRegistry.get()
    mem = PersistentMemory()

    async def _scatter():
        results = await registry.execute_many([
            (tool_name, (inp,), {}) for inp in inputs
        ])
        for inp, result in zip(inputs, results):
            if isinstance(result, Exception):
                console.print(f"  [red]{inp}: {result}[/red]")
            else:
                mem.record(result, tool_name, (inp,))
                console.print(f"  [green]{inp}[/green]: {result.phase_used.name} {result.elapsed_us}μs")
        mem.close()
        return results

    console.print(f"[cyan]Scattering {tool_name} across {len(inputs)} inputs...[/cyan]")
    _run(_scatter())


@app.command(name="self-build")
def self_build(
    auto_apply: bool = typer.Option(False, "--apply", help="Auto-apply validated changes"),
    tools: list[str] = typer.Option(None, "--tool", help="Specific tool descriptions to generate"),
):
    """Run a self-improvement cycle — the engine builds itself."""
    from agent_setup_cli.core.self_build import SelfBuilder

    async def _build():
        builder = SelfBuilder()
        try:
            return await builder.build_self(
                tools_to_generate=list(tools) if tools else None,
                auto_apply=auto_apply,
            )
        finally:
            await builder.shutdown()

    result = _run(_build())

    console.print("\n[bold cyan]Self-Build Results:[/bold cyan]")
    console.print(json.dumps(
        {k: v for k, v in result.items() if k != "proposals"},
        indent=2, default=str,
    ))
