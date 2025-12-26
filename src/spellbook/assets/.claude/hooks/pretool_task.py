#!/usr/bin/env python3
"""
PreToolUse hook for Task tool: Inject load_references instructions for subagents.

When the Task tool is invoked, this hook checks if the target agent
has `load_references` defined in its YAML frontmatter. If so, it modifies
the tool input to prepend instructions to load those reference files
before proceeding with the task.

Input JSON (PreToolUse format):
{
    "session_id": "...",
    "tool_name": "Task",
    "tool_input": {
        "subagent_type": "agent name (e.g., '📜 Archivist')",
        "prompt": "original prompt from Task call"
    },
    "cwd": "/path/to/vault",
    "hook_event_name": "PreToolUse"
}

Output JSON (PreToolUse format):
{
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": {
            "prompt": "modified prompt with reference loading instructions"
        }
    }
}

If tool_name is not "Task", exits with no output (pass-through).
"""

import json
import re
import sys
from pathlib import Path


def find_vault_root(start_path: Path) -> Path | None:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".spellbook").exists():
            return current
        current = current.parent
    return None


def parse_yaml_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content.

    Simple parser that handles the frontmatter format used in agent definitions.
    Does not require PyYAML dependency.
    """
    # Check for frontmatter delimiters
    if not content.startswith("---"):
        return {}

    # Find the closing delimiter
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}

    frontmatter = content[3 : 3 + end_match.start()]
    result = {}

    # Parse key-value pairs, handling lists
    current_key = None
    current_list = None

    for line in frontmatter.split("\n"):
        line = line.rstrip()

        # Skip empty lines
        if not line.strip():
            continue

        # Check for list item (starts with spaces and -)
        if re.match(r"^\s+-\s+", line):
            if current_key and current_list is not None:
                # Extract the list item value
                item = re.sub(r"^\s+-\s+", "", line).strip()
                current_list.append(item)
            continue

        # Check for key: value or key:
        match = re.match(r"^(\w+):\s*(.*)", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()

            # If value is empty, this might be a list key
            if not value:
                current_key = key
                current_list = []
                result[key] = current_list
            else:
                # Simple key-value pair
                result[key] = value
                current_key = None
                current_list = None

    return result


def find_agent_file(vault: Path, subagent_type: str) -> Path | None:
    """Find the agent definition file for a given subagent type.

    Agent files are in .claude/agents/ with names derived from the agent type.
    For example, "📜 Archivist" -> archivist.md
    """
    agents_dir = vault / ".claude" / "agents"
    if not agents_dir.exists():
        return None

    # Normalize the subagent type to a filename
    # Remove emoji prefix and convert to lowercase
    # "📜 Archivist" -> "archivist"
    # "🐍 Backend" -> "backend"
    # "🤖 AI Engineer" -> "ai-engineer"
    name = subagent_type.strip()

    # Remove leading emoji (any non-ASCII chars at start)
    name = re.sub(r"^[^\x00-\x7F]+\s*", "", name)

    # Convert to lowercase and replace spaces with hyphens
    name = name.lower().strip().replace(" ", "-")

    agent_file = agents_dir / f"{name}.md"
    if agent_file.exists():
        return agent_file

    # Fallback: try to find by matching the 'name' field in frontmatter
    for md_file in agents_dir.glob("*.md"):
        try:
            content = md_file.read_text()
            frontmatter = parse_yaml_frontmatter(content)
            if frontmatter.get("name", "").strip() == subagent_type.strip():
                return md_file
        except Exception:
            continue

    return None


def get_load_references(vault: Path, subagent_type: str) -> list[str]:
    """Get the load_references list for an agent, if defined."""
    agent_file = find_agent_file(vault, subagent_type)
    if not agent_file:
        return []

    try:
        content = agent_file.read_text()
        frontmatter = parse_yaml_frontmatter(content)
        refs = frontmatter.get("load_references", [])
        if isinstance(refs, list):
            return refs
        return []
    except Exception:
        return []


def build_reference_prefix(references: list[str]) -> str:
    """Build the instruction prefix for loading references."""
    if not references:
        return ""

    lines = ["FIRST: Load your reference files before doing anything else:"]
    for ref in references:
        lines.append(f"  cat {ref}")
    lines.append("")
    lines.append("Then proceed with your task:")
    lines.append("")

    return "\n".join(lines)


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Invalid input, pass through silently
        sys.exit(0)

    # Early exit if not a Task tool call
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Task":
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    cwd = Path(hook_input.get("cwd", "."))
    subagent_type = tool_input.get("subagent_type", "")
    original_prompt = tool_input.get("prompt", "")

    # Find vault root
    vault = find_vault_root(cwd)
    if not vault:
        # Not in a spellbook vault, pass through
        sys.exit(0)

    # Get load_references for this agent
    references = get_load_references(vault, subagent_type)

    if not references:
        # No references to load, pass through
        sys.exit(0)

    # Build the modified prompt with reference loading instructions
    prefix = build_reference_prefix(references)
    modified_prompt = prefix + original_prompt

    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {
                **tool_input,  # Preserve all original fields (subagent_type, etc.)
                "prompt": modified_prompt
            }
        }
    }
    print(json.dumps(response))


if __name__ == "__main__":
    main()
