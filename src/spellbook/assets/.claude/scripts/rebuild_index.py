#!/usr/bin/env python3
"""Standalone script to rebuild index.db from log and docs documents."""

import sqlite3
import sys
from pathlib import Path

import yaml

# Directories to scan for documents
DOC_DIRS = ["log", "docs"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    created DATETIME NOT NULL,
    last_mentioned DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias TEXT PRIMARY KEY COLLATE NOCASE,
    entity_id INTEGER NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS refs (
    entity_id INTEGER NOT NULL,
    doc_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    PRIMARY KEY (entity_id, doc_id),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_refs_doc ON refs(doc_id);
CREATE INDEX IF NOT EXISTS idx_refs_ts ON refs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_last ON entities(last_mentioned DESC);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name COLLATE NOCASE);
"""


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def parse_entities(raw_entities) -> list[tuple[str, str]]:
    """Parse entities from either format, returns list of (name, type) tuples."""
    entities = []

    if isinstance(raw_entities, dict):
        # Format A (Archivist): {person: [Sam], project: [spellbook]}
        for entity_type, names in raw_entities.items():
            if isinstance(names, list):
                for name in names:
                    entities.append((name, entity_type))
    elif isinstance(raw_entities, list):
        # Format B (structured): [{name: Sam, type: person}, ...]
        for e in raw_entities:
            if isinstance(e, dict) and "name" in e and "type" in e:
                entities.append((e["name"], e["type"]))

    return entities


def rebuild(vault_path: Path) -> None:
    """Rebuild index.db from log and docs documents."""
    db_path = vault_path / "index.db"

    # Check at least one doc directory exists
    existing_dirs = [d for d in DOC_DIRS if (vault_path / d).exists()]
    if not existing_dirs:
        print(f"Error: No document directories (log/, docs/) found at {vault_path}")
        sys.exit(1)

    # Remove existing database
    db_path.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    doc_count = 0
    entity_count = 0
    errors = 0

    # Scan all document directories
    for dir_name in DOC_DIRS:
        dir_path = vault_path / dir_name
        if not dir_path.exists():
            continue

        for doc_file in sorted(dir_path.glob("**/*.md")):
            content = doc_file.read_text()
            frontmatter = parse_frontmatter(content)

            if not frontmatter:
                print(f"  ! {doc_file.relative_to(vault_path)} (no frontmatter)")
                errors += 1
                continue

            # Use relative path as doc_id for better identification
            doc_id = str(doc_file.relative_to(vault_path))
            # Accept both 'ts' and 'date' fields
            ts = frontmatter.get("ts") or frontmatter.get("date")

            if not ts:
                print(f"  ! {doc_file.relative_to(vault_path)} (no timestamp)")
                errors += 1
                continue

            # Parse entities from either format
            entities = parse_entities(frontmatter.get("entities", []))

            for name, etype in entities:
                # Insert or update entity
                conn.execute(
                    """
                    INSERT INTO entities (name, type, created, last_mentioned)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        last_mentioned = excluded.last_mentioned
                    """,
                    [name, etype, ts, ts],
                )

                # Get entity id
                cursor = conn.execute("SELECT id FROM entities WHERE name = ?", [name])
                entity_id = cursor.fetchone()[0]

                # Add canonical name as an alias (if not exists)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO entity_aliases (alias, entity_id)
                    VALUES (?, ?)
                    """,
                    [name, entity_id],
                )

                # Insert ref using entity_id
                conn.execute(
                    """
                    INSERT OR IGNORE INTO refs (entity_id, doc_id, ts)
                    VALUES (?, ?, ?)
                    """,
                    [entity_id, doc_id, ts],
                )

                entity_count += 1

            doc_count += 1
            print(f"  + {doc_file.relative_to(vault_path)}")

    conn.commit()

    # Get unique entity count
    cursor = conn.execute("SELECT COUNT(*) FROM entities")
    unique_entities = cursor.fetchone()[0]
    conn.close()

    print("\nDone!")
    print(f"  Documents: {doc_count}")
    print(f"  Entities:  {unique_entities}")
    if errors:
        print(f"  Errors:    {errors}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        vault = Path(sys.argv[1])
    else:
        vault = Path.cwd()

    if not (vault / ".spellbook").exists():
        print(f"Error: {vault} is not a Spellbook vault")
        sys.exit(1)

    rebuild(vault)
