"""Table extraction and cell-by-cell diffing."""

import logging
import uuid
from pathlib import Path

import pdfplumber

from specdiff.config import get_config
from specdiff.models import Change, ChangeKind, Location, TableData

logger = logging.getLogger(__name__)


def extract_tables(pdf_path: Path) -> list[TableData]:
    """Extract tables from PDF using pdfplumber."""
    config = get_config()

    if not config.tables.enable_table_diff:
        return []

    tables: list[TableData] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_tables = page.find_tables()

                for table_num, table in enumerate(page_tables):
                    # Extract table data
                    extracted = table.extract()

                    if not extracted:
                        continue

                    # Look for caption above table
                    caption = f"Table {len(tables) + 1}"
                    # Simple caption detection - look for "Table N" in text above
                    text_above = page.crop(
                        (table.bbox[0], max(0, table.bbox[1] - 50), table.bbox[2], table.bbox[1])
                    ).extract_text()

                    if text_above and "table" in text_above.lower():
                        caption = text_above.strip().split("\n")[-1]

                    tables.append(
                        TableData(
                            table_ref=caption,
                            page=page_num,
                            caption=caption,
                            rows=extracted,  # type: ignore[arg-type]
                            bbox=table.bbox,
                        )
                    )

        logger.info(f"Extracted {len(tables)} tables from {pdf_path.name}")
        return tables

    except Exception as e:
        logger.warning(f"Failed to extract tables from {pdf_path}: {e}")
        return []


def match_tables(
    old_tables: list[TableData], new_tables: list[TableData]
) -> list[tuple[TableData | None, TableData | None]]:
    """Match tables between versions by caption and position."""
    matched: list[tuple[TableData | None, TableData | None]] = []

    # Build caption index
    old_by_caption: dict[str, TableData] = {t.caption: t for t in old_tables}
    new_by_caption: dict[str, TableData] = {t.caption: t for t in new_tables}

    # Match by caption
    old_matched: set[str] = set()
    new_matched: set[str] = set()

    for caption in old_by_caption:
        if caption in new_by_caption:
            matched.append((old_by_caption[caption], new_by_caption[caption]))
            old_matched.add(caption)
            new_matched.add(caption)

    # Add unmatched tables
    for caption, table in old_by_caption.items():
        if caption not in old_matched:
            matched.append((table, None))

    for caption, table in new_by_caption.items():
        if caption not in new_matched:
            matched.append((None, table))

    return matched


def diff_table_cells(old_table: TableData, new_table: TableData) -> list[Change]:
    """Diff tables cell by cell."""
    changes: list[Change] = []

    old_rows = old_table.rows
    new_rows = new_table.rows

    # Check dimensions
    if len(old_rows) != len(new_rows):
        changes.append(
            Change(
                id=str(uuid.uuid4()),
                kind=ChangeKind.TABLE_CHANGE,
                location=Location(
                    page=new_table.page,
                    table_ref=new_table.table_ref,
                ),
                old_text=f"{len(old_rows)} rows",
                new_text=f"{len(new_rows)} rows",
                needs_manual_review=True,
            )
        )

    max_old_cols = max((len(row) for row in old_rows), default=0)
    max_new_cols = max((len(row) for row in new_rows), default=0)

    if max_old_cols != max_new_cols:
        changes.append(
            Change(
                id=str(uuid.uuid4()),
                kind=ChangeKind.TABLE_CHANGE,
                location=Location(
                    page=new_table.page,
                    table_ref=new_table.table_ref,
                ),
                old_text=f"{max_old_cols} columns",
                new_text=f"{max_new_cols} columns",
                needs_manual_review=True,
            )
        )

    # Compare cells
    min_rows = min(len(old_rows), len(new_rows))

    for row_idx in range(min_rows):
        old_row = old_rows[row_idx]
        new_row = new_rows[row_idx]
        min_cols = min(len(old_row), len(new_row))

        for col_idx in range(min_cols):
            old_cell = (old_row[col_idx] or "").strip()
            new_cell = (new_row[col_idx] or "").strip()

            if old_cell != new_cell:
                changes.append(
                    Change(
                        id=str(uuid.uuid4()),
                        kind=ChangeKind.TABLE_CHANGE,
                        location=Location(
                            page=new_table.page,
                            table_ref=new_table.table_ref,
                            cell_ref=f"R{row_idx + 1}C{col_idx + 1}",
                        ),
                        old_text=old_cell[:200],
                        new_text=new_cell[:200],
                    )
                )

    return changes


def compare_tables(
    old_pdf: Path, new_pdf: Path
) -> tuple[list[Change], int]:
    """
    Extract and compare tables between two PDFs.

    Returns list of table-specific changes and new table count.
    """
    logger.info("Comparing tables")

    old_tables = extract_tables(old_pdf)
    new_tables = extract_tables(new_pdf)

    matched = match_tables(old_tables, new_tables)
    all_changes: list[Change] = []

    for old_table, new_table in matched:
        if old_table and new_table:
            # Compare cells
            table_changes = diff_table_cells(old_table, new_table)
            all_changes.extend(table_changes)

        elif old_table and not new_table:
            # Table removed
            all_changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.TABLE_CHANGE,
                    location=Location(
                        page=old_table.page,
                        table_ref=old_table.table_ref,
                    ),
                    old_text=f"Table removed: {old_table.caption}",
                    new_text="",
                    needs_manual_review=True,
                )
            )

        elif new_table and not old_table:
            # Table added
            all_changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.TABLE_CHANGE,
                    location=Location(
                        page=new_table.page,
                        table_ref=new_table.table_ref,
                    ),
                    old_text="",
                    new_text=f"Table added: {new_table.caption}",
                    needs_manual_review=True,
                )
            )

    logger.info(f"Table comparison complete: {len(all_changes)} changes")
    return all_changes, len(new_tables)
