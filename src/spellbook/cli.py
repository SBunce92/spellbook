"""Spellbook CLI - vault installer and admin commands."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from . import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="spellbook")
def cli():
    """Spellbook - Personal knowledge vault for Claude Code."""
    pass


@cli.command()
@click.option("--name", "-n", prompt="Vault directory", help="Directory name for this vault")
@click.option("--path", "-p", type=click.Path(), default=None, help="Parent directory (defaults to cwd)")
def init(name: str, path: Optional[str]):
    """Initialize a new Spellbook vault.

    Creates a directory with the vault name and initializes inside it.
    """
    from .installer import init_vault

    parent = Path(path).resolve() if path else Path.cwd()
    vault_path = parent / name
    init_vault(vault_path, name)


@cli.command()
@click.option("--no-fetch", is_flag=True, hidden=True, help="Skip package upgrade (internal)")
def update(no_fetch: bool):
    """Update managed files to latest version.

    Fetches the latest version from GitHub and syncs vault files.
    """
    from .installer import update_vault, find_vault_root

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    update_vault(vault_path, fetch=not no_fetch)


@cli.command()
def status():
    """Show vault status and statistics."""
    from .installer import find_vault_root, get_vault_status

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    get_vault_status(vault_path)


@cli.command()
def rebuild():
    """Rebuild index.db from log documents."""
    from .installer import find_vault_root
    from .index import rebuild_index

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    rebuild_index(vault_path)


@cli.command()
@click.option("--type", "-t", "entity_type", help="Filter by entity type")
def entities(entity_type: Optional[str]):
    """List all entities with their aliases.

    Shows entities grouped by type, sorted alphabetically, with any
    aliases listed beneath each canonical name.
    """
    from .installer import find_vault_root
    from .index import list_entities_with_aliases

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    list_entities_with_aliases(vault_path, entity_type)


@cli.command()
@click.option("--resume", "-r", is_flag=True, help="Resume last session")
@click.option("--continue", "-c", "cont", is_flag=True, help="Continue last session")
@click.option("--safe", "-s", is_flag=True, help="Disable --dangerously-skip-permissions")
@click.argument("args", nargs=-1)
def cc(resume: bool, cont: bool, safe: bool, args: tuple):
    """Launch Claude Code in the vault (skips permissions by default)."""
    import os
    import subprocess
    from .installer import find_vault_root

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    cmd = ["claude"]
    if not safe:
        cmd.append("--dangerously-skip-permissions")
    if resume:
        cmd.append("--resume")
    if cont:
        cmd.append("--continue")
    cmd.extend(args)

    os.chdir(vault_path)

    # Display spellbook banner with details
    console.print(f"\n📖 [bold magenta]Spellbook[/bold magenta] [dim]v{__version__}[/dim]")
    console.print(f"[dim]   vault:[/dim]  {vault_path}")
    console.print(f"[dim]   cmd:[/dim]    {' '.join(cmd)}")
    console.print()

    subprocess.run(cmd)


@cli.command()
def context():
    """Show context/token usage in a tree view.

    Displays sessions grouped by date with agents nested underneath.
    """
    from .installer import find_vault_root
    from .index import (
        ensure_context_schema,
        get_sessions,
        get_subagent_calls_for_session,
        has_context_tables,
    )

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    # Ensure schema exists
    conn = ensure_context_schema(vault_path)

    if not has_context_tables(conn):
        console.print("[yellow]No context data found.[/yellow]")
        console.print("Context tracking starts automatically on next session end.")
        conn.close()
        return

    _show_sessions_tree(conn)

    conn.close()


def _format_tokens(n: int) -> str:
    """Format token count with K suffix for readability."""
    if n is None:
        return "0"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _format_duration(ms: Optional[int]) -> str:
    """Format duration in ms to human-readable."""
    if ms is None or ms == 0:
        return "-"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _format_date(dt_str: Optional[str]) -> str:
    """Format datetime string to date only."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return dt_str[:10] if len(dt_str) >= 10 else dt_str


def _show_sessions_tree(conn) -> None:
    """Show sessions in tree view with agents nested underneath."""
    from .index import get_sessions, get_subagent_calls_for_session

    sessions = get_sessions(conn, limit=50)

    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for s in sessions:
        date = _format_date(s.get("started_at"))
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(s)

    console.print(f"\n[bold]Context Usage[/bold]\n")

    for date in sorted(by_date.keys(), reverse=True):
        day_sessions = by_date[date]

        console.print(f"[cyan]{date}[/cyan]")

        for s in day_sessions:
            session_tokens = (s.get("total_input_tokens") or 0) + (s.get("total_output_tokens") or 0)

            # Calculate duration
            started = s.get("started_at")
            ended = s.get("ended_at")
            duration_str = "-"
            if started and ended:
                try:
                    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                    duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
                    duration_str = _format_duration(duration_ms)
                except (ValueError, AttributeError):
                    pass

            session_name = s.get("slug") or s["id"][:8]
            console.print(f"  {session_name:<16} {_format_tokens(session_tokens):>8} tokens  {duration_str:>8}")

            # Get agent calls and aggregate by type
            calls = get_subagent_calls_for_session(conn, s["id"])
            if not calls:
                console.print(f"    [dim](no agents)[/dim]")
            else:
                # Aggregate by agent type
                by_type: dict[str, dict] = {}
                for c in calls:
                    atype = c.get("agent_type") or "Unknown"
                    if atype not in by_type:
                        by_type[atype] = {"count": 0, "tokens": 0, "duration_ms": 0}
                    by_type[atype]["count"] += 1
                    by_type[atype]["tokens"] += c.get("total_tokens") or 0
                    by_type[atype]["duration_ms"] += c.get("duration_ms") or 0

                # Sort by tokens descending, show top agents
                sorted_types = sorted(by_type.items(), key=lambda x: x[1]["tokens"], reverse=True)
                shown = 0
                for atype, stats in sorted_types:
                    if shown >= 3:
                        remaining = len(sorted_types) - shown
                        if remaining > 0:
                            console.print(f"    [dim]...[/dim]")
                        break
                    # Format with emoji prefix if agent type matches known agents
                    agent_display = _format_agent_name(atype)
                    tokens_str = _format_tokens(stats["tokens"])
                    duration_str = _format_duration(stats["duration_ms"])
                    count = stats["count"]
                    console.print(f"    {agent_display:<20} {tokens_str:>8} tokens  {duration_str:>8}    [dim]x{count}[/dim]")
                    shown += 1

            console.print()


def _format_agent_name(agent_type: str) -> str:
    """Format agent type with emoji prefix."""
    # Map agent types to their emoji prefixes
    emoji_map = {
        "Archivist": "\U0001F4DC",      # scroll
        "Librarian": "\U0001F4DA",      # books
        "Researcher": "\U0001F50D",     # magnifying glass
        "Backend": "\U0001F40D",        # snake
        "Frontend": "\U0001F3A8",       # palette
        "Architect": "\U0001F3D7",      # building construction
        "Trader": "\U0001F4C8",         # chart increasing
        "AI Engineer": "\U0001F916",    # robot
        "Data Engineer": "\U0001F5C4",  # file cabinet
        "DevOps": "\U0001F6E0",         # hammer and wrench
        "General": "\U0001F464",        # bust in silhouette
    }
    emoji = emoji_map.get(agent_type, "")
    if emoji:
        return f"{emoji} {agent_type}"
    return agent_type


if __name__ == "__main__":
    cli()
