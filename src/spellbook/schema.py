"""Spellbook schema definitions using Pydantic."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# =============================================================================
# Document Types
# =============================================================================


class DocType(str, Enum):
    DECISION = "decision"
    INSIGHT = "insight"
    CODE = "code"
    REFERENCE = "reference"
    CONVERSATION = "conversation"
    ANALYSIS = "analysis"


# =============================================================================
# Entity Schema
# =============================================================================


class EntityType(str, Enum):
    PROJECT = "project"
    PERSON = "person"
    TOOL = "tool"
    REPO = "repo"
    CONCEPT = "concept"
    ORG = "org"


class EntityRef(BaseModel):
    """Entity reference embedded in a document."""

    name: str
    type: EntityType


class Entity(BaseModel):
    """Entity record in index.db."""

    type: EntityType
    refs: list[str]
    created: datetime
    last_mentioned: datetime


# =============================================================================
# Document Schema
# =============================================================================


class RelatedDoc(BaseModel):
    """Reference to another document."""

    id: str
    relationship: str


class ArchiveDoc(BaseModel):
    """A single knowledge document in log/."""

    id: str
    ts: datetime
    type: DocType
    title: str
    summary: str
    content: str
    entities: list[EntityRef]
    related_docs: list[RelatedDoc] = []
    tags: list[str] = []
    source_session: Optional[str] = None
    source_files: list[str] = []


# =============================================================================
# Buffer Schema
# =============================================================================


class BufferEntry(BaseModel):
    """Raw transcript awaiting processing."""

    ts: datetime
    session_id: Optional[str] = None
    transcript: str
    working_directory: Optional[str] = None
    files_touched: list[str] = []


# =============================================================================
# Config Schema
# =============================================================================


class SpellbookConfig(BaseModel):
    """Stored in .spellbook file."""

    version: str
    vault_dir: str
    created: datetime
    last_updated: datetime


# =============================================================================
# Context/Usage Tracking Schema
# =============================================================================


class SessionUsage(BaseModel):
    """Session-level token usage summary."""

    id: str  # Session UUID
    vault_path: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation: int = 0
    total_cache_read: int = 0
    total_messages: int = 0
    slug: Optional[str] = None  # Human-readable session name


class SubagentCall(BaseModel):
    """Token usage for a single subagent invocation."""

    session_id: str
    agent_id: str  # Short hex ID (e.g., "afb88bb")
    agent_type: str  # "Archivist", "Backend", etc.
    description: Optional[str] = None
    prompt_preview: Optional[str] = None  # First 200 chars of prompt
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    total_tokens: int = 0
    tool_use_count: int = 0
    status: str = "running"  # running, completed, failed
