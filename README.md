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
├── _claude/
│   ├── core/            # Managed (sb update)
│   └── local/           # User customizations
├── log/                 # Archived documents
├── buffer/              # Pending transcripts
├── index.db             # SQLite index
└── CLAUDE.md            # Project instructions
```

## Agents

- **Archivist**: Process transcripts into structured docs
- **Librarian**: Deep retrieval with synthesis
- **Researcher**: Fast factual lookup
- **Specter**: Dead code and quality checks

## License

MIT
