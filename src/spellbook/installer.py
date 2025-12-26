"""Spellbook vault installation and management."""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from . import __version__
from .schema import SpellbookConfig

console = Console()

GITHUB_REPO = "https://github.com/sbunce92/spellbook.git"

SPELLBOOK_MARKER = ".spellbook"

# Directories to create in new vaults
VAULT_DIRS = [
    ".claude/agents",
    ".claude/hooks",
    ".claude/scripts",
    "log",
    "buffer",
]


def get_assets_path() -> Path:
    """Get path to bundled assets."""
    return Path(__file__).parent / "assets"


def find_vault_root(start_path: Path) -> Optional[Path]:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / SPELLBOOK_MARKER).exists():
            return current
        current = current.parent
    return None


def read_config(vault_path: Path) -> Optional[SpellbookConfig]:
    """Read vault configuration from .spellbook file."""
    config_path = vault_path / SPELLBOOK_MARKER
    if not config_path.exists():
        return None
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return SpellbookConfig(**data)


def write_config(vault_path: Path, config: SpellbookConfig) -> None:
    """Write vault configuration to .spellbook file."""
    config_path = vault_path / SPELLBOOK_MARKER
    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(mode="json"), f, default_flow_style=False)


def init_vault(vault_path: Path, name: str) -> None:
    """Initialize a new Spellbook vault."""
    console.print(f"\n[bold]Spellbook v{__version__}[/bold]\n")

    if (vault_path / SPELLBOOK_MARKER).exists():
        console.print(f"[red]Error:[/red] Vault already exists at {vault_path}")
        raise SystemExit(1)

    console.print(f"Vault path: [cyan]{vault_path}[/cyan]")
    console.print("Creating structure...")

    # Create directories
    vault_path.mkdir(parents=True, exist_ok=True)
    for dir_path in VAULT_DIRS:
        full_path = vault_path / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]\u2713[/green] {dir_path}/")

    # Copy managed assets
    assets_path = get_assets_path()
    if assets_path.exists():
        _copy_managed_assets(assets_path, vault_path)

    # Create CLAUDE.md from template
    _create_claude_md(vault_path, name)

    # Write config
    now = datetime.now()
    config = SpellbookConfig(
        version=__version__,
        vault_dir=name,
        created=now,
        last_updated=now,
    )
    write_config(vault_path, config)
    console.print(f"  [green]\u2713[/green] {SPELLBOOK_MARKER}")

    console.print("\n[green]Done![/green] Vault initialized.\n")
    console.print("Next steps:")
    console.print(f"  cd {vault_path}")
    console.print("  sb cc                     # Launch Claude in vault")
    console.print("  sb status                 # Check vault status")


def _self_upgrade() -> bool:
    """Upgrade spellbook from GitHub. Returns True if successful."""
    if shutil.which("uv"):
        console.print("[dim]Using uv to upgrade (forcing fresh install)...[/dim]")
        # Use --force --reinstall --refresh to ensure we always get the latest
        # --force: Force installation even if already installed
        # --reinstall: Reinstall all packages regardless of cache
        # --refresh: Refresh all cached data (re-fetch from git)
        result = subprocess.run(
            [
                "uv", "tool", "install",
                "--force",
                "--reinstall",
                "--refresh",
                f"git+{GITHUB_REPO}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        console.print(f"[red]uv install failed:[/red] {result.stderr.strip()}")
        return False

    if shutil.which("pip"):
        console.print("[dim]Falling back to pip...[/dim]")
        # Use --no-cache-dir to ensure fresh download
        result = subprocess.run(
            [
                "pip", "install",
                "--upgrade",
                "--no-cache-dir",
                f"git+{GITHUB_REPO}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        console.print(f"[red]pip install failed:[/red] {result.stderr.strip()}")
        return False

    console.print("[red]Error:[/red] Neither uv nor pip found")
    return False


def update_vault(vault_path: Path, fetch: bool = True) -> None:
    """Update managed files in existing vault.

    Args:
        vault_path: Path to the vault root
        fetch: If True, fetch latest from GitHub before syncing assets
    """
    config = read_config(vault_path)
    if not config:
        console.print("[red]Error:[/red] Invalid vault (no .spellbook found)")
        raise SystemExit(1)

    console.print(f"\n[bold]Spellbook[/bold] v{__version__}\n")

    # Step 1: Fetch and install latest from GitHub
    if fetch:
        console.print("Fetching latest from GitHub...")
        if _self_upgrade():
            console.print("[green]\u2713[/green] Package upgraded, restarting...\n")
            # Re-exec so new code runs the asset sync
            os.execv(
                sys.executable,
                [sys.executable, "-m", "spellbook.cli", "update", "--no-fetch"],
            )
            return  # Never reached

        # Upgrade failed - show error and exit
        console.print("\n[red]Error:[/red] Failed to fetch latest version from GitHub.")
        console.print("Please check your network connection and try again.")
        raise SystemExit(1)

    # Step 2: Copy assets to vault
    console.print("Syncing vault files...")

    # Copy managed assets (overwrites _claude/core/)
    assets_path = get_assets_path()
    if assets_path.exists():
        updated, new = _copy_managed_assets(assets_path, vault_path, report=True)
        for f in updated:
            console.print(f"  [green]\u2713[/green] {f} (updated)")
        for f in new:
            console.print(f"  [green]\u2713[/green] {f} (new)")

    # Update CLAUDE.md from template
    _update_claude_md(vault_path, config.vault_dir)
    console.print("  [green]\u2713[/green] CLAUDE.md (updated)")

    # Update config
    config.version = __version__
    config.last_updated = datetime.now()
    write_config(vault_path, config)

    # Report preserved files
    console.print("\nPreserved:")
    log_count = len(list((vault_path / "log").rglob("*.md")))
    console.print(f"  - log/* ({log_count} docs)")

    console.print("\n[green]Done![/green]")


def get_vault_status(vault_path: Path) -> None:
    """Display vault status and statistics."""
    config = read_config(vault_path)
    if not config:
        console.print("[red]Error:[/red] Invalid vault")
        raise SystemExit(1)

    console.print("\n[bold]Spellbook Vault Status[/bold]")
    console.print("\u2500" * 22)

    console.print(f"Version:        {config.version}")
    console.print(f"Directory:      {config.vault_dir}")
    console.print(f"Path:           {vault_path}")

    # Count buffer files
    buffer_path = vault_path / "buffer"
    buffer_count = len(list(buffer_path.glob("*.txt"))) if buffer_path.exists() else 0
    console.print(f"Buffer:         {buffer_count} pending")

    # Count docs and entities
    log_path = vault_path / "log"
    doc_count = len(list(log_path.rglob("*.md"))) if log_path.exists() else 0

    db_path = vault_path / "index.db"
    entity_count = 0
    if db_path.exists():
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM entities")
            entity_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    console.print(f"Index:          {entity_count} entities, {doc_count} docs")
    console.print(f"Created:        {config.created.strftime('%Y-%m-%d')}")
    console.print(f"Last updated:   {config.last_updated.strftime('%Y-%m-%d %H:%M')}")
    console.print()


def _copy_managed_assets(
    assets_path: Path, vault_path: Path, report: bool = False
) -> tuple[list[str], list[str]]:
    """Copy managed assets to vault. Returns (updated, new) file lists."""
    updated = []
    new = []

    # Copy .claude/ directory structure (agents, hooks, scripts)
    src_claude = assets_path / ".claude"
    if src_claude.exists():
        # Ensure .claude directory exists
        (vault_path / ".claude").mkdir(parents=True, exist_ok=True)

        # Copy settings.json (hook registration)
        src_settings = src_claude / "settings.json"
        if src_settings.exists():
            dest_settings = vault_path / ".claude" / "settings.json"
            was_existing = dest_settings.exists()
            shutil.copy2(src_settings, dest_settings)

            if report:
                if was_existing:
                    updated.append(".claude/settings.json")
                else:
                    new.append(".claude/settings.json")
            else:
                console.print("  [green]\u2713[/green] .claude/settings.json")

        # Copy subdirectories (agents, hooks, scripts, context)
        for subdir in ["agents", "hooks", "scripts", "context"]:
            src_dir = src_claude / subdir
            dest_dir = vault_path / ".claude" / subdir

            if not src_dir.exists():
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)

            for src_file in src_dir.iterdir():
                if src_file.is_file():
                    dest_file = dest_dir / src_file.name
                    was_existing = dest_file.exists()

                    shutil.copy2(src_file, dest_file)

                    # Make hook scripts executable
                    if subdir == "hooks":
                        dest_file.chmod(dest_file.stat().st_mode | 0o111)

                    if report:
                        rel_path = f".claude/{subdir}/{src_file.name}"
                        if was_existing:
                            updated.append(rel_path)
                        else:
                            new.append(rel_path)
                    else:
                        console.print(f"  [green]\u2713[/green] .claude/{subdir}/{src_file.name}")

    # Copy root-level config files (canonical_entities.yaml, etc.) to vault root
    root_configs = ["canonical_entities.yaml"]
    for config_name in root_configs:
        src_config = assets_path / config_name
        if src_config.exists():
            dest_config = vault_path / config_name
            # Only copy if doesn't exist (user may have customized)
            if not dest_config.exists():
                shutil.copy2(src_config, dest_config)
                if report:
                    new.append(config_name)
                else:
                    console.print(f"  [green]✓[/green] {config_name}")

    return updated, new


def _create_claude_md(vault_path: Path, name: str) -> None:
    """Create CLAUDE.md from template (only if it doesn't exist)."""
    claude_md_path = vault_path / "CLAUDE.md"
    if claude_md_path.exists():
        return

    _update_claude_md(vault_path, name)
    console.print("  [green]\u2713[/green] CLAUDE.md")


def _update_claude_md(vault_path: Path, name: str) -> None:
    """Update CLAUDE.md from template (always overwrites)."""
    claude_md_path = vault_path / "CLAUDE.md"

    template_path = get_assets_path() / "templates" / "CLAUDE.md.template"
    if template_path.exists():
        content = template_path.read_text()
        content = content.replace("{{vault_dir}}", name)
        content = content.replace("{{version}}", __version__)
    else:
        # Fallback if template doesn't exist
        content = f"""# {name}

Spellbook vault v{__version__}

## Quick Start

- `sb status` - Check vault status
- `sb archive` - Process buffer to log
- `sb recall <query>` - Search archive
- `sb quick <query>` - Fast lookup
"""

    claude_md_path.write_text(content)
