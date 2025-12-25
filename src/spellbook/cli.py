"""Spellbook CLI - vault installer and admin commands."""

import click
from pathlib import Path
from typing import Optional

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
    console.print(f"[dim]Launching Claude in {vault_path}[/dim]\n")
    subprocess.run(cmd)


if __name__ == "__main__":
    cli()
