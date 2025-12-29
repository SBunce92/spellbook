"""Spellbook vault installation and management."""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console

from . import __version__
from .schema import SpellbookConfig

console = Console()

GITHUB_REPO = "https://github.com/sbunce92/spellbook.git"

SPELLBOOK_MARKER = ".spellbook"

# Directories to create in new vaults
VAULT_DIRS = [
    "knowledge/docs",
    "knowledge/log",
    "knowledge/buffer",
    "repos",
]


def get_assets_path() -> Path:
    """Get path to bundled assets."""
    return Path(__file__).parent / "assets"


def find_vault_root(start_path: Path) -> Path | None:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / SPELLBOOK_MARKER).exists():
            return current
        current = current.parent
    return None


def read_config(vault_path: Path) -> SpellbookConfig | None:
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

    # Copy .claude/ directory from assets
    assets_path = get_assets_path()
    _copy_claude_dir(assets_path, vault_path)
    console.print("  [green]\u2713[/green] .claude/")

    # Create knowledge/.gitignore
    _create_knowledge_gitignore(vault_path)
    console.print("  [green]\u2713[/green] knowledge/.gitignore")

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
                "uv",
                "tool",
                "install",
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
                "pip",
                "install",
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

    Fully deletes and rewrites: .claude/, .spellbook, CLAUDE.md
    Never touches: knowledge/buffer/, knowledge/log/, knowledge/index.db

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

    # Step 2: Delete and rewrite managed files
    console.print("Syncing vault files...")

    # Migrate old vault structure if needed
    _migrate_to_knowledge_structure(vault_path)

    # Delete .claude/ entirely and copy fresh
    assets_path = get_assets_path()
    _copy_claude_dir(assets_path, vault_path, clean_first=True)
    console.print("  [green]\u2713[/green] .claude/ (replaced)")

    # Ensure knowledge/.gitignore exists
    _create_knowledge_gitignore(vault_path)

    # Overwrite CLAUDE.md
    _update_claude_md(vault_path, config.vault_dir)
    console.print("  [green]\u2713[/green] CLAUDE.md (replaced)")

    # Update .spellbook config
    config.version = __version__
    config.last_updated = datetime.now()
    write_config(vault_path, config)
    console.print("  [green]\u2713[/green] .spellbook (updated)")

    # Report preserved files
    console.print("\nPreserved:")
    knowledge_path = vault_path / "knowledge"
    log_count = len(list((knowledge_path / "log").rglob("*.md"))) if (knowledge_path / "log").exists() else 0
    buffer_count = len(list((knowledge_path / "buffer").glob("*.txt"))) if (knowledge_path / "buffer").exists() else 0
    console.print(f"  - knowledge/log/ ({log_count} docs)")
    console.print(f"  - knowledge/buffer/ ({buffer_count} pending)")
    if (knowledge_path / "index.db").exists():
        console.print("  - knowledge/index.db")

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
    knowledge_path = vault_path / "knowledge"
    buffer_path = knowledge_path / "buffer"
    buffer_count = len(list(buffer_path.glob("*.txt"))) if buffer_path.exists() else 0
    console.print(f"Buffer:         {buffer_count} pending")

    # Count docs and entities
    log_path = knowledge_path / "log"
    doc_count = len(list(log_path.rglob("*.md"))) if log_path.exists() else 0

    db_path = knowledge_path / "index.db"
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


def _copy_claude_dir(assets_path: Path, vault_path: Path, clean_first: bool = False) -> None:
    """Copy .claude/ directory from assets to vault.

    Args:
        assets_path: Path to bundled assets
        vault_path: Path to vault root
        clean_first: If True, delete existing .claude/ before copying
    """
    src_claude = assets_path / ".claude"
    dest_claude = vault_path / ".claude"

    if not src_claude.exists():
        return

    # Delete existing .claude/ if requested
    if clean_first and dest_claude.exists():
        shutil.rmtree(dest_claude)

    # Copy entire .claude/ directory
    shutil.copytree(src_claude, dest_claude, dirs_exist_ok=True)

    # Make hook scripts executable
    hooks_dir = dest_claude / "hooks"
    if hooks_dir.exists():
        for hook_file in hooks_dir.iterdir():
            if hook_file.is_file():
                hook_file.chmod(hook_file.stat().st_mode | 0o111)


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


def _create_knowledge_gitignore(vault_path: Path) -> None:
    """Create knowledge/.gitignore with index.db entry."""
    knowledge_path = vault_path / "knowledge"
    knowledge_path.mkdir(parents=True, exist_ok=True)
    gitignore_path = knowledge_path / ".gitignore"
    gitignore_path.write_text("index.db\n")


def _migrate_to_knowledge_structure(vault_path: Path) -> None:
    """Migrate old vault structure to new knowledge/ structure.

    Old structure:
        buffer/, log/, docs/, index.db

    New structure:
        knowledge/buffer/, knowledge/log/, knowledge/docs/, knowledge/index.db
    """
    knowledge_path = vault_path / "knowledge"

    # Check if migration is needed (old structure exists but new doesn't)
    old_dirs = ["buffer", "log", "docs"]
    old_exists = any((vault_path / d).exists() for d in old_dirs)
    new_exists = (knowledge_path / "log").exists() or (knowledge_path / "buffer").exists()

    if not old_exists or new_exists:
        return  # No migration needed

    console.print("\n[yellow]Migrating to new knowledge/ structure...[/yellow]")

    # Create knowledge directory
    knowledge_path.mkdir(parents=True, exist_ok=True)

    # Move directories
    for dir_name in old_dirs:
        old_path = vault_path / dir_name
        new_path = knowledge_path / dir_name
        if old_path.exists() and not new_path.exists():
            shutil.move(str(old_path), str(new_path))
            console.print(f"  [green]\u2713[/green] Moved {dir_name}/ -> knowledge/{dir_name}/")

    # Move index.db
    old_db = vault_path / "index.db"
    new_db = knowledge_path / "index.db"
    if old_db.exists() and not new_db.exists():
        shutil.move(str(old_db), str(new_db))
        console.print("  [green]\u2713[/green] Moved index.db -> knowledge/index.db")

    # Create repos/ directory
    repos_path = vault_path / "repos"
    if not repos_path.exists():
        repos_path.mkdir(parents=True, exist_ok=True)
        console.print("  [green]\u2713[/green] Created repos/")

    console.print("[green]Migration complete![/green]\n")
