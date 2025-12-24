# Spellbook

Personal knowledge vault system for Claude Code with subagentic workflows.

## Installation

```bash
uv pip install spellbook-vault
```

Or from source:

```bash
git clone https://github.com/SBunce92/spellbook
cd spellbook
uv pip install -e .
```

## Quick Start

```bash
# Initialize a new vault
sb init ~/vaults/work

# Check status
sb status

# Start Claude Code - agents are invoked automatically
cd ~/vaults/work
claude
```

## CLI Commands

The CLI is for installation and administration only. All agent work happens within Claude Code sessions.

| Command | Description |
|---------|-------------|
| `sb init [path]` | Create new vault |
| `sb update` | Update managed files |
| `sb status` | Show vault status |
| `sb rebuild` | Rebuild index.db |

## Vault Structure

```
vault/
├── .spellbook           # Config
├── .claude/
│   └── agents/          # Auto-delegated subagents
├── log/                 # Archived documents
├── buffer/              # Pending transcripts
├── index.db             # SQLite index
└── CLAUDE.md            # Project instructions
```

## Agents

Agents in `.claude/agents/` are auto-delegated by Claude Code based on task description:

- **archivist**: Process transcripts into structured docs
- **librarian**: Deep retrieval with synthesis
- **researcher**: Fast factual lookup
- **specter**: Dead code and quality checks
- **trader**, **ai-engineer**, **data-engineer**, **quant-dev**: Domain specialists

## License

MIT
