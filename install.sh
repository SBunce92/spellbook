#!/bin/bash
set -e

# Spellbook installer
# Usage: curl -fsSL https://raw.githubusercontent.com/SBunce92/spellbook/main/install.sh | bash

BIN_DIR="$HOME/.local/bin"

# Install uv if needed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$BIN_DIR:$PATH"
fi

echo "Installing Spellbook..."
uv tool install --force git+https://github.com/SBunce92/spellbook.git

# Ensure PATH is configured
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    SHELL_RC=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$SHELL_RC" 2>/dev/null; then
            echo '' >> "$SHELL_RC"
            echo '# Spellbook' >> "$SHELL_RC"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
            echo "Added ~/.local/bin to PATH in $SHELL_RC"
            echo "Run: source $SHELL_RC"
        fi
    fi
fi

echo "Done! Run 'sb --help' to get started."
