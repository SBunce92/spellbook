# Entity Guidelines

Reference for entity extraction and canonicalization.

## The Librarian Test (CRITICAL)

Before adding ANY entity, ask: **"Would a Librarian ever search for this term?"**

If the answer is no, DO NOT extract it. Entities exist for retrieval. Noise entities pollute the index and make real entities harder to find.

## Good Entities (Extract These)

| Type | Examples | Why |
|------|----------|-----|
| Named tools | Claude Code, SQLite, Redis, uv, Python | Specific, searchable |
| Named agents | Archivist, Librarian (as `tool` type) | Part of this system |
| Project names | spellbook, acme-api | Specific projects |
| People | Samuel Bunce, Jane Doe | Named individuals |
| Specific technical concepts | hooks, YAML frontmatter, entity extraction, TTL, pub/sub | Would search for these |
| Protocols/formats | JSON, YAML, HTTP, WebSocket | Specific standards |

## Bad Entities (DO NOT Extract)

| Type | Examples | Why |
|------|----------|-----|
| Generic abstract nouns | planning, research, documentation, automation, design | Too vague to search |
| Platitudes | best practices, single source of truth | Marketing speak |
| Process words | delegation, orchestration, management, coordination | Describe actions, not things |
| Meta-commentary | agent scaling, workflow optimization | Self-referential noise |
| Adjective+noun combos | efficient caching, proper validation | Adjectives don't help retrieval |
| Things already implied | code, software, development, implementation | Every doc is about these |

## When In Doubt

- Fewer entities is better than more
- If it sounds like a buzzword, skip it
- If you wouldn't ctrl+F for it, skip it
- 2-4 entities per document is typical; 0 is fine for simple docs

## Deduplication Rules

1. **Agents are tools, not concepts**: Use `tool: [Archivist]`, never `concept: [archivist]`
2. **One canonical per thing**: `Git` and `git` should be the same canonical
3. **Prefer specific over general**: If you have `Redis caching`, just use `Redis`

## Detecting Entity Variations

| Pattern | Example | Choose As Canonical |
|---------|---------|---------------------|
| Case variations | sam, Sam, SAM | Most formal: "Sam" |
| Nicknames vs full | Sam, Samuel Bunce | Full name: "Samuel Bunce" |
| Tool name variants | Claude Code, claude-code, CC | Official: "Claude Code" |
| Abbreviations | JS, JavaScript | Full unless abbreviation is standard |

**Principle:** The canonical should be the most complete, formal, or official form.

## Canonical Resolution SQL

```bash
# Check if a term resolves to an existing canonical
sqlite3 index.db "SELECT canonical, entity_type FROM entity_aliases WHERE alias = 'sam' COLLATE NOCASE"

# If result: Use the canonical value in frontmatter
# If no result: Check if this is a variation of existing entity before creating new
```

## Creating New Canonical Entities

```bash
# 1. Create the canonical entity
sqlite3 index.db "INSERT INTO entities (name, type, created, last_mentioned) VALUES ('Samuel Bunce', 'person', datetime('now'), datetime('now'))"

# 2. Register the canonical as an alias to itself
sqlite3 index.db "INSERT OR IGNORE INTO entity_aliases (alias, canonical, entity_type) VALUES ('Samuel Bunce', 'Samuel Bunce', 'person')"

# 3. Register common variations as aliases
sqlite3 index.db "INSERT OR IGNORE INTO entity_aliases (alias, canonical, entity_type) VALUES ('Sam', 'Samuel Bunce', 'person')"
sqlite3 index.db "INSERT OR IGNORE INTO entity_aliases (alias, canonical, entity_type) VALUES ('sam', 'Samuel Bunce', 'person')"
```

**Always self-alias:** Register the canonical name as an alias to itself for consistent lookups.

## Adding Aliases to Existing Canonicals

```bash
# Verify canonical exists
sqlite3 index.db "SELECT name FROM entities WHERE name = 'Claude Code'"

# Add the new alias
sqlite3 index.db "INSERT OR IGNORE INTO entity_aliases (alias, canonical, entity_type) VALUES ('CC', 'Claude Code', 'tool')"
```

## Examples

**BAD frontmatter:**
```yaml
entities:
  concept: [planning, best practices, automation, single source of truth]
  tool: [Archivist, Claude Code]
```

**GOOD frontmatter:**
```yaml
entities:
  tool: [Archivist, Claude Code]
```

**BAD frontmatter:**
```yaml
entities:
  concept: [hooks, hook architecture, delegation enforcement, agent routing]
```

**GOOD frontmatter:**
```yaml
entities:
  concept: [hooks, routing table]
  tool: [Claude Code]
```
