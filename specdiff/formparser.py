"""
Form-aware parser for structured part-report / BOM PDFs (TechnipFMC style).

Extracts:
  - Header fields  (PART NUMBER, REVISION, DESCRIPTION, etc.)
  - BOM rows       (ITEM, PART NUMBER, DESCRIPTION, DWG NUMBER, UOM, QTY, MATERIAL)
  - Document sections (DOCUMENTS LIST entries)
  - Notes

These are compared field-by-field and row-by-row instead of word-soup diffs.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from specdiff.models import Change, ChangeKind, Location

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class BomRow:
    item: str
    part_number: str
    description: str
    dwg_number: str
    uom: str
    qty: str
    material: str
    page: int

    def key(self) -> str:
        return self.item.strip()

    def to_display(self) -> str:
        parts = []
        if self.part_number:
            parts.append(f"P/N: {self.part_number}")
        if self.description:
            parts.append(f"DESC: {self.description}")
        if self.qty:
            parts.append(f"QTY: {self.qty}")
        if self.material:
            parts.append(f"MAT: {self.material}")
        return "  |  ".join(parts)


@dataclass
class DocEntry:
    doc_number: str
    description: str
    page: int

    def key(self) -> str:
        return self.doc_number.strip()


@dataclass
class ParsedPartReport:
    header: dict[str, str] = field(default_factory=dict)
    bom_rows: list[BomRow] = field(default_factory=list)
    doc_entries: list[DocEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_sections: dict[str, str] = field(default_factory=dict)


# ── Extraction helpers ─────────────────────────────────────────────────────────

def _get_pages_text(pdf_path: Path) -> list[tuple[int, str]]:
    """Return list of (page_num, text) for each page."""
    doc = fitz.open(pdf_path)
    result = []
    for i, page in enumerate(doc):
        result.append((i, page.get_text()))
    doc.close()
    return result


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ── Header field extraction ────────────────────────────────────────────────────

_HEADER_PATTERNS = [
    ("PART NUMBER",     r"PART\s+NUMBER\s*[:\-]?\s*(\S+)"),
    ("REVISION",        r"REVISION\s*[:\-]?\s*([A-Z0-9]+)"),
    ("ECN",             r"ECN\s*[:\-]?\s*(\d+)"),
    ("DRAWING NO",      r"DRAWING\s+NO\s*[:\-]?\s*(\S+)"),
    ("DRAWING REV",     r"DRAWING\s+REV\s*[:\-]?\s*([A-Z0-9]+)"),
    ("DWG OWN",         r"DWG\s+OWN\s*[:\-]?\s*(\S+\s*\S*)"),
    ("TYPE",            r"TYPE\s*:\s*([A-Z])"),
    ("STATUS",          r"STATUS\s*:\s*(\w+)"),
    ("UOM",             r"UOM\s*:\s*(\w+)"),
    ("WEIGHT",          r"WEIGHT\s*:\s*([\d\.]+\s*\([\d\.]+\))"),
    ("PROD SPEC",       r"PROD\s+SPEC\s*[:\-]?\s*(.+?)(?:\n|$)"),
    ("REPORT BY",       r"REPORT\s+BY\s*[:\-]?\s*(.+?)\s{3,}"),
    ("REPORT DATE",     r"(?:REPORT\s+BY.*?)\s{3,}(\d{1,2}-[A-Z]+-\d{4})"),
]


def _extract_header(full_text: str) -> dict[str, str]:
    header: dict[str, str] = {}
    for name, pattern in _HEADER_PATTERNS:
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            header[name] = _clean(m.group(1))
    # Description: text between part-number line and the dashes
    m = re.search(
        r"(?:PART\s+NUMBER.*?DRAWING\s+NO.*?\n)(.*?)(?=\nREVISION|\nECN|\n_{5})",
        full_text, re.DOTALL | re.IGNORECASE,
    )
    if m:
        header["DESCRIPTION"] = _clean(m.group(1))
    return header


# ── BOM row extraction ─────────────────────────────────────────────────────────

# Matches lines like:  "1     P178142     GV BONNET CAP...   2009DU1110971   EA  1   E55512"
_BOM_ITEM_RE = re.compile(
    r"^\s*(\d+)\s{2,}(\S+)\s{2,}(.+?)\s{2,}(\S+)\s{2,}(\w+)\s{1,}(\d+(?:\.\d+)?)\s{1,}(\S+)\s*$"
)
# Continuation line starts with spaces (no item number at start)
_CONTINUATION_RE = re.compile(r"^\s{10,}(.+)$")


def _extract_bom(pages_text: list[tuple[int, str]]) -> list[BomRow]:
    """
    Parse BOM section rows from the full text.
    Handles multi-line description continuations.
    """
    rows: list[BomRow] = []
    in_bom = False
    current_row: BomRow | None = None

    for page_num, text in pages_text:
        for line in text.splitlines():
            # Detect BOM header
            if re.search(r"BILL\s+OF\s+MATERIAL", line, re.IGNORECASE):
                in_bom = True
                continue
            if re.search(r"DOCUMENTS\s+LIST|END\s+OF\s+PART|ENGINEERING\s+DOCUMENTS", line, re.IGNORECASE):
                in_bom = False
                if current_row:
                    rows.append(current_row)
                    current_row = None
                continue

            if not in_bom:
                continue

            # Try to match a BOM item row
            m = _BOM_ITEM_RE.match(line)
            if m:
                if current_row:
                    rows.append(current_row)
                current_row = BomRow(
                    item=m.group(1),
                    part_number=m.group(2),
                    description=_clean(m.group(3)),
                    dwg_number=m.group(4),
                    uom=m.group(5),
                    qty=m.group(6),
                    material=m.group(7),
                    page=page_num,
                )
                continue

            # Continuation of description
            cm = _CONTINUATION_RE.match(line)
            if cm and current_row:
                extra = _clean(cm.group(1))
                if extra and not re.match(r"[-_]{5,}", extra):
                    current_row.description += " " + extra

    if current_row:
        rows.append(current_row)

    logger.info(f"Extracted {len(rows)} BOM rows")
    return rows


# ── Document entry extraction ──────────────────────────────────────────────────

_DOC_ENTRY_RE = re.compile(r"^\s*([A-Z0-9]{6,})\s{3,}(.+)$")


def _extract_doc_entries(pages_text: list[tuple[int, str]]) -> list[DocEntry]:
    entries: list[DocEntry] = []
    in_docs = False

    for page_num, text in pages_text:
        for line in text.splitlines():
            if re.search(r"DOCUMENTS\s+LIST", line, re.IGNORECASE):
                in_docs = True
                continue
            if re.search(r"END\s+OF\s+PART|BILL\s+OF\s+MATERIAL", line, re.IGNORECASE):
                in_docs = False
                continue
            if not in_docs:
                continue
            m = _DOC_ENTRY_RE.match(line)
            if m:
                entries.append(DocEntry(
                    doc_number=m.group(1),
                    description=_clean(m.group(2)),
                    page=page_num,
                ))

    logger.info(f"Extracted {len(entries)} document entries")
    return entries


# ── Note extraction ────────────────────────────────────────────────────────────

_NOTE_RE = re.compile(r"^NOTE\d+\s+(.*)", re.IGNORECASE)


def _extract_notes(pages_text: list[tuple[int, str]]) -> list[str]:
    notes = []
    current_note: str | None = None

    for _, text in pages_text:
        for line in text.splitlines():
            m = _NOTE_RE.match(line.strip())
            if m:
                if current_note:
                    notes.append(_clean(current_note))
                current_note = m.group(1)
            elif current_note and line.strip() and not re.match(r"[-_*=]{3,}", line.strip()):
                current_note += " " + line.strip()

    if current_note:
        notes.append(_clean(current_note))

    return notes


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_part_report(pdf_path: Path) -> ParsedPartReport:
    """Parse a TechnipFMC-style part report PDF into structured data."""
    pages_text = _get_pages_text(pdf_path)
    full_text = "\n".join(t for _, t in pages_text)

    report = ParsedPartReport()
    report.header = _extract_header(full_text)
    report.bom_rows = _extract_bom(pages_text)
    report.doc_entries = _extract_doc_entries(pages_text)
    report.notes = _extract_notes(pages_text)

    logger.info(
        f"Parsed {pdf_path.name}: header={len(report.header)} fields, "
        f"bom={len(report.bom_rows)} rows, docs={len(report.doc_entries)}, "
        f"notes={len(report.notes)}"
    )
    return report


# ── Diff logic ─────────────────────────────────────────────────────────────────

def _make_change(kind: ChangeKind, page: int, section: str,
                 old: str, new: str, cell: str | None = None) -> Change:
    return Change(
        id=str(uuid.uuid4()),
        kind=kind,
        location=Location(clause_id=section, page=page, cell_ref=cell),
        old_text=old,
        new_text=new,
    )


def diff_part_reports(old: ParsedPartReport, new: ParsedPartReport) -> list[Change]:
    """Diff two parsed part reports into a clean change list."""
    changes: list[Change] = []

    # ── 1. Header fields ──────────────────────────────────────────────────────
    all_keys = set(old.header) | set(new.header)
    for key in sorted(all_keys):
        ov = old.header.get(key, "")
        nv = new.header.get(key, "")
        if ov == nv:
            continue
        if not ov:
            changes.append(_make_change(ChangeKind.INSERTION, 0, f"Header / {key}", "", nv))
        elif not nv:
            changes.append(_make_change(ChangeKind.DELETION, 0, f"Header / {key}", ov, ""))
        else:
            changes.append(_make_change(ChangeKind.MODIFICATION, 0, f"Header / {key}", ov, nv))

    # ── 2. BOM rows ───────────────────────────────────────────────────────────
    old_bom = {r.key(): r for r in old.bom_rows}
    new_bom = {r.key(): r for r in new.bom_rows}
    all_items = sorted(set(old_bom) | set(new_bom), key=lambda x: int(x) if x.isdigit() else 0)

    for item in all_items:
        ov = old_bom.get(item)
        nv = new_bom.get(item)

        if ov and not nv:
            changes.append(_make_change(
                ChangeKind.DELETION, ov.page, f"BOM / Item {item}",
                ov.to_display(), "",
            ))
        elif nv and not ov:
            changes.append(_make_change(
                ChangeKind.INSERTION, nv.page, f"BOM / Item {item}",
                "", nv.to_display(),
            ))
        elif ov and nv:
            # Compare each column
            fields = [
                ("Part Number", ov.part_number, nv.part_number),
                ("Description", ov.description, nv.description),
                ("DWG Number",  ov.dwg_number,  nv.dwg_number),
                ("UOM",         ov.uom,          nv.uom),
                ("QTY",         ov.qty,          nv.qty),
                ("Material",    ov.material,     nv.material),
            ]
            for fname, oval, nval in fields:
                if _clean(oval) != _clean(nval):
                    changes.append(_make_change(
                        ChangeKind.MODIFICATION, nv.page,
                        f"BOM / Item {item}", oval, nval, cell=fname,
                    ))

    # ── 3. Document entries ───────────────────────────────────────────────────
    old_docs = {e.key(): e for e in old.doc_entries}
    new_docs = {e.key(): e for e in new.doc_entries}
    all_docs = set(old_docs) | set(new_docs)

    for doc_num in sorted(all_docs):
        ov = old_docs.get(doc_num)
        nv = new_docs.get(doc_num)
        if ov and not nv:
            changes.append(_make_change(
                ChangeKind.DELETION, ov.page, "Documents List",
                f"{doc_num}: {ov.description}", "",
            ))
        elif nv and not ov:
            changes.append(_make_change(
                ChangeKind.INSERTION, nv.page, "Documents List",
                "", f"{doc_num}: {nv.description}",
            ))
        elif ov and nv and _clean(ov.description) != _clean(nv.description):
            changes.append(_make_change(
                ChangeKind.MODIFICATION, nv.page, "Documents List",
                f"{doc_num}: {ov.description}", f"{doc_num}: {nv.description}",
            ))

    # ── 4. Notes ─────────────────────────────────────────────────────────────
    old_notes = set(old.notes)
    new_notes = set(new.notes)
    for note in sorted(new_notes - old_notes):
        changes.append(_make_change(ChangeKind.INSERTION, 0, "Notes", "", note))
    for note in sorted(old_notes - new_notes):
        changes.append(_make_change(ChangeKind.DELETION, 0, "Notes", note, ""))

    logger.info(f"Form diff complete: {len(changes)} changes")
    return changes
