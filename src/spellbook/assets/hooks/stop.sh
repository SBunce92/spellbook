#!/bin/bash
# Spellbook stop hook - captures session transcript to buffer

# Find vault root
find_vault_root() {
    local dir="$1"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/.spellbook" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

# Get vault root
VAULT_ROOT=$(find_vault_root "$PWD")
if [[ -z "$VAULT_ROOT" ]]; then
    exit 0  # Not in a vault, skip silently
fi

BUFFER_DIR="$VAULT_ROOT/buffer"
mkdir -p "$BUFFER_DIR"

# Generate timestamp filename
TS=$(date -u +"%Y-%m-%dT%H-%M-%S")
BUFFER_FILE="$BUFFER_DIR/${TS}.json"

# Read transcript from stdin (passed by Claude Code)
TRANSCRIPT=$(cat)

# Skip if transcript is empty or trivial
if [[ -z "$TRANSCRIPT" ]] || [[ ${#TRANSCRIPT} -lt 100 ]]; then
    exit 0
fi

# Write buffer entry as JSON
cat > "$BUFFER_FILE" << EOF
{
  "ts": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "session_id": "${CLAUDE_SESSION_ID:-}",
  "working_directory": "$PWD",
  "transcript": $(echo "$TRANSCRIPT" | jq -Rs .)
}
EOF
