#!/usr/bin/env python3
"""
Stop hook: Capture session to buffer, suggest archivist if buffer is large.

Flow:
1. Read transcript from transcript_path
2. Write to buffer/ as JSON
3. Count buffer files
4. If > threshold, return message suggesting archivist

Receives JSON on stdin:
{
    "session_id": "...",
    "transcript_path": "/path/to/transcript.jsonl",
    "cwd": "/path/to/vault",
    "hook_event_name": "Stop"
}
"""
import json
import sys
from pathlib import Path
from datetime import datetime

BUFFER_THRESHOLD = 5  # Suggest archivist after this many buffer files


def find_vault_root(start_path: Path) -> Path | None:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".spellbook").exists():
            return current
        current = current.parent
    return None


def get_transcript_summary(transcript_path: str) -> dict:
    """Extract summary info from transcript."""
    try:
        with open(transcript_path, "r") as f:
            lines = f.readlines()

        message_count = 0
        tool_uses = set()

        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("role") in ("user", "assistant"):
                    message_count += 1
                # Count tool uses from content blocks
                content = entry.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "tool_use":
                            tool_uses.add(block.get("name", "unknown"))
            except json.JSONDecodeError:
                continue

        return {
            "message_count": message_count,
            "tool_uses": list(tool_uses),
            "line_count": len(lines),
        }
    except (FileNotFoundError, IOError):
        return {"message_count": 0, "tool_uses": [], "line_count": 0}


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return

    cwd = Path(hook_input.get("cwd", "."))
    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "unknown")

    # Find vault root
    vault = find_vault_root(cwd)
    if not vault:
        # Not in a vault, skip silently
        print(json.dumps({"continue": True}))
        return

    # Skip if no transcript
    if not transcript_path or not Path(transcript_path).exists():
        print(json.dumps({"continue": True}))
        return

    # Get transcript info
    summary = get_transcript_summary(transcript_path)

    # Skip trivial sessions (< 4 messages)
    if summary["message_count"] < 4:
        print(json.dumps({"continue": True}))
        return

    # Ensure buffer directory exists
    buffer_dir = vault / "buffer"
    buffer_dir.mkdir(exist_ok=True)

    # Write to buffer
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    buffer_file = buffer_dir / f"{ts}.json"

    buffer_entry = {
        "ts": ts,
        "session_id": session_id,
        "cwd": str(cwd),
        "transcript_path": transcript_path,
        "summary": summary,
    }

    # Copy transcript content
    try:
        with open(transcript_path, "r") as f:
            buffer_entry["transcript"] = f.read()
    except IOError:
        buffer_entry["transcript"] = ""

    with open(buffer_file, "w") as f:
        json.dump(buffer_entry, f, indent=2)

    # Count buffer files
    buffer_count = len(list(buffer_dir.glob("*.json")))

    # Build response
    response = {"continue": True}

    if buffer_count >= BUFFER_THRESHOLD:
        response["systemMessage"] = (
            f"[Spellbook] Buffer has {buffer_count} sessions pending. "
            f"Run the archivist agent to process them into the knowledge base."
        )

    print(json.dumps(response))


if __name__ == "__main__":
    main()
