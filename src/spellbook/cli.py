"""Spellbook CLI - vault installer and admin commands."""

from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="spellbook")
def cli():
    """Spellbook - Personal knowledge vault for Claude Code."""
    pass


@cli.command()
@click.option("--name", "-n", prompt="Vault directory", help="Directory name for this vault")
@click.option(
    "--path", "-p", type=click.Path(), default=None, help="Parent directory (defaults to cwd)"
)
def init(name: str, path: str | None):
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
    from .installer import find_vault_root, update_vault

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
    from .index import rebuild_index
    from .installer import find_vault_root

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    rebuild_index(vault_path)


@cli.command()
@click.option("--type", "-t", "entity_type", help="Filter by entity type")
def entities(entity_type: str | None):
    """List all entities with their aliases.

    Shows entities grouped by type, sorted alphabetically, with any
    aliases listed beneath each canonical name.
    """
    from .index import list_entities_with_aliases
    from .installer import find_vault_root

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
    from .index import (
        ensure_context_schema,
        has_context_tables,
    )
    from .installer import find_vault_root

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


def _format_duration(ms: int | None) -> str:
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


def _format_date(dt_str: str | None) -> str:
    """Format datetime string to date only."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return dt_str[:10] if len(dt_str) >= 10 else dt_str


def _show_sessions_tree(conn) -> None:
    """Show sessions in a clean table format."""
    from .index import get_sessions, get_subagent_calls_for_session

    sessions = get_sessions(conn, limit=50)

    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    console.print()

    # Create main sessions table
    table = Table(
        title="Context Usage",
        title_style="bold",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        padding=(0, 1),
    )

    table.add_column("Date", style="dim", width=10)
    table.add_column("Session", style="bold", width=12)
    table.add_column("Tokens", justify="right", width=10)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Agents", width=40)

    prev_date = None
    for s in sessions:
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
        date = _format_date(s.get("started_at"))

        # Get agent calls and aggregate by type
        calls = get_subagent_calls_for_session(conn, s["id"])
        agents_str = _format_agents_summary(calls)

        # Only show date if different from previous row
        display_date = date if date != prev_date else ""
        prev_date = date

        table.add_row(
            display_date,
            session_name,
            _format_tokens(session_tokens),
            duration_str,
            agents_str,
        )

    console.print(table)
    console.print()


def _format_agents_summary(calls: list[dict]) -> str:
    """Format agent calls into a compact summary string."""
    if not calls:
        return "[dim]-[/dim]"

    # Aggregate by agent type
    by_type: dict[str, dict] = {}
    for c in calls:
        atype = c.get("agent_type") or "Unknown"
        if atype not in by_type:
            by_type[atype] = {"count": 0, "tokens": 0}
        by_type[atype]["count"] += 1
        by_type[atype]["tokens"] += c.get("total_tokens") or 0

    # Sort by tokens descending
    sorted_types = sorted(by_type.items(), key=lambda x: x[1]["tokens"], reverse=True)

    # Build compact display: "Agent x2, Agent x1" format - show ALL agents
    parts = []
    for atype, stats in sorted_types:
        # Use agent type as-is (preserves emoji if present in name)
        # Only add emoji if not already present
        if not any(ord(c) > 127 for c in atype[:2] if atype):
            emoji = _get_agent_emoji(atype)
            display_name = f"{emoji} {atype}" if emoji else atype
        else:
            display_name = atype
        count = stats["count"]
        tokens = _format_tokens(stats["tokens"])
        if count > 1:
            parts.append(f"{display_name} [dim]x{count}[/dim] ({tokens})")
        else:
            parts.append(f"{display_name} ({tokens})")

    return ", ".join(parts)


def _get_agent_emoji(agent_type: str) -> str:
    """Get emoji for agent type."""
    emoji_map = {
        "Archivist": "\U0001f4dc",  # scroll
        "Librarian": "\U0001f4da",  # books
        "Researcher": "\U0001f50d",  # magnifying glass
        "Backend": "\U0001f40d",  # snake
        "Frontend": "\U0001f3a8",  # palette
        "Architect": "\U0001f3d7",  # building construction
        "Trader": "\U0001f4c8",  # chart increasing
        "AI Engineer": "\U0001f916",  # robot
        "Data Engineer": "\U0001f5c4",  # file cabinet
        "DevOps": "\U0001f6e0",  # hammer and wrench
        "General": "\U0001f464",  # bust in silhouette
    }
    return emoji_map.get(agent_type, "")


def _format_agent_name(agent_type: str) -> str:
    """Format agent type with emoji prefix."""
    # Map agent types to their emoji prefixes
    emoji_map = {
        "Archivist": "\U0001f4dc",  # scroll
        "Librarian": "\U0001f4da",  # books
        "Researcher": "\U0001f50d",  # magnifying glass
        "Backend": "\U0001f40d",  # snake
        "Frontend": "\U0001f3a8",  # palette
        "Architect": "\U0001f3d7",  # building construction
        "Trader": "\U0001f4c8",  # chart increasing
        "AI Engineer": "\U0001f916",  # robot
        "Data Engineer": "\U0001f5c4",  # file cabinet
        "DevOps": "\U0001f6e0",  # hammer and wrench
        "General": "\U0001f464",  # bust in silhouette
    }
    emoji = emoji_map.get(agent_type, "")
    if emoji:
        return f"{emoji} {agent_type}"
    return agent_type


if __name__ == "__main__":
    cli()
