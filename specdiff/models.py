"""Core data models for spec-diff."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChangeKind(str, Enum):
    """Type of change detected."""

    INSERTION = "insertion"
    DELETION = "deletion"
    MODIFICATION = "modification"
    TABLE_CHANGE = "table_change"
    FIGURE_FLAG = "figure_flag"


class ChangeCategory(str, Enum):
    """Semantic category of change (optional LLM classification)."""

    EDITORIAL = "editorial"
    TECHNICAL = "technical"
    UNKNOWN = "unknown"


class Location(BaseModel):
    """Location of a change in the document."""

    clause_id: str | None = None
    page: int
    table_ref: str | None = None
    cell_ref: str | None = None


class Change(BaseModel):
    """A single detected change between document versions."""

    id: str
    kind: ChangeKind
    location: Location
    old_text: str = ""
    new_text: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    category: ChangeCategory = ChangeCategory.UNKNOWN
    needs_manual_review: bool = False


class DocumentMetadata(BaseModel):
    """Metadata about a processed document."""

    page_count: int
    clause_count: int
    table_count: int
    figure_count: int
    file_hash: str


class ComparisonSummary(BaseModel):
    """Summary statistics of comparison."""

    insertions: int = 0
    deletions: int = 0
    modifications: int = 0
    table_changes: int = 0
    figure_flags: int = 0
    pages_changed: list[int] = Field(default_factory=list)
    editorial_count: int = 0
    technical_count: int = 0


class ComparisonResult(BaseModel):
    """Complete result of comparing two documents."""

    old_metadata: DocumentMetadata
    new_metadata: DocumentMetadata
    changes: list[Change]
    summary: ComparisonSummary
    manual_review_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    """A structural segment (clause/section) of a document."""

    clause_id: str | None = None
    title: str = ""
    page_start: int
    page_end: int
    text: str
    text_hash: str = ""
    position: int = 0  # Order in document


class TableData(BaseModel):
    """Extracted table data."""

    table_ref: str
    page: int
    caption: str = ""
    rows: list[list[str]] = Field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None


class PageInfo(BaseModel):
    """Information about a page for figure detection."""

    page_num: int
    text_density: float
    image_count: int
    is_figure_heavy: bool = False
