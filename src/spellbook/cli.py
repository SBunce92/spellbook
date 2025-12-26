"""Spellbook CLI - vault installer and admin commands."""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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
@click.option("--session", "-s", "session_id", help="Show details for specific session (ID or slug prefix)")
@click.option("--agent", "-a", "agent_type", help="Filter by agent type (e.g., Archivist, Backend)")
@click.option("--expensive", "-e", "expensive_n", type=int, default=None, is_flag=False, flag_value=10, help="Show top N most expensive exchanges (default 10)")
@click.option("--since", "since_str", help="Filter by recency (e.g., 7d, 1w, 2025-12-24)")
def context(
    session_id: Optional[str],
    agent_type: Optional[str],
    expensive_n: Optional[int],
    since_str: Optional[str],
):
    """Show context/token usage statistics.

    Examples:
        sb context                    # Recent sessions summary
        sb context --session abc123   # Details for session
        sb context --agent Archivist  # Filter by agent type
        sb context --expensive 10     # Top 10 most expensive calls
        sb context --since 7d         # Last 7 days only
    """
    from .installer import find_vault_root
    from .index import (
        ensure_context_schema,
        get_sessions,
        get_session_by_id,
        get_subagent_calls_for_session,
        get_subagent_calls_by_type,
        get_expensive_calls,
        get_agent_type_summary,
        has_context_tables,
    )

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    # Parse --since option
    since_date = _parse_since(since_str) if since_str else None

    # Ensure schema exists
    conn = ensure_context_schema(vault_path)

    if not has_context_tables(conn):
        console.print("[yellow]No context data found.[/yellow]")
        console.print("Context tracking starts automatically on next session end.")
        conn.close()
        return

    # Route to appropriate view
    if session_id:
        _show_session_detail(conn, session_id)
    elif agent_type:
        _show_agent_filter(conn, agent_type, since_date)
    elif expensive_n is not None:
        _show_expensive(conn, expensive_n, since_date)
    else:
        _show_sessions_summary(conn, since_date)

    conn.close()


def _parse_since(since_str: str) -> Optional[str]:
    """Parse --since argument to ISO date string."""
    # Try relative format: 7d, 1w, 30d
    match = re.match(r"^(\d+)([dwm])$", since_str.lower())
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            delta = timedelta(days=num)
        elif unit == "w":
            delta = timedelta(weeks=num)
        elif unit == "m":
            delta = timedelta(days=num * 30)
        else:
            delta = timedelta(days=num)
        since_date = datetime.now() - delta
        return since_date.isoformat()

    # Try ISO date format
    try:
        datetime.fromisoformat(since_str)
        return since_str
    except ValueError:
        console.print(f"[yellow]Warning:[/yellow] Could not parse --since '{since_str}', ignoring")
        return None


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


def _format_datetime(dt_str: Optional[str]) -> str:
    """Format datetime string to readable date."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return dt_str[:16] if len(dt_str) >= 16 else dt_str


def _format_date(dt_str: Optional[str]) -> str:
    """Format datetime string to date only."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return dt_str[:10] if len(dt_str) >= 10 else dt_str


def _show_sessions_summary(conn, since_date: Optional[str]) -> None:
    """Show recent sessions grouped by date."""
    from .index import get_sessions, get_subagent_calls_for_session

    sessions = get_sessions(conn, since=since_date, limit=50)

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

    # Calculate totals
    total_tokens = sum(
        (s.get("total_input_tokens") or 0) + (s.get("total_output_tokens") or 0)
        for s in sessions
    )
    total_sessions = len(sessions)

    title = "Context Usage"
    if since_date:
        title += f" (since {since_date[:10]})"
    else:
        title += " (recent)"

    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"Total: {total_sessions} sessions, {_format_tokens(total_tokens)} tokens\n")

    for date in sorted(by_date.keys(), reverse=True):
        day_sessions = by_date[date]
        day_tokens = sum(
            (s.get("total_input_tokens") or 0) + (s.get("total_output_tokens") or 0)
            for s in day_sessions
        )

        console.print(f"[cyan]{date}[/cyan] ({len(day_sessions)} sessions, {_format_tokens(day_tokens)} tokens)")

        for s in day_sessions:
            session_tokens = (s.get("total_input_tokens") or 0) + (s.get("total_output_tokens") or 0)
            # Get agent call count
            calls = get_subagent_calls_for_session(conn, s["id"])
            call_count = len(calls)

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
            console.print(f"  {session_name:<24} {_format_tokens(session_tokens):>8} tokens  {duration_str:>8}  {call_count:>3} agent calls")

        console.print()


def _show_session_detail(conn, session_id: str) -> None:
    """Show detailed view of a specific session."""
    from .index import get_session_by_id, get_subagent_calls_for_session

    session = get_session_by_id(conn, session_id)
    if not session:
        console.print(f"[red]Error:[/red] Session '{session_id}' not found")
        return

    calls = get_subagent_calls_for_session(conn, session["id"])

    # Header
    session_name = session.get("slug") or session["id"]
    short_id = session["id"][:8] if len(session["id"]) > 8 else session["id"]
    console.print(f"\n[bold]Session: {session_name}[/bold] ({short_id}...)")

    # Duration
    started = session.get("started_at")
    ended = session.get("ended_at")
    if started and ended:
        try:
            start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
            duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
            console.print(f"Duration: {_format_duration(duration_ms)} ({_format_datetime(started)} - {_format_datetime(ended).split()[-1] if ' ' in _format_datetime(ended) else _format_datetime(ended)})")
        except (ValueError, AttributeError):
            console.print(f"Started: {_format_datetime(started)}")
    else:
        console.print(f"Started: {_format_datetime(started)}")

    # Token summary
    input_tokens = session.get("total_input_tokens") or 0
    output_tokens = session.get("total_output_tokens") or 0
    total_tokens = input_tokens + output_tokens
    cache_read = session.get("total_cache_read") or 0

    console.print(f"Total: {_format_tokens(total_tokens)} tokens ({_format_tokens(input_tokens)} in / {_format_tokens(output_tokens)} out)")

    if total_tokens > 0 and cache_read > 0:
        cache_pct = (cache_read / total_tokens) * 100
        console.print(f"Cache: {cache_pct:.0f}% read ({_format_tokens(cache_read)} tokens from cache)")

    # Agent calls table
    if calls:
        console.print(f"\n[bold]Agent Calls ({len(calls)}):[/bold]")

        # Aggregate by agent type
        by_type: dict[str, dict] = {}
        for c in calls:
            atype = c.get("agent_type") or "Unknown"
            if atype not in by_type:
                by_type[atype] = {"calls": 0, "tokens": 0, "duration_ms": 0, "tools": 0}
            by_type[atype]["calls"] += 1
            by_type[atype]["tokens"] += c.get("total_tokens") or 0
            by_type[atype]["duration_ms"] += c.get("duration_ms") or 0
            by_type[atype]["tools"] += c.get("tool_use_count") or 0

        table = Table(show_header=True, header_style="bold")
        table.add_column("Agent", style="cyan")
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Tools", justify="right")

        for atype in sorted(by_type.keys(), key=lambda x: by_type[x]["tokens"], reverse=True):
            stats = by_type[atype]
            table.add_row(
                atype,
                str(stats["calls"]),
                _format_tokens(stats["tokens"]),
                _format_duration(stats["duration_ms"]),
                str(stats["tools"]),
            )

        console.print(table)
    else:
        console.print("\n[dim]No agent calls in this session.[/dim]")

    console.print()


def _show_agent_filter(conn, agent_type: str, since_date: Optional[str]) -> None:
    """Show calls filtered by agent type."""
    from .index import get_subagent_calls_by_type, get_agent_type_summary

    # Get summary stats for this agent type
    summaries = get_agent_type_summary(conn, since=since_date)
    agent_summary = next((s for s in summaries if s["agent_type"].lower() == agent_type.lower()), None)

    if not agent_summary:
        console.print(f"[yellow]No calls found for agent type '{agent_type}'[/yellow]")
        return

    title = f"{agent_type} Usage"
    if since_date:
        title += f" (since {since_date[:10]})"
    else:
        title += " (all time)"

    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"Total: {_format_tokens(agent_summary['total_tokens'] or 0)} tokens across {agent_summary['call_count']} calls")
    console.print(f"Avg per call: {_format_tokens(int(agent_summary['avg_tokens'] or 0))} tokens")
    console.print(f"Avg duration: {_format_duration(int(agent_summary['avg_duration_ms'] or 0))}")

    # Get detailed calls
    calls = get_subagent_calls_by_type(conn, agent_type, since=since_date, limit=20)

    if calls:
        console.print(f"\n[bold]Most expensive calls:[/bold]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Date", style="dim")
        table.add_column("Session")
        table.add_column("Tokens", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Description")

        # Sort by tokens descending
        calls_sorted = sorted(calls, key=lambda c: c.get("total_tokens") or 0, reverse=True)

        for c in calls_sorted[:10]:
            desc = c.get("description") or c.get("prompt_preview") or "-"
            if len(desc) > 30:
                desc = desc[:27] + "..."
            table.add_row(
                _format_date(c.get("started_at")),
                c.get("session_slug") or c.get("session_id", "")[:8],
                _format_tokens(c.get("total_tokens") or 0),
                _format_duration(c.get("duration_ms")),
                desc,
            )

        console.print(table)

    console.print()


def _show_expensive(conn, limit: int, since_date: Optional[str]) -> None:
    """Show top N most expensive subagent calls."""
    from .index import get_expensive_calls

    calls = get_expensive_calls(conn, limit=limit, since=since_date)

    if not calls:
        console.print("[yellow]No subagent calls found.[/yellow]")
        return

    title = f"Most Expensive Exchanges (top {limit})"
    if since_date:
        title += f" since {since_date[:10]}"

    console.print(f"\n[bold]{title}[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Date", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Description")

    for i, c in enumerate(calls, 1):
        desc = c.get("description") or c.get("prompt_preview") or "-"
        if len(desc) > 35:
            desc = desc[:32] + "..."
        table.add_row(
            str(i),
            _format_date(c.get("started_at")),
            c.get("agent_type") or "Unknown",
            _format_tokens(c.get("total_tokens") or 0),
            _format_duration(c.get("duration_ms")),
            desc,
        )

    console.print(table)
    console.print()


if __name__ == "__main__":
    cli()
