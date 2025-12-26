"""SQLite index operations for Spellbook."""

import sqlite3
from pathlib import Path

import yaml
from rich.console import Console

from .schema import ArchiveDoc, DocType, EntityRef, EntityType, SessionUsage, SubagentCall

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

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias TEXT PRIMARY KEY COLLATE NOCASE,
    canonical TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    FOREIGN KEY (canonical) REFERENCES entities(name)
);

CREATE INDEX IF NOT EXISTS idx_refs_doc ON refs(doc_id);
CREATE INDEX IF NOT EXISTS idx_refs_ts ON refs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_last ON entities(last_mentioned DESC);
CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON entity_aliases(canonical);
"""

# Context tracking schema (separate from entity schema for migration safety)
CONTEXT_SCHEMA_SQL = """
-- Session-level context tracking
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,           -- sessionId (UUID)
    vault_path TEXT NOT NULL,      -- Vault this session ran in
    started_at DATETIME NOT NULL,  -- First message timestamp
    ended_at DATETIME,             -- Last message timestamp
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cache_creation INTEGER DEFAULT 0,
    total_cache_read INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    slug TEXT                      -- Human-readable session name
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_vault ON sessions(vault_path);

-- Subagent invocations within a session
CREATE TABLE IF NOT EXISTS subagent_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,        -- Short hex ID (e.g., "afb88bb")
    agent_type TEXT NOT NULL,      -- "Archivist", "Backend", etc.
    description TEXT,              -- From Task input
    prompt_preview TEXT,           -- First 200 chars of prompt
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    duration_ms INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_creation INTEGER DEFAULT 0,
    cache_read INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    tool_use_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'  -- running, completed, failed
);

CREATE INDEX IF NOT EXISTS idx_subagent_session ON subagent_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_type ON subagent_calls(agent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_started ON subagent_calls(started_at DESC);
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

    # Parse entities - support both formats:
    # Format A (Archivist): {person: [Sam], project: [spellbook]}
    # Format B (structured): [{name: Sam, type: person}, ...]
    entities = []
    raw_entities = frontmatter.get("entities", [])

    if isinstance(raw_entities, dict):
        # Format A: nested dict with type keys
        for entity_type, names in raw_entities.items():
            if isinstance(names, list):
                for name in names:
                    try:
                        entities.append(EntityRef(name=name, type=EntityType(entity_type)))
                    except ValueError:
                        pass  # Skip unknown entity types
    elif isinstance(raw_entities, list):
        # Format B: list of {name, type} dicts
        for e in raw_entities:
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

    # Get timestamp - accept both 'ts' and 'date' fields
    ts = frontmatter.get("ts") or frontmatter.get("date")
    if not ts:
        return None

    # Extract title from first heading if not in frontmatter
    title = frontmatter.get("title")
    if not title:
        body = parts[2].strip()
        for line in body.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if not title:
            title = "Untitled"

    try:
        doc = ArchiveDoc(
            id=frontmatter.get("id", doc_path.stem),
            ts=ts,
            type=DocType(frontmatter.get("type", "reference")),
            title=title,
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


def _has_aliases_table(conn: sqlite3.Connection) -> bool:
    """Check if the entity_aliases table exists in the database."""
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='entity_aliases'
        """
    )
    return cursor.fetchone() is not None


def add_entity_alias(
    conn: sqlite3.Connection,
    alias: str,
    canonical: str,
    entity_type: str,
) -> bool:
    """Add an alias mapping for an entity.

    Args:
        conn: Database connection
        alias: The alias name (e.g., "sam", "Sam")
        canonical: The canonical name (e.g., "Samuel Bunce")
        entity_type: Entity type (e.g., "person")

    Returns:
        True if alias was added, False if it already exists
    """
    try:
        conn.execute(
            """
            INSERT INTO entity_aliases (alias, canonical, entity_type)
            VALUES (?, ?, ?)
            """,
            [alias, canonical, entity_type],
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Alias already exists
        return False


def get_canonical_name(conn: sqlite3.Connection, name: str) -> str:
    """Resolve an entity name to its canonical form.

    If the name is an alias, returns the canonical name.
    Otherwise, returns the name unchanged.
    """
    cursor = conn.execute(
        """
        SELECT canonical FROM entity_aliases
        WHERE alias = ? COLLATE NOCASE
        """,
        [name],
    )
    row = cursor.fetchone()
    return row["canonical"] if row else name


def get_aliases_for_entity(conn: sqlite3.Connection, canonical: str) -> list[str]:
    """Get all aliases for a canonical entity name."""
    cursor = conn.execute(
        """
        SELECT alias FROM entity_aliases
        WHERE canonical = ?
        ORDER BY alias COLLATE NOCASE
        """,
        [canonical],
    )
    return [row["alias"] for row in cursor.fetchall()]


def _get_entity_id_column(conn: sqlite3.Connection) -> str:
    """Determine the entity identifier column name.

    Newer schema uses 'id' as primary key with 'name' as canonical.
    Older schema uses 'name' as primary key directly.
    """
    cursor = conn.execute("PRAGMA table_info(entities)")
    columns = {row[1] for row in cursor.fetchall()}
    return "id" if "id" in columns else "name"


def list_entities_with_aliases(vault_path: Path, entity_type: str | None = None) -> None:
    """List all entities grouped by type with their aliases.

    Output is deterministic: sorted by type, then by canonical name.
    Aliases are sorted alphabetically under each entity.

    Only shows canonical entities (those that are not aliases of another entity).
    """
    db_path = vault_path / "index.db"
    if not db_path.exists():
        console.print("[yellow]No index.db found. Run 'sb rebuild' first.[/yellow]")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    has_aliases = _has_aliases_table(conn)

    # Get canonical entities only (exclude entities that are aliases of others)
    if has_aliases:
        # Only show entities that are NOT aliases pointing to a DIFFERENT entity
        # (self-referential aliases like "Samuel Bunce" -> "Samuel Bunce" are allowed)
        if entity_type:
            cursor = conn.execute(
                """
                SELECT e.name, e.type FROM entities e
                WHERE e.type = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM entity_aliases ea
                    WHERE ea.alias = e.name COLLATE NOCASE
                      AND ea.canonical != e.name COLLATE NOCASE
                  )
                ORDER BY e.type, e.name COLLATE NOCASE
                """,
                [entity_type],
            )
        else:
            cursor = conn.execute(
                """
                SELECT e.name, e.type FROM entities e
                WHERE NOT EXISTS (
                    SELECT 1 FROM entity_aliases ea
                    WHERE ea.alias = e.name COLLATE NOCASE
                      AND ea.canonical != e.name COLLATE NOCASE
                )
                ORDER BY e.type, e.name COLLATE NOCASE
                """
            )
    else:
        # No aliases table - show all entities
        if entity_type:
            cursor = conn.execute(
                """
                SELECT name, type FROM entities
                WHERE type = ?
                ORDER BY type, name COLLATE NOCASE
                """,
                [entity_type],
            )
        else:
            cursor = conn.execute(
                """
                SELECT name, type FROM entities
                ORDER BY type, name COLLATE NOCASE
                """
            )

    entities = cursor.fetchall()

    if not entities:
        if entity_type:
            console.print(f"[yellow]No entities of type '{entity_type}' found.[/yellow]")
        else:
            console.print("[yellow]No entities found in index.[/yellow]")
        conn.close()
        return

    # Group entities by type
    by_type: dict[str, list[tuple[str, list[str]]]] = {}
    for row in entities:
        name = row["name"]
        etype = row["type"]

        # Get aliases for this canonical entity (excluding self-referential alias)
        aliases: list[str] = []
        if has_aliases:
            alias_cursor = conn.execute(
                """
                SELECT alias FROM entity_aliases
                WHERE canonical = ?
                  AND alias != canonical COLLATE NOCASE
                ORDER BY alias COLLATE NOCASE
                """,
                [name],
            )
            aliases = [r["alias"] for r in alias_cursor.fetchall()]

        if etype not in by_type:
            by_type[etype] = []
        by_type[etype].append((name, aliases))

    conn.close()

    # Calculate total count
    total = sum(len(v) for v in by_type.values())
    console.print(f"\n[bold]Entities ({total} total)[/bold]\n")

    # Print grouped output, sorted by type name
    for etype in sorted(by_type.keys()):
        entity_list = by_type[etype]
        console.print(f"[cyan]{etype}[/cyan]:")

        for name, aliases in entity_list:
            console.print(f"  {name}")
            for alias in aliases:
                console.print(f"    [dim]- {alias}[/dim]")

        console.print()


def rebuild_index(vault_path: Path) -> None:
    """Rebuild index.db by scanning all documents in log/."""
    db_path = vault_path / "index.db"
    log_path = vault_path / "log"

    console.print("\n[bold]Rebuilding index...[/bold]\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Drop only entity tables (preserves context tables: sessions, subagent_calls)
    conn.execute("DROP TABLE IF EXISTS refs")
    conn.execute("DROP TABLE IF EXISTS entity_aliases")
    conn.execute("DROP TABLE IF EXISTS entities")
    conn.commit()

    # Recreate entity schema
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

    console.print("\n[green]Done![/green]")
    console.print(f"  Documents: {doc_count}")
    console.print(f"  Entities:  {unique_entities}")
    if errors:
        console.print(f"  Errors:    {errors}")
    console.print()


# =============================================================================
# Context Tracking Functions
# =============================================================================


def init_context_schema(conn: sqlite3.Connection) -> None:
    """Initialize context tracking schema (idempotent)."""
    conn.executescript(CONTEXT_SCHEMA_SQL)
    conn.commit()


def ensure_context_schema(vault_path: Path) -> sqlite3.Connection:
    """Ensure context schema exists and return connection."""
    db_path = vault_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_context_schema(conn)
    return conn


def upsert_session(conn: sqlite3.Connection, session: SessionUsage) -> None:
    """Insert or update session usage data."""
    conn.execute(
        """
        INSERT INTO sessions (
            id, vault_path, started_at, ended_at,
            total_input_tokens, total_output_tokens,
            total_cache_creation, total_cache_read,
            total_messages, slug
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ended_at = excluded.ended_at,
            total_input_tokens = excluded.total_input_tokens,
            total_output_tokens = excluded.total_output_tokens,
            total_cache_creation = excluded.total_cache_creation,
            total_cache_read = excluded.total_cache_read,
            total_messages = excluded.total_messages,
            slug = excluded.slug
        """,
        [
            session.id,
            session.vault_path,
            session.started_at.isoformat() if session.started_at else None,
            session.ended_at.isoformat() if session.ended_at else None,
            session.total_input_tokens,
            session.total_output_tokens,
            session.total_cache_creation,
            session.total_cache_read,
            session.total_messages,
            session.slug,
        ],
    )
    conn.commit()


def insert_subagent_call(conn: sqlite3.Connection, call: SubagentCall) -> None:
    """Insert a subagent call record."""
    conn.execute(
        """
        INSERT INTO subagent_calls (
            session_id, agent_id, agent_type, description, prompt_preview,
            started_at, ended_at, duration_ms,
            input_tokens, output_tokens, cache_creation, cache_read,
            total_tokens, tool_use_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            call.session_id,
            call.agent_id,
            call.agent_type,
            call.description,
            call.prompt_preview,
            call.started_at.isoformat() if call.started_at else None,
            call.ended_at.isoformat() if call.ended_at else None,
            call.duration_ms,
            call.input_tokens,
            call.output_tokens,
            call.cache_creation,
            call.cache_read,
            call.total_tokens,
            call.tool_use_count,
            call.status,
        ],
    )
    conn.commit()


def get_sessions(
    conn: sqlite3.Connection,
    since: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get sessions, optionally filtered by date."""
    if since:
        cursor = conn.execute(
            """
            SELECT * FROM sessions
            WHERE started_at >= ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            [since, limit],
        )
    else:
        cursor = conn.execute(
            """
            SELECT * FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            [limit],
        )
    return [dict(row) for row in cursor.fetchall()]


def get_session_by_id(conn: sqlite3.Connection, session_id: str) -> dict | None:
    """Get a specific session by ID or slug prefix."""
    # Try exact ID match first
    cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", [session_id])
    row = cursor.fetchone()
    if row:
        return dict(row)

    # Try slug prefix match
    cursor = conn.execute(
        "SELECT * FROM sessions WHERE slug LIKE ? ORDER BY started_at DESC LIMIT 1",
        [f"{session_id}%"],
    )
    row = cursor.fetchone()
    if row:
        return dict(row)

    return None


def get_subagent_calls_for_session(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Get all subagent calls for a session."""
    cursor = conn.execute(
        """
        SELECT * FROM subagent_calls
        WHERE session_id = ?
        ORDER BY started_at ASC
        """,
        [session_id],
    )
    return [dict(row) for row in cursor.fetchall()]


def get_subagent_calls_by_type(
    conn: sqlite3.Connection,
    agent_type: str,
    since: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get subagent calls filtered by agent type."""
    if since:
        cursor = conn.execute(
            """
            SELECT sc.*, s.slug as session_slug
            FROM subagent_calls sc
            JOIN sessions s ON sc.session_id = s.id
            WHERE sc.agent_type = ? AND sc.started_at >= ?
            ORDER BY sc.started_at DESC
            LIMIT ?
            """,
            [agent_type, since, limit],
        )
    else:
        cursor = conn.execute(
            """
            SELECT sc.*, s.slug as session_slug
            FROM subagent_calls sc
            JOIN sessions s ON sc.session_id = s.id
            WHERE sc.agent_type = ?
            ORDER BY sc.started_at DESC
            LIMIT ?
            """,
            [agent_type, limit],
        )
    return [dict(row) for row in cursor.fetchall()]


def get_expensive_calls(
    conn: sqlite3.Connection,
    limit: int = 10,
    since: str | None = None,
) -> list[dict]:
    """Get top N most expensive subagent calls by total tokens."""
    if since:
        cursor = conn.execute(
            """
            SELECT sc.*, s.slug as session_slug
            FROM subagent_calls sc
            JOIN sessions s ON sc.session_id = s.id
            WHERE sc.started_at >= ?
            ORDER BY sc.total_tokens DESC
            LIMIT ?
            """,
            [since, limit],
        )
    else:
        cursor = conn.execute(
            """
            SELECT sc.*, s.slug as session_slug
            FROM subagent_calls sc
            JOIN sessions s ON sc.session_id = s.id
            ORDER BY sc.total_tokens DESC
            LIMIT ?
            """,
            [limit],
        )
    return [dict(row) for row in cursor.fetchall()]


def get_agent_type_summary(
    conn: sqlite3.Connection,
    since: str | None = None,
) -> list[dict]:
    """Get aggregated stats by agent type."""
    if since:
        cursor = conn.execute(
            """
            SELECT
                agent_type,
                COUNT(*) as call_count,
                SUM(total_tokens) as total_tokens,
                SUM(duration_ms) as total_duration_ms,
                AVG(total_tokens) as avg_tokens,
                AVG(duration_ms) as avg_duration_ms
            FROM subagent_calls
            WHERE started_at >= ?
            GROUP BY agent_type
            ORDER BY total_tokens DESC
            """,
            [since],
        )
    else:
        cursor = conn.execute(
            """
            SELECT
                agent_type,
                COUNT(*) as call_count,
                SUM(total_tokens) as total_tokens,
                SUM(duration_ms) as total_duration_ms,
                AVG(total_tokens) as avg_tokens,
                AVG(duration_ms) as avg_duration_ms
            FROM subagent_calls
            GROUP BY agent_type
            ORDER BY total_tokens DESC
            """
        )
    return [dict(row) for row in cursor.fetchall()]


def has_context_tables(conn: sqlite3.Connection) -> bool:
    """Check if context tracking tables exist."""
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='sessions'
        """
    )
    return cursor.fetchone() is not None
