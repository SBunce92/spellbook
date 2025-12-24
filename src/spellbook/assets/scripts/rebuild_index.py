#!/usr/bin/env python3
"""Standalone script to rebuild index.db from log documents."""

import sqlite3
import sys
from pathlib import Path

import yaml

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    created DATETIME NOT NULL,
    last_mentioned DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
    entity TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    ts DATETIME NOT NULL,
    PRIMARY KEY (entity, doc_id),
    FOREIGN KEY (entity) REFERENCES entities(name)
);

CREATE INDEX IF NOT EXISTS idx_refs_doc ON refs(doc_id);
CREATE INDEX IF NOT EXISTS idx_refs_ts ON refs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_last ON entities(last_mentioned DESC);
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


def rebuild(vault_path: Path) -> None:
    """Rebuild index.db from log documents."""
    db_path = vault_path / "index.db"
    log_path = vault_path / "log"

    if not log_path.exists():
        print(f"Error: log/ directory not found at {vault_path}")
        sys.exit(1)

    # Remove existing database
    db_path.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    doc_count = 0
    entity_count = 0

    for doc_file in sorted(log_path.glob("**/*.md")):
        content = doc_file.read_text()
        frontmatter = parse_frontmatter(content)

        if not frontmatter:
            print(f"  ! {doc_file.name} (no frontmatter)")
            continue

        doc_id = frontmatter.get("id", doc_file.stem)
        ts = frontmatter.get("ts")

        if not ts:
            print(f"  ! {doc_file.name} (no timestamp)")
            continue

        entities = frontmatter.get("entities", [])

        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = entity.get("name")
            etype = entity.get("type")
            if not name or not etype:
                continue

            conn.execute(
                """
                INSERT INTO entities (name, type, created, last_mentioned)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    last_mentioned = excluded.last_mentioned
                """,
                [name, etype, ts, ts],
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO refs (entity, doc_id, ts)
                VALUES (?, ?, ?)
                """,
                [name, doc_id, ts],
            )

            entity_count += 1

        doc_count += 1
        print(f"  + {doc_file.relative_to(vault_path)}")

    conn.commit()

    # Get unique entity count
    cursor = conn.execute("SELECT COUNT(*) FROM entities")
    unique_entities = cursor.fetchone()[0]
    conn.close()

    print(f"\nDone! {doc_count} docs, {unique_entities} entities")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        vault = Path(sys.argv[1])
    else:
        vault = Path.cwd()

    if not (vault / ".spellbook").exists():
        print(f"Error: {vault} is not a Spellbook vault")
        sys.exit(1)

    rebuild(vault)
