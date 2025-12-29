#!/usr/bin/env python3
"""
Stop hook: Capture exchange delta to buffer and track context usage.

Flow:
1. Load last captured timestamp from buffer/.state
2. Extract only NEW messages (after last timestamp)
3. Write delta as plain text to buffer/{timestamp}.txt
4. Extract usage data and store in index.db
5. Update .state with new timestamp

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
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BUFFER_THRESHOLD = 5  # Suggest archivist after this many buffer files


def find_vault_root(start_path: Path) -> Path | None:
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
        except (OSError, json.JSONDecodeError):
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


def extract_delta(transcript_path: str, last_ts: str | None) -> tuple[str, str, int]:
    """
    Extract messages newer than last_ts as simple text.
    Returns (text_content, latest_ts, message_count).
    Format: "USER: ...\n\nAGENT: ...\n\n..."
    """
    lines = []
    latest_ts = last_ts
    message_count = 0

    try:
        with open(transcript_path) as f:
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
    except (OSError, FileNotFoundError):
        pass

    return "\n\n".join(lines), latest_ts, message_count


# =============================================================================
# Context/Usage Tracking
# =============================================================================

CONTEXT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    vault_path TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cache_creation INTEGER DEFAULT 0,
    total_cache_read INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    slug TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_vault ON sessions(vault_path);

CREATE TABLE IF NOT EXISTS subagent_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    description TEXT,
    prompt_preview TEXT,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    duration_ms INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_creation INTEGER DEFAULT 0,
    cache_read INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    tool_use_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_subagent_session ON subagent_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_type ON subagent_calls(agent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_started ON subagent_calls(started_at DESC);
"""


def extract_usage_data(transcript_path: str, session_id: str) -> dict:
    """
    Extract token usage from transcript JSONL.

    Returns dict with:
    - session_id, started_at, ended_at
    - total_input, total_output, total_cache_creation, total_cache_read
    - total_messages
    - subagent_calls: list of subagent usage dicts
    """
    usage = {
        "session_id": session_id,
        "started_at": None,
        "ended_at": None,
        "total_input": 0,
        "total_output": 0,
        "total_cache_creation": 0,
        "total_cache_read": 0,
        "total_messages": 0,
        "subagent_calls": [],
    }

    # Track Task tool invocations to match inputs with results
    pending_tasks: dict[str, dict] = {}  # tool_use_id -> task input info

    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_ts = entry.get("timestamp")

                    # Track session timestamps
                    if entry_ts:
                        if not usage["started_at"] or entry_ts < usage["started_at"]:
                            usage["started_at"] = entry_ts
                        if not usage["ended_at"] or entry_ts > usage["ended_at"]:
                            usage["ended_at"] = entry_ts

                    # Skip subagent messages (isSidechain=True) - we get aggregates from toolUseResult
                    if entry.get("isSidechain"):
                        continue

                    entry_type = entry.get("type", "")
                    message = entry.get("message", {})

                    # Extract message-level usage from assistant messages
                    if entry_type == "assistant":
                        msg_usage = message.get("usage", {})
                        usage["total_input"] += msg_usage.get("input_tokens", 0)
                        usage["total_output"] += msg_usage.get("output_tokens", 0)
                        usage["total_cache_creation"] += msg_usage.get(
                            "cache_creation_input_tokens", 0
                        )
                        usage["total_cache_read"] += msg_usage.get("cache_read_input_tokens", 0)
                        usage["total_messages"] += 1

                        # Look for Task tool_use blocks to track pending tasks
                        content = message.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "tool_use"
                                    and block.get("name") == "Task"
                                ):
                                    tool_use_id = block.get("id")
                                    task_input = block.get("input", {})
                                    if tool_use_id:
                                        pending_tasks[tool_use_id] = {
                                            "subagent_type": task_input.get(
                                                "subagent_type", "Unknown"
                                            ),
                                            "description": task_input.get("description"),
                                            "prompt": task_input.get("prompt", ""),
                                            "started_at": entry_ts,
                                        }

                    # Extract Task tool results (subagent summaries)
                    # NOTE: toolUseResult is at entry level, not block level
                    if entry_type == "user":
                        content = message.get("content", [])
                        # toolUseResult is at entry level (top of JSONL line)
                        tool_result = entry.get("toolUseResult", {})
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_result":
                                    tool_use_id = block.get("tool_use_id")

                                    # Check if this is a Task result with agentId
                                    if "agentId" in tool_result:
                                        # Get task input info if available
                                        task_info = pending_tasks.pop(tool_use_id, {})
                                        result_usage = tool_result.get("usage", {})

                                        # Strip emoji prefix from agent type for cleaner storage
                                        agent_type = task_info.get("subagent_type", "Unknown")
                                        # Remove leading emoji + space if present
                                        # Handle both actual Unicode emojis and escaped forms like \\U0001F916
                                        agent_type = re.sub(r"^\\U[0-9A-Fa-f]+\s*", "", agent_type)
                                        agent_type = re.sub(r"^[^\w\s]+\s*", "", agent_type)

                                        subagent_call = {
                                            "agent_id": tool_result.get("agentId", ""),
                                            "agent_type": agent_type,
                                            "description": task_info.get("description"),
                                            "prompt_preview": (
                                                task_info.get("prompt", "")[:200]
                                                if task_info.get("prompt")
                                                else None
                                            ),
                                            "started_at": task_info.get("started_at"),
                                            "ended_at": entry_ts,
                                            "duration_ms": tool_result.get("totalDurationMs"),
                                            "total_tokens": tool_result.get("totalTokens", 0),
                                            "tool_use_count": tool_result.get(
                                                "totalToolUseCount", 0
                                            ),
                                            "input_tokens": result_usage.get("input_tokens", 0),
                                            "output_tokens": result_usage.get("output_tokens", 0),
                                            "cache_creation": result_usage.get(
                                                "cache_creation_input_tokens", 0
                                            ),
                                            "cache_read": result_usage.get(
                                                "cache_read_input_tokens", 0
                                            ),
                                            "status": tool_result.get("status", "completed"),
                                        }
                                        usage["subagent_calls"].append(subagent_call)

                except json.JSONDecodeError:
                    continue

    except (OSError, FileNotFoundError):
        pass

    return usage


def store_usage(vault_path: Path, session_id: str, usage: dict) -> None:
    """Store usage data in knowledge/index.db."""
    db_path = vault_path / "knowledge" / "index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    try:
        # Ensure context schema exists
        conn.executescript(CONTEXT_SCHEMA_SQL)

        # Upsert session
        conn.execute(
            """
            INSERT INTO sessions (
                id, vault_path, started_at, ended_at,
                total_input_tokens, total_output_tokens,
                total_cache_creation, total_cache_read,
                total_messages, slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                ended_at = excluded.ended_at,
                total_input_tokens = excluded.total_input_tokens,
                total_output_tokens = excluded.total_output_tokens,
                total_cache_creation = excluded.total_cache_creation,
                total_cache_read = excluded.total_cache_read,
                total_messages = excluded.total_messages
            """,
            [
                session_id,
                str(vault_path),
                usage.get("started_at"),
                usage.get("ended_at"),
                usage.get("total_input", 0),
                usage.get("total_output", 0),
                usage.get("total_cache_creation", 0),
                usage.get("total_cache_read", 0),
                usage.get("total_messages", 0),
                None,  # slug - could be derived from session name later
            ],
        )

        # Delete existing subagent calls for this session (for idempotent reprocessing)
        conn.execute("DELETE FROM subagent_calls WHERE session_id = ?", [session_id])

        # Insert subagent calls
        for call in usage.get("subagent_calls", []):
            conn.execute(
                """
                INSERT INTO subagent_calls (
                    session_id, agent_id, agent_type, description, prompt_preview,
                    started_at, ended_at, duration_ms,
                    input_tokens, output_tokens, cache_creation, cache_read,
                    total_tokens, tool_use_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    session_id,
                    call.get("agent_id", ""),
                    call.get("agent_type", "Unknown"),
                    call.get("description"),
                    call.get("prompt_preview"),
                    call.get("started_at"),
                    call.get("ended_at"),
                    call.get("duration_ms"),
                    call.get("input_tokens", 0),
                    call.get("output_tokens", 0),
                    call.get("cache_creation", 0),
                    call.get("cache_read", 0),
                    call.get("total_tokens", 0),
                    call.get("tool_use_count", 0),
                    call.get("status", "completed"),
                ],
            )

        conn.commit()
    finally:
        conn.close()


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return

    cwd = Path(hook_input.get("cwd", "."))
    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "")

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
    buffer_dir = vault / "knowledge" / "buffer"
    buffer_dir.mkdir(parents=True, exist_ok=True)

    # Load state
    state = load_state(buffer_dir)

    # Extract delta as simple text
    text_content, latest_ts, message_count = extract_delta(
        transcript_path, state.get("last_captured_ts")
    )

    # Extract and store usage data (always, even for trivial sessions)
    if session_id:
        try:
            usage = extract_usage_data(transcript_path, session_id)
            store_usage(vault, session_id, usage)
        except Exception:
            pass  # Don't fail the hook if usage tracking fails

    # Skip buffer write if no new content or trivial (< 2 messages)
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
            f"Run: Task(📜 Archivist, 'Process buffer')"
        )

    print(json.dumps(response))


if __name__ == "__main__":
    main()
