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

# Process buffer to archive
sb archive

# Query the archive
sb recall "What was the decision about ClickHouse?"
sb quick "Strike-PnL status"

# Scan for dead code
sb haunt ./src
```

## Commands

| Command | Description |
|---------|-------------|
| `sb init [path]` | Create new vault |
| `sb update` | Update managed files |
| `sb status` | Show vault status |
| `sb archive` | Process buffer to log |
| `sb recall <query>` | Deep retrieval |
| `sb quick <query>` | Fast lookup |
| `sb haunt [path]` | Dead code scan |
| `sb rebuild` | Rebuild index |

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
