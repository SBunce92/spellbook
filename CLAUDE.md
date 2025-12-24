# Spellbook Development

Personal knowledge vault system for Claude Code.

## Version Bumping (MANDATORY)

**Every change to spellbook requires a version bump.**

Version lives in `src/spellbook/__init__.py`:

```python
__version__ = "0.1.8"  # Bump this
```

### When committing:

1. Make your changes
2. Bump version in `__init__.py`
3. Commit message format: `v{version}: Brief description`

```bash
# Example
git commit -m "v0.1.8: Librarian database-first retrieval workflows"
```

### Versioning scheme

- **Patch** (0.1.x): Bug fixes, agent prompt updates, small improvements
- **Minor** (0.x.0): New features, new agents, schema changes
- **Major** (x.0.0): Breaking changes

## Project Structure

```
src/spellbook/
  __init__.py      # Version (single source of truth)
  cli.py           # sb command
  installer.py     # Vault creation/update
  index.py         # Entity indexing
  schema.py        # Database schema
  assets/          # Copied to vault on install
    .claude/
      agents/      # Subagent definitions
      hooks/       # Hook scripts
    CLAUDE.md      # Vault instructions
```

## Testing changes

```bash
# Install in editable mode
pip install -e .

# Create test vault
cd /tmp && mkdir test-vault && cd test-vault
sb init

# Test update flow
sb update
```
