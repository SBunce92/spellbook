#!/usr/bin/env python3
"""
Stop hook: Capture exchange delta to buffer as slim text.

Flow:
1. Load last captured timestamp from buffer/.state
2. Extract only NEW messages (after last timestamp)
3. Write delta as plain text to buffer/{timestamp}.txt
4. Update .state with new timestamp

Buffer format is minimal:
    USER: message text

    AGENT: response text

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
from typing import Optional

BUFFER_THRESHOLD = 5  # Suggest archivist after this many buffer files


def find_vault_root(start_path: Path) -> Optional[Path]:
    """Find vault root by looking for .spellbook marker."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".spellbook").exists():
            return current
        current = current.parent
    return None


def load_state(buffer_dir: Path) -> dict:
    """Load capture state."""
    state_file = buffer_dir / ".state"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_captured_ts": None}


def save_state(buffer_dir: Path, state: dict):
    """Save capture state."""
    state_file = buffer_dir / ".state"
    state_file.write_text(json.dumps(state, indent=2))


def extract_text_content(content) -> str:
    """Extract just the text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                # Skip tool_use, tool_result - just want human-readable text
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    return ""


def extract_delta(transcript_path: str, last_ts: Optional[str]) -> tuple[str, str, int]:
    """
    Extract messages newer than last_ts as simple text.
    Returns (text_content, latest_ts, message_count).
    Format: "USER: ...\n\nAGENT: ...\n\n..."
    """
    lines = []
    latest_ts = last_ts
    message_count = 0

    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_ts = entry.get("timestamp")

                    if not entry_ts:
                        continue
                    if last_ts and entry_ts <= last_ts:
                        continue

                    if not latest_ts or entry_ts > latest_ts:
                        latest_ts = entry_ts

                    # Handle Claude Code transcript format
                    entry_type = entry.get("type", "")
                    if entry_type not in ("user", "assistant"):
                        continue

                    message = entry.get("message", {})
                    content = message.get("content", [])
                    text = extract_text_content(content)

                    if not text.strip():
                        continue

                    # Simple format: USER or AGENT prefix
                    prefix = "USER" if entry_type == "user" else "AGENT"
                    lines.append(f"{prefix}: {text.strip()}")
                    message_count += 1

                except json.JSONDecodeError:
                    continue
    except (FileNotFoundError, IOError):
        pass

    return "\n\n".join(lines), latest_ts, message_count


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return

    cwd = Path(hook_input.get("cwd", "."))
    transcript_path = hook_input.get("transcript_path", "")

    # Find vault root
    vault = find_vault_root(cwd)
    if not vault:
        print(json.dumps({"continue": True}))
        return

    # Skip if no transcript
    if not transcript_path or not Path(transcript_path).exists():
        print(json.dumps({"continue": True}))
        return

    # Ensure buffer directory exists
    buffer_dir = vault / "buffer"
    buffer_dir.mkdir(exist_ok=True)

    # Load state
    state = load_state(buffer_dir)

    # Extract delta as simple text
    text_content, latest_ts, message_count = extract_delta(
        transcript_path,
        state.get("last_captured_ts")
    )

    # Skip if no new content or trivial (< 2 messages)
    if not text_content or message_count < 2:
        print(json.dumps({"continue": True}))
        return

    # Write delta as plain text file
    ts_filename = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    buffer_file = buffer_dir / f"{ts_filename}.txt"
    buffer_file.write_text(text_content)

    # Update state
    state["last_captured_ts"] = latest_ts
    save_state(buffer_dir, state)

    # Count buffer files and optionally remind about archiving
    buffer_count = len(list(buffer_dir.glob("*.txt")))

    response = {"continue": True}
    if buffer_count >= BUFFER_THRESHOLD:
        response["systemMessage"] = (
            f"[Spellbook] {buffer_count} buffer files pending. "
            f"Consider archiving via General → Archivist."
        )

    print(json.dumps(response))


if __name__ == "__main__":
    main()
