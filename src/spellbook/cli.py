"""Spellbook CLI - vault installer and admin commands."""

import click
from pathlib import Path
from rich.console import Console

from . import __version__
from .agents import list_agents

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="spellbook")
def cli():
    """Spellbook - Personal knowledge vault for Claude Code."""
    pass


@cli.command()
@click.argument("path", type=click.Path(), default=".")
@click.option("--name", prompt="Vault name", help="Name for this vault")
def init(path: str, name: str):
    """Initialize a new Spellbook vault."""
    from .installer import init_vault

    vault_path = Path(path).resolve()
    init_vault(vault_path, name)


@cli.command()
def update():
    """Update managed files to latest version."""
    from .installer import update_vault, find_vault_root

    vault_path = find_vault_root(Path.cwd())
    if not vault_path:
        console.print("[red]Error:[/red] Not in a Spellbook vault")
        raise SystemExit(1)

    update_vault(vault_path)


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
def agents():
    """List available agents."""
    list_agents(console)


if __name__ == "__main__":
    cli()
