"""SQLite index operations for Spellbook."""

import sqlite3
from pathlib import Path

import yaml
from rich.console import Console

from .schema import ArchiveDoc, DocType, EntityRef, EntityType

console = Console()

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


def connect(vault_path: Path) -> sqlite3.Connection:
    """Connect to vault's index database."""
    db_path = vault_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize database schema."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def add_document(conn: sqlite3.Connection, doc: ArchiveDoc) -> None:
    """Add document refs to index."""
    for entity_ref in doc.entities:
        conn.execute(
            """
            INSERT INTO entities (name, type, created, last_mentioned)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                last_mentioned = excluded.last_mentioned
            """,
            [entity_ref.name, entity_ref.type.value, doc.ts, doc.ts],
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO refs (entity, doc_id, ts)
            VALUES (?, ?, ?)
            """,
            [entity_ref.name, doc.id, doc.ts],
        )

    conn.commit()


def get_entity_docs(conn: sqlite3.Connection, entity: str) -> list[str]:
    """Get all doc IDs for an entity, most recent first."""
    cursor = conn.execute(
        """
        SELECT doc_id FROM refs
        WHERE entity = ?
        ORDER BY ts DESC
        """,
        [entity],
    )
    return [row[0] for row in cursor.fetchall()]


def find_entities_like(conn: sqlite3.Connection, pattern: str) -> list[str]:
    """Find entities matching pattern (for repo subpaths)."""
    cursor = conn.execute(
        """
        SELECT name FROM entities
        WHERE name LIKE ?
        ORDER BY last_mentioned DESC
        """,
        [f"{pattern}%"],
    )
    return [row[0] for row in cursor.fetchall()]


def get_entity(conn: sqlite3.Connection, name: str) -> dict | None:
    """Get entity details by name."""
    cursor = conn.execute(
        """
        SELECT name, type, created, last_mentioned FROM entities
        WHERE name = ?
        """,
        [name],
    )
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)


def get_recent_entities(
    conn: sqlite3.Connection, limit: int = 20, entity_type: str | None = None
) -> list[dict]:
    """Get recently mentioned entities."""
    if entity_type:
        cursor = conn.execute(
            """
            SELECT name, type, last_mentioned FROM entities
            WHERE type = ?
            ORDER BY last_mentioned DESC
            LIMIT ?
            """,
            [entity_type, limit],
        )
    else:
        cursor = conn.execute(
            """
            SELECT name, type, last_mentioned FROM entities
            ORDER BY last_mentioned DESC
            LIMIT ?
            """,
            [limit],
        )
    return [dict(row) for row in cursor.fetchall()]


def parse_document(doc_path: Path) -> ArchiveDoc | None:
    """Parse a markdown document with YAML frontmatter."""
    content = doc_path.read_text()

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    if not frontmatter:
        return None

    # Parse entities
    entities = []
    for e in frontmatter.get("entities", []):
        if isinstance(e, dict) and "name" in e and "type" in e:
            try:
                entities.append(EntityRef(name=e["name"], type=EntityType(e["type"])))
            except ValueError:
                pass

    # Parse related docs
    related_docs = []
    for r in frontmatter.get("related_docs", []):
        if isinstance(r, dict) and "id" in r:
            related_docs.append({"id": r["id"], "relationship": r.get("relationship", "related")})

    try:
        doc = ArchiveDoc(
            id=frontmatter.get("id", doc_path.stem),
            ts=frontmatter.get("ts"),
            type=DocType(frontmatter.get("type", "reference")),
            title=frontmatter.get("title", "Untitled"),
            summary=frontmatter.get("summary", ""),
            content=parts[2].strip(),
            entities=entities,
            related_docs=related_docs,
            tags=frontmatter.get("tags", []),
            source_session=frontmatter.get("source_session"),
            source_files=frontmatter.get("source_files", []),
        )
        return doc
    except Exception:
        return None


def rebuild_index(vault_path: Path) -> None:
    """Rebuild index.db by scanning all documents in log/."""
    db_path = vault_path / "index.db"
    log_path = vault_path / "log"

    console.print("\n[bold]Rebuilding index...[/bold]\n")

    # Remove existing database
    db_path.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    init_schema(conn)

    doc_count = 0
    entity_count = 0
    errors = 0

    for doc_file in sorted(log_path.glob("**/*.md")):
        doc = parse_document(doc_file)
        if doc:
            add_document(conn, doc)
            doc_count += 1
            entity_count += len(doc.entities)
            console.print(f"  [green]\u2713[/green] {doc_file.relative_to(vault_path)}")
        else:
            errors += 1
            console.print(f"  [yellow]![/yellow] {doc_file.relative_to(vault_path)} (parse error)")

    conn.close()

    # Get unique entity count
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM entities")
    unique_entities = cursor.fetchone()[0]
    conn.close()

    console.print(f"\n[green]Done![/green]")
    console.print(f"  Documents: {doc_count}")
    console.print(f"  Entities:  {unique_entities}")
    if errors:
        console.print(f"  Errors:    {errors}")
    console.print()
