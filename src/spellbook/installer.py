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


def init_vault(vault_path: Path, name: str, knowledge_url: str | None = None) -> None:
    """Initialize a new Spellbook vault.

    Args:
        vault_path: Path where the vault will be created
        name: Name of the vault directory
        knowledge_url: Optional git URL to clone as the knowledge/ directory
    """
    console.print(f"\n[bold]Spellbook v{__version__}[/bold]\n")

    if (vault_path / SPELLBOOK_MARKER).exists():
        console.print(f"[red]Error:[/red] Vault already exists at {vault_path}")
        raise SystemExit(1)

    console.print(f"Vault path: [cyan]{vault_path}[/cyan]")
    console.print("Creating structure...")

    # Create vault root directory
    vault_path.mkdir(parents=True, exist_ok=True)

    # Handle knowledge directory - clone from URL or create empty structure
    if knowledge_url:
        console.print(f"Cloning knowledge repo from [cyan]{knowledge_url}[/cyan]...")
        knowledge_path = vault_path / "knowledge"
        result = subprocess.run(
            ["git", "clone", knowledge_url, str(knowledge_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Clean up on failure
            if vault_path.exists():
                shutil.rmtree(vault_path)
            console.print("[red]Error:[/red] Failed to clone knowledge repository")
            console.print(f"[red]{result.stderr.strip()}[/red]")
            raise SystemExit(1)
        console.print("  [green]\u2713[/green] knowledge/ (cloned)")

        # Ensure subdirectories exist in cloned repo
        for subdir in ["docs", "log", "buffer"]:
            subdir_path = knowledge_path / subdir
            subdir_path.mkdir(parents=True, exist_ok=True)

        # Clone repos from manifest if it exists
        repos_yaml = vault_path / "knowledge" / "repos.yaml"
        if repos_yaml.exists():
            with open(repos_yaml) as f:
                manifest = yaml.safe_load(f)

            repos_dir = vault_path / "repos"
            repos_dir.mkdir(exist_ok=True)

            # Support both old format (repos:) and new format (repositories:)
            repositories = manifest.get("repositories", manifest.get("repos", []))
            defaults = manifest.get("defaults", {})
            default_depth = defaults.get("depth")
            default_branch = defaults.get("branch", "main")

            for repo in repositories:
                url = repo["url"]
                # Support both old format (path:) and new format (name:)
                default_name = url.rstrip("/").split("/")[-1].replace(".git", "")
                name = repo.get("name") or repo.get("path") or default_name
                branch = repo.get("branch", default_branch)
                depth = repo.get("depth", default_depth)
                target = repos_dir / name

                if not target.exists():
                    console.print(f"Cloning [cyan]{url}[/cyan] into repos/{name}...")
                    clone_cmd = ["git", "clone"]
                    if depth:
                        clone_cmd.extend(["--depth", str(depth)])
                    if branch:
                        clone_cmd.extend(["--branch", branch])
                    clone_cmd.extend([url, str(target)])
                    result = subprocess.run(
                        clone_cmd,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        console.print(
                            f"[yellow]Warning:[/yellow] Failed to clone {url}",
                        )
                        console.print(f"  {result.stderr.strip()}")
    else:
        # Create empty knowledge structure
        for dir_path in ["knowledge/docs", "knowledge/log", "knowledge/buffer"]:
            full_path = vault_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            console.print(f"  [green]\u2713[/green] {dir_path}/")

    # Create other directories (repos/)
    for dir_path in VAULT_DIRS:
        if not dir_path.startswith("knowledge/"):
            full_path = vault_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            console.print(f"  [green]\u2713[/green] {dir_path}/")

    # Copy .claude/ directory from assets
    assets_path = get_assets_path()
    _copy_claude_dir(assets_path, vault_path)
    console.print("  [green]\u2713[/green] .claude/")

    # Copy .vscode/ directory from assets
    _copy_vscode_dir(assets_path, vault_path)
    console.print("  [green]\u2713[/green] .vscode/")

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

    # Delete .claude/ entirely and copy fresh
    assets_path = get_assets_path()
    _copy_claude_dir(assets_path, vault_path, clean_first=True)
    console.print("  [green]\u2713[/green] .claude/ (replaced)")

    # Delete .vscode/ entirely and copy fresh
    _copy_vscode_dir(assets_path, vault_path, clean_first=True)
    console.print("  [green]\u2713[/green] .vscode/ (replaced)")

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
    log_count = (
        len(list((knowledge_path / "log").rglob("*.md")))
        if (knowledge_path / "log").exists()
        else 0
    )
    buffer_count = (
        len(list((knowledge_path / "buffer").glob("*.txt")))
        if (knowledge_path / "buffer").exists()
        else 0
    )
    console.print(f"  - knowledge/log/ ({log_count} docs)")
    console.print(f"  - knowledge/buffer/ ({buffer_count} pending)")
    if (knowledge_path / "index.db").exists():
        console.print("  - knowledge/index.db")

    console.print("\n[green]Done![/green]")


def get_vault_status(vault_path: Path) -> None:
    """Display vault status and statistics."""
    import json
    import sqlite3
    from datetime import datetime, timedelta

    config = read_config(vault_path)
    if not config:
        console.print("[red]Error:[/red] Invalid vault")
        raise SystemExit(1)

    console.print(f"\n[bold]Spellbook Vault[/bold] v{__version__}\n")

    knowledge_path = vault_path / "knowledge"
    db_path = knowledge_path / "index.db"

    # =========================================================================
    # Knowledge Section
    # =========================================================================
    console.print("[bold]Knowledge:[/bold]")

    # Count buffer files
    buffer_path = knowledge_path / "buffer"
    buffer_count = len(list(buffer_path.glob("*.txt"))) if buffer_path.exists() else 0
    buffer_status = f"{buffer_count} files pending"
    if buffer_count > 0:
        buffer_status = f"[yellow]{buffer_count} files pending[/yellow]"
    console.print(f"  Buffer:     {buffer_status}")

    # Count log documents
    log_path = knowledge_path / "log"
    doc_count = len(list(log_path.rglob("*.md"))) if log_path.exists() else 0
    console.print(f"  Log:        {doc_count} documents")

    # Query entity counts by type
    entity_total = 0
    entity_by_type: dict[str, int] = {}
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC"
            )
            for row in cursor.fetchall():
                entity_by_type[row["type"]] = row["cnt"]
                entity_total += row["cnt"]
        except sqlite3.OperationalError:
            pass
        conn.close()

    if entity_total > 0:
        type_summary = ", ".join(f"{t}: {c}" for t, c in list(entity_by_type.items())[:4])
        if len(entity_by_type) > 4:
            type_summary += ", ..."
        console.print(f"  Entities:   {entity_total} ({type_summary})")
    else:
        console.print("  Entities:   0")

    console.print()

    # =========================================================================
    # Sessions Section
    # =========================================================================
    console.print("[bold]Sessions:[/bold]")

    session_count = 0
    total_input_7d = 0
    total_output_7d = 0
    has_sessions = False

    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Check if sessions table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            if cursor.fetchone():
                has_sessions = True

                # Total session count
                cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                session_count = cursor.fetchone()[0]

                # Token usage in last 7 days
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                cursor = conn.execute(
                    """
                    SELECT
                        COALESCE(SUM(total_input_tokens), 0) as input_sum,
                        COALESCE(SUM(total_output_tokens), 0) as output_sum
                    FROM sessions
                    WHERE started_at >= ?
                    """,
                    [week_ago],
                )
                row = cursor.fetchone()
                total_input_7d = row["input_sum"] or 0
                total_output_7d = row["output_sum"] or 0
        except sqlite3.OperationalError:
            pass
        conn.close()

    if has_sessions and session_count > 0:
        console.print(f"  Total:      {session_count} recorded")
        input_str = _format_token_count(total_input_7d)
        output_str = _format_token_count(total_output_7d)
        console.print(f"  Tokens:     {input_str} input, {output_str} output (last 7 days)")
    else:
        console.print("  [dim]No session data yet[/dim]")

    console.print()

    # =========================================================================
    # Repos Section
    # =========================================================================
    console.print("[bold]Repos:[/bold]")

    repos_yaml = knowledge_path / "repos.yaml"
    if repos_yaml.exists():
        try:
            repos_data = yaml.safe_load(repos_yaml.read_text())
            repos_list = repos_data.get("repositories", repos_data.get("repos", []))
            repo_count = len(repos_list) if repos_list else 0
            console.print(f"  Configured: {repo_count}")
        except Exception:
            console.print("  [yellow]Error reading repos.yaml[/yellow]")
    else:
        console.print("  [dim]Configured: 0 (add repos to knowledge/repos.yaml)[/dim]")

    console.print()

    # =========================================================================
    # Health Checks
    # =========================================================================
    console.print("[bold]Health:[/bold]")

    # Check stop hook in .claude/settings.json
    settings_path = vault_path / ".claude" / "settings.json"
    stop_hook_ok = False
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            hooks = settings.get("hooks", {})
            stop_hooks = hooks.get("Stop", [])
            # Check nested hook structure: Stop: [{hooks: [{type, command}]}]
            for entry in stop_hooks:
                if isinstance(entry, dict):
                    nested_hooks = entry.get("hooks", [])
                    for h in nested_hooks:
                        if isinstance(h, dict) and h.get("command"):
                            stop_hook_ok = True
                            break
                if stop_hook_ok:
                    break
        except Exception:
            pass

    if stop_hook_ok:
        console.print("  [green][OK][/green] Stop hook active")
    else:
        console.print("  [yellow][!][/yellow]  Stop hook not found in .claude/settings.json")

    # Check orchestrator injection file
    orchestrator_path = vault_path / ".claude" / "references" / "orchestrator.md"
    if orchestrator_path.exists():
        console.print("  [green][OK][/green] Orchestrator injection working")
    else:
        console.print("  [yellow][!][/yellow]  Orchestrator file missing (.claude/references/)")

    # Check index.db exists
    if db_path.exists():
        console.print("  [green][OK][/green] index.db synced")
    else:
        console.print("  [yellow][!][/yellow]  index.db missing (run 'sb rebuild')")

    # Warn if buffer has >2 files
    if buffer_count > 2:
        console.print(
            f"  [yellow][!][/yellow]  {buffer_count} buffer files > threshold (invoke Archivist)"
        )

    console.print()


def _format_token_count(n: int) -> str:
    """Format token count with K/M suffix for readability."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


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


def _copy_vscode_dir(assets_path: Path, vault_path: Path, clean_first: bool = False) -> None:
    """Copy .vscode/ directory from assets to vault.

    Args:
        assets_path: Path to bundled assets
        vault_path: Path to vault root
        clean_first: If True, delete existing .vscode/ before copying
    """
    src_vscode = assets_path / ".vscode"
    dest_vscode = vault_path / ".vscode"

    if not src_vscode.exists():
        return

    # Delete existing .vscode/ if requested
    if clean_first and dest_vscode.exists():
        shutil.rmtree(dest_vscode)

    # Copy entire .vscode/ directory
    shutil.copytree(src_vscode, dest_vscode, dirs_exist_ok=True)


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
    """Create or update knowledge/.gitignore with index.db entry."""
    knowledge_path = vault_path / "knowledge"
    knowledge_path.mkdir(parents=True, exist_ok=True)
    gitignore_path = knowledge_path / ".gitignore"

    # If .gitignore exists, ensure index.db is in it
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if "index.db" not in content:
            # Append index.db to existing .gitignore
            if not content.endswith("\n"):
                content += "\n"
            content += "index.db\n"
            gitignore_path.write_text(content)
    else:
        gitignore_path.write_text("index.db\n")
