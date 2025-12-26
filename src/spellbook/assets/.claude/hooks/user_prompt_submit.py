#!/usr/bin/env python3
"""
UserPromptSubmit hook: Inject orchestration context to main Claude.

Tests what we can inject:
1. systemMessage with agent roster + routing table
2. Vault state (buffer count, recent entities)
3. Tool restriction reminders

Input JSON:
{
    "session_id": "...",
    "user_prompt": "user's message",
    "cwd": "/path/to/vault",
    "hook_event_name": "UserPromptSubmit"
}

Output JSON:
{
    "continue": true,
    "systemMessage": "optional message to inject before Claude sees prompt"
}
"""
import json
import sys
from pathlib import Path
from typing import Optional


def find_vault_root(start_path: Path) -> Optional[Path]:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".spellbook").exists():
            return current
        current = current.parent
    return None


def get_vault_state(vault: Path) -> dict:
    """Get current vault state (buffer count, etc)."""
    buffer_dir = vault / "buffer"
    buffer_count = 0
    if buffer_dir.exists():
        buffer_count = len(list(buffer_dir.glob("*.txt")))

    return {
        "buffer_count": buffer_count,
    }


def load_orchestrator_context(vault: Path) -> str:
    """Load orchestrator context from markdown file."""
    context_file = vault / ".claude" / "context" / "orchestrator.md"

    if context_file.exists():
        try:
            return context_file.read_text()
        except Exception:
            # Fallback to empty if read fails
            return ""
    return ""


def build_orchestration_context(vault: Path, vault_state: dict) -> str:
    """Build injection for main Claude by combining markdown context + dynamic state."""

    buffer_count = vault_state.get("buffer_count", 0)

    # Load base context from markdown
    context = load_orchestrator_context(vault)

    if not context:
        # Fallback if markdown file missing
        context = "[Spellbook Vault Context]\n\nOrchestrator context not found."
    else:
        # Prepend header to markdown content
        context = "[Spellbook Vault Context]\n\n" + context

    # Add dynamic vault state if needed
    if buffer_count >= 3:
        context += f"\n\n---\n\n⚠️ VAULT STATE: {buffer_count} buffer files pending archival (invoke 📜 Archivist directly)\n"

    return context.strip()


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return

    cwd = Path(hook_input.get("cwd", "."))
    user_prompt = hook_input.get("user_prompt", "")

    # Find vault root
    vault = find_vault_root(cwd)
    if not vault:
        # Not in a spellbook vault, pass through
        print(json.dumps({"continue": True}))
        return

    # Skip trivial prompts (greetings, etc) - don't bloat with context
    prompt_lower = user_prompt.lower().strip()
    trivial_patterns = ["hi", "hello", "hey", "thanks", "thank you", "ok", "okay"]
    if prompt_lower in trivial_patterns or len(user_prompt.strip()) < 10:
        print(json.dumps({"continue": True}))
        return

    # Get vault state
    vault_state = get_vault_state(vault)

    # Build and inject orchestration context
    context = build_orchestration_context(vault, vault_state)

    response = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }
    }

    print(json.dumps(response))


if __name__ == "__main__":
    main()
