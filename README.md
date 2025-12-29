# Spellbook

Personal knowledge vault system for Claude Code with subagentic workflows.

## Prerequisites

Before installing spellbook, ensure you have the following on your Linux system:

### Python 3.11+

```bash
# Check version
python3 --version

# If needed, install via your package manager
# Ubuntu/Debian:
sudo apt update && sudo apt install python3.11 python3.11-venv

# Fedora:
sudo dnf install python3.11

# Arch:
sudo pacman -S python
```

### uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (restart shell or run):
source ~/.local/bin/env
```

### Claude Code

```bash
# Requires Node.js 18+
node --version

# Install Node.js if needed (via nvm recommended):
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 22

# Install Claude Code globally
npm install -g @anthropic-ai/claude-code

# Authenticate (opens browser)
claude auth
```

## Installation

```bash
uv tool install git+https://github.com/SBunce92/spellbook.git
```

For development (from source):

```bash
git clone https://github.com/SBunce92/spellbook
cd spellbook
uv pip install -e .
```

## Quick Start

```bash
# Initialize a new vault
sb init ~/vaults/work

# Run Claude Code in the vault (works from anywhere)
sb cc ~/vaults/work

# Or if you're already in the vault directory
cd ~/vaults/work
sb cc

# Check vault status
sb status
```

## CLI Commands

The CLI is for installation and administration only. All agent work happens within Claude Code sessions.

| Command | Description |
|---------|-------------|
| `sb init [path]` | Create new vault |
| `sb cc [path]` | Run Claude Code in a vault |
| `sb update` | Update managed files |
| `sb status` | Show vault status |
| `sb rebuild` | Rebuild index.db |

## Vault Structure

```
vault/
├── .spellbook           # Vault marker
├── .claude/
│   ├── agents/          # Subagent definitions
│   ├── hooks/           # Hook scripts
│   └── settings.json    # Hook registration
├── knowledge/           # Git repo for knowledge artifacts
│   ├── buffer/          # Pending transcripts
│   ├── log/             # Archived documents
│   ├── docs/            # Design documents
│   ├── index.db         # SQLite index (gitignored)
│   └── repos.yaml       # Repository manifest (future)
├── repos/               # Cloned repositories (future)
└── CLAUDE.md            # Project instructions
```

## Agents

Agents in `.claude/agents/` are auto-delegated by Claude Code based on task description:

**Core:**
- **📜 Archivist** - Process knowledge/buffer → knowledge/log, extract entities
- **📚 Librarian** - Deep retrieval from vault, synthesize answers with citations
- **🔍 Researcher** - Web research, scientific papers, multi-source synthesis

**Coding:**
- **🐍 Backend** - Python, APIs, server-side, performance
- **🎨 Frontend** - TypeScript, React, UX/UI, accessibility
- **🏗️ Architect** - System design, planning, fullstack, tech decisions

**Domain:**
- **📈 Trader** - Derivatives, options, Greeks, quant
- **🤖 AI Engineer** - ML systems, LLM integration, RAG, spellbook/MCP
- **🗄️ Data Engineer** - Pipelines, ClickHouse, ETL
- **🛠️ DevOps** - CI/CD, Docker, infra, deployment

## License

MIT
