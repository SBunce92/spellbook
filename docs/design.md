# Spellbook

Personal knowledge vault system for Claude Code with subagentic workflows.

**Spellbook is an installer** — it creates and manages vault instances on any machine.

---

## Overview

```bash
# Install CLI
pip install spellbook-vault

# Initialize a vault
sb init ~/vaults/work

# Update managed files
sb update

# Use the vault
cd ~/vaults/work
claude
```

---

## Core Principles

1. **Docs are source of truth** — Log files are the durable record
2. **Index is derived** — SQLite is a cache, fully rebuildable from docs
3. **Entities embedded in docs** — Each doc contains its entity refs for rebuild
4. **Subagents, not personas** — Isolated specialists that do work, not advisory modes
5. **Managed vs User separation** — `sb update` never touches user data
6. **Python types for structure** — Pydantic models enforce schema consistency

---

## Architecture

### Spellbook Package (this repo)

```
spellbook/
├── pyproject.toml
├── README.md
├── docs/
│   └── design.md                  # This document
│
├── src/
│   └── spellbook/
│       ├── __init__.py
│       ├── cli.py                 # Click commands
│       ├── installer.py           # Init/update logic
│       ├── index.py               # SQLite operations
│       ├── schema.py              # Pydantic models
│       │
│       └── assets/                # Files copied to vault on init/update
│           ├── agents/
│           │   ├── archivist.md
│           │   ├── librarian.md
│           │   ├── researcher.md
│           │   ├── specter.md
│           │   ├── trader.md
│           │   ├── ai-engineer.md
│           │   ├── data-engineer.md
│           │   └── quant-dev.md
│           ├── hooks/
│           │   └── stop.sh
│           ├── scripts/
│           │   └── rebuild_index.py
│           └── templates/
│               └── CLAUDE.md.template
│
└── tests/
    └── ...
```

### Installed Vault Structure

```
vault/                             # Created by `sb init`
├── .spellbook                     # Version marker + config
│
├── _claude/
│   ├── core/                      # MANAGED (sb update overwrites)
│   │   ├── agents/
│   │   │   ├── archivist.md
│   │   │   ├── librarian.md
│   │   │   ├── researcher.md
│   │   │   ├── specter.md
│   │   │   ├── trader.md
│   │   │   ├── ai-engineer.md
│   │   │   ├── data-engineer.md
│   │   │   └── quant-dev.md
│   │   ├── hooks/
│   │   │   └── stop.sh
│   │   └── scripts/
│   │       ├── schema.py
│   │       └── rebuild_index.py
│   │
│   └── local/                     # USER (sb update never touches)
│       ├── agents/                # Custom agents
│       └── hooks/                 # Custom hooks
│
├── log/                           # USER DATA - archived documents
│   └── 2025-12-24/
│       ├── 001.md
│       └── ...
│
├── buffer/                        # USER DATA - pending transcripts
│   └── 2025-12-24T14-30-00.json
│
├── index.db                       # DERIVED - SQLite index (rebuildable)
│
└── CLAUDE.md                      # USER - init creates, update preserves
```

### Ownership Model

| Path | Owner | `sb update` Behavior |
|------|-------|----------------------|
| `.spellbook` | Spellbook | Updates version |
| `_claude/core/` | Spellbook | Overwrites |
| `_claude/local/` | User | Never touches |
| `log/` | User | Never touches |
| `buffer/` | User | Never touches |
| `index.db` | Derived | Never touches |
| `CLAUDE.md` | User | Never touches (init creates template) |

---

## CLI Commands

The CLI is purely for installation and administration. All agent invocation happens within Claude Code sessions.

```bash
sb init [path]              # Create new vault at path (default: current dir)
sb update                   # Update managed files to latest version
sb status                   # Show vault version, stats, health
sb rebuild                  # Rebuild index.db from log documents
sb agents                   # List available agents
sb --version                # Show Spellbook version
```

### Example Flows

```bash
# Initialize new vault
$ sb init ~/vaults/work

Spellbook v0.1.0

Vault path: /Users/sam/vaults/work
Creating structure...
  ✓ _claude/core/agents/
  ✓ _claude/core/hooks/
  ✓ _claude/core/scripts/
  ✓ _claude/local/
  ✓ log/
  ✓ buffer/
  ✓ CLAUDE.md
  ✓ .spellbook

Done! Vault initialized.

Next steps:
  cd ~/vaults/work
  claude                    # Start Claude Code
  sb status                 # Check vault status
```

```bash
# Update existing vault
$ sb update

Spellbook v0.1.0 → v0.2.0

Updating managed files...
  ✓ _claude/core/agents/archivist.md (updated)
  ✓ _claude/core/agents/specter.md (new)
  ✓ _claude/core/scripts/schema.py (updated)

Preserved:
  - _claude/local/* (3 files)
  - log/* (47 docs)
  - CLAUDE.md

Done!
```

```bash
# Check status
$ sb status

Spellbook Vault Status
──────────────────────
Version:        0.1.0
Path:           /Users/sam/vaults/work
Buffer:         3 pending
Index:          142 entities, 89 docs
Last archive:   2025-12-24 14:30:00
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER SESSION                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (session ends)
┌─────────────────────────────────────────────────────────────────┐
│                         STOP HOOK                                │
│   Write raw transcript → buffer/2025-12-24T14-30-00.json        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (sb archive or next session)
┌─────────────────────────────────────────────────────────────────┐
│                        ARCHIVIST                                 │
│   1. Read buffer/*.json                                          │
│   2. Filter noise (trivial exchanges)                            │
│   3. Extract entities, type, summary                             │
│   4. Write doc → log/2025-12-24/003.md (with entities embedded) │
│   5. Update index.db                                             │
│   6. Delete processed buffer file                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (sb recall / sb quick)
┌─────────────────────────────────────────────────────────────────┐
│                    LIBRARIAN / RESEARCHER                        │
│   1. Query index.db for matching entities                        │
│   2. Retrieve referenced docs from log/                          │
│   3. Synthesize answer with citations                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Schema Definitions

### Python Types (`src/spellbook/schema.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional


# =============================================================================
# Document Types
# =============================================================================

class DocType(str, Enum):
    DECISION = "decision"          # Choice made with rationale
    INSIGHT = "insight"            # Learning or realization
    CODE = "code"                  # Implementation with context
    REFERENCE = "reference"        # Factual information
    CONVERSATION = "conversation"  # Notable discussion
    ANALYSIS = "analysis"          # Deep dive on a topic


# =============================================================================
# Entity Schema
# =============================================================================

class EntityType(str, Enum):
    PROJECT = "project"     # Business initiative (Strike-PnL)
    PERSON = "person"       # Individual (Oscar Wignall)
    TOOL = "tool"           # Software/service (ClickHouse, Docker)
    REPO = "repo"           # Code repository or subpath (mm-data-py/src/clickhouse)
    CONCEPT = "concept"     # Idea or pattern (ReplacingMergeTree strategy)
    ORG = "org"             # Organization (Maven, Anthropic)


class EntityRef(BaseModel):
    """Entity reference embedded in a document."""
    name: str
    type: EntityType


class Entity(BaseModel):
    """Entity record in index.db."""
    type: EntityType
    refs: list[str]              # Doc IDs: ["2025-12-24/003", ...]
    created: datetime
    last_mentioned: datetime


# =============================================================================
# Document Schema
# =============================================================================

class RelatedDoc(BaseModel):
    """Reference to another document."""
    id: str                      # "2025-12-24/003"
    relationship: str            # supersedes, continues, contradicts, related


class ArchiveDoc(BaseModel):
    """
    A single knowledge document in log/.

    IMPORTANT: The `entities` field is the source of truth for rebuilding
    the index. Every entity mentioned MUST be listed here.
    """
    # Identity
    id: str                      # "2025-12-24/003"
    ts: datetime
    type: DocType

    # Content
    title: str
    summary: str                 # One-line summary for quick scanning
    content: str                 # Full markdown body

    # Entities (CRITICAL: used to rebuild index.db)
    entities: list[EntityRef]

    # Rich context
    related_docs: list[RelatedDoc] = []
    tags: list[str] = []

    # Provenance
    source_session: Optional[str] = None
    source_files: list[str] = []  # Files discussed/modified


# =============================================================================
# Buffer Schema
# =============================================================================

class BufferEntry(BaseModel):
    """Raw transcript awaiting processing."""
    ts: datetime
    session_id: Optional[str] = None
    transcript: str              # Raw conversation text
    working_directory: Optional[str] = None
    files_touched: list[str] = []


# =============================================================================
# Config Schema
# =============================================================================

class SpellbookConfig(BaseModel):
    """Stored in .spellbook file."""
    version: str
    vault_name: str
    created: datetime
    last_updated: datetime
```

### SQLite Schema (`index.db`)

```sql
-- Entities table
CREATE TABLE entities (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    created DATETIME NOT NULL,
    last_mentioned DATETIME NOT NULL
);

-- Entity-to-document references
CREATE TABLE refs (
    entity TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    PRIMARY KEY (entity, doc_id),
    FOREIGN KEY (entity) REFERENCES entities(name)
);

-- Indexes for common queries
CREATE INDEX idx_refs_doc ON refs(doc_id);
CREATE INDEX idx_refs_ts ON refs(ts DESC);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_last ON entities(last_mentioned DESC);
```

---

## Document Format

Documents are Markdown with YAML frontmatter.

### Example: Decision Document

```markdown
---
id: "2025-12-24/003"
ts: "2025-12-24T14:30:00Z"
type: decision
title: "Use ReplacingMergeTree for Strike-PnL position data"
summary: "Chose ReplacingMergeTree with version column for out-of-order updates"

entities:
  - name: Strike-PnL
    type: project
  - name: mm-data-py/src/clickhouse
    type: repo
  - name: ClickHouse
    type: tool
  - name: Oscar Wignall
    type: person

related_docs:
  - id: "2025-12-23/017"
    relationship: continues

tags:
  - database
  - architecture

source_files:
  - mm-data-py/src/clickhouse/tables/position.py
---

## Context

Strike-PnL needs to handle position updates that arrive out of order.

## Decision

Use `ReplacingMergeTree` with version column based on event timestamp.

## Rationale

- Handles late-arriving updates without manual dedup
- Oscar confirmed this matches the existing Matador pattern
```

---

## Subagent Definitions

### Core Agents

| Agent | Purpose | Model | Command |
|-------|---------|-------|---------|
| **Archivist** | Process buffer → docs → index | Sonnet | `sb archive` |
| **Librarian** | Deep retrieval + synthesis | Sonnet | `sb recall` |
| **Researcher** | Fast factual lookup | Haiku | `sb quick` |
| **Specter** | Dead code + bloat detection | Sonnet | `sb haunt` |

### Domain Agents

| Agent | Purpose | Model | Trigger |
|-------|---------|-------|---------|
| **Trader** | Options/risk analysis | Sonnet | Contextual |
| **AI Engineer** | ML systems | Sonnet | Contextual |
| **Data Engineer** | Pipelines/ClickHouse | Sonnet | Contextual |
| **Quant Dev** | Numerical code | Sonnet | Contextual |

### Archivist

```markdown
# Archivist Agent

You process raw conversation transcripts into structured knowledge documents.

## Process

1. Read all files in `buffer/`
2. For each transcript, evaluate:
   - Is this substantive? (Skip: greetings, trivial reads, failed debugging)
   - What type? (decision, insight, code, reference, conversation, analysis)
   - What entities? (people, projects, tools, repos, concepts, orgs)
3. For substantive content:
   - Generate document with YAML frontmatter + markdown body
   - Include ALL entities in frontmatter (critical for index rebuild)
   - Write to `log/YYYY-MM-DD/NNN.md`
   - Update index.db
4. Delete processed buffer file

## Entity Extraction Rules

- Use canonical names (check existing entities in index.db)
- "Felix" → "Felix Poirier" if that's the known name
- For repos, include path: "mm-data-py/src/clickhouse"
- When uncertain, prefer creating new entity over wrong match

## Output

- New documents in log/
- Updated index.db
- Deleted buffer files
```

### Librarian

```markdown
# Librarian Agent

You answer questions by retrieving and synthesizing knowledge from the archive.

## Process

1. Parse query for entities, time constraints, query type
2. Query index.db for matching entities
3. Retrieve documents from log/
4. Synthesize answer with citations

## Response Format

Always cite sources:

> Based on your discussion on 2025-12-24 ([003](log/2025-12-24/003.md)),
> you decided to use ReplacingMergeTree because...
```

### Researcher

```markdown
# Researcher Agent

You provide quick, concise answers from the archive.

## Process

1. Identify target entity or keyword
2. Query index.db for refs
3. Read most recent 1-2 relevant docs
4. Return concise answer (2-3 sentences max)

## Response Format

Direct and brief:

> Strike-PnL is a P&L calculation project, currently staging-ready.
> Last discussed 2025-12-24.
```

### Specter

```markdown
# Specter Agent

You hunt dead code and unnecessary bloat in codebases and diffs.

## Scope

- Unused imports, variables, functions
- Unreachable code paths
- Orphaned files (no references)
- Diff bloat (unnecessary additions, duplicated logic)
- Commented-out code that should be deleted

## Output Format

## Dead Code Found

### High Confidence (safe to delete)
- `src/utils/old_helper.py` - No imports found

### Needs Verification
- `src/models/user.py:23` - Only used in tests

### Diff Bloat
- Lines 45-60 duplicate logic from `src/utils/helpers.py:12-27`
```

---

## Index Operations

### Adding a Document

```python
def add_document(conn: sqlite3.Connection, doc: ArchiveDoc):
    """Add document refs to index."""
    for entity_ref in doc.entities:
        conn.execute("""
            INSERT INTO entities (name, type, created, last_mentioned)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                last_mentioned = excluded.last_mentioned
        """, [entity_ref.name, entity_ref.type.value, doc.ts, doc.ts])

        conn.execute("""
            INSERT OR IGNORE INTO refs (entity, doc_id, ts)
            VALUES (?, ?, ?)
        """, [entity_ref.name, doc.id, doc.ts])

    conn.commit()
```

### Querying

```python
def get_entity_docs(conn: sqlite3.Connection, entity: str) -> list[str]:
    """Get all doc IDs for an entity, most recent first."""
    cursor = conn.execute("""
        SELECT doc_id FROM refs
        WHERE entity = ?
        ORDER BY ts DESC
    """, [entity])
    return [row[0] for row in cursor.fetchall()]

def find_entities_like(conn: sqlite3.Connection, pattern: str) -> list[str]:
    """Find entities matching pattern (for repo subpaths)."""
    cursor = conn.execute("""
        SELECT name FROM entities
        WHERE name LIKE ?
        ORDER BY last_mentioned DESC
    """, [f"{pattern}%"])
    return [row[0] for row in cursor.fetchall()]
```

### Rebuilding

```python
def rebuild_index(vault_path: Path):
    """Rebuild index.db by scanning all documents in log/."""
    db_path = vault_path / "index.db"
    log_path = vault_path / "log"

    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    for doc_file in sorted(log_path.glob("**/*.md")):
        doc = parse_document(doc_file)
        if doc:
            add_document(conn, doc)

    conn.close()
```

---

## Implementation Plan

### Phase 1: Core CLI ✅
- [x] Project scaffolding (pyproject.toml, src layout)
- [x] Click CLI with `init`, `update`, `status`, `rebuild`, `agents`
- [x] Asset copying for managed files
- [x] `.spellbook` config file handling

### Phase 2: Schema & Index ✅
- [x] Pydantic models in `schema.py`
- [x] SQLite operations in `index.py`
- [x] `rebuild` command
- [x] Document parsing (YAML frontmatter + markdown)

### Phase 3: Agent Prompts ✅
- [x] Agent prompt files in assets/
- [x] Agent color/icon styling
- [x] Stop hook implementation

### Phase 4: Polish
- [ ] Error handling and validation
- [ ] Tests
- [x] Documentation and README

---

## Distribution

```toml
# pyproject.toml
[project]
name = "spellbook-vault"
version = "0.1.0"
description = "Personal knowledge vault for Claude Code"
dependencies = [
    "click>=8.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "rich>=13.0",
]

[project.scripts]
sb = "spellbook.cli:cli"
```

```bash
# Install
pip install spellbook-vault

# Or from source
pip install -e .
```
