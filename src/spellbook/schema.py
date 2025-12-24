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
