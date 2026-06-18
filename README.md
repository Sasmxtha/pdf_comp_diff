# spec-diff

Production-grade, fully offline, CPU-only desktop tool for comparing revisions of specification PDFs. Detects every change deterministically between two versions of standards (API, ASTM, ISO, ASME, BIS, SAE, etc.) with complete, auditable change lists.

## Features

- **Deterministic Change Detection**: Uses Myers diff algorithm for complete, reproducible change lists
- **Fully Offline**: Zero network calls, guaranteed privacy, works on air-gapped systems
- **CPU-Only**: Runs on standard laptops, no GPU required
- **Hierarchical Diff**: Two-level algorithm handles clause renumbering and word-level changes
- **Table-Aware**: Cell-by-cell comparison of tables
- **Figure Safeguards**: Detects and flags pages with images/figures for manual review
- **Multiple Export Formats**: JSON, HTML redline, Word with tracked changes

## Offline Guarantee

The core engine makes ZERO network calls. All processing is local:
- PDF parsing: PyMuPDF (local)
- Diff algorithm: diff-match-patch (local)
- Table extraction: pdfplumber (local)
- No telemetry, no API calls, no data leaves your machine


## Installation

Requires Python 3.11+

```bash
# Install from source
git clone https://github.com/Sasmxtha/pdf_comp_diff
cd spec-diff
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Usage

### Command Line

```bash
# Basic comparison
specdiff old_version.pdf new_version.pdf

# Specify output directory
specdiff old.pdf new.pdf -o reports/

# Custom config
specdiff old.pdf new.pdf -c myconfig.toml

# Verbose logging
specdiff old.pdf new.pdf -v
```

### Outputs

- `comparison.pdf`: Printable redline report
- `comparison.docx`: Word document with tracked-changes style markup

### Python API

```python
from pathlib import Path
from specdiff.engine import compare_pdfs
from specdiff.report import export_all

# Compare PDFs
result = compare_pdfs(
    Path("old_version.pdf"),
    Path("new_version.pdf")
)

# Access changes
for change in result.changes:
    print(f"{change.kind}: {change.location.clause_id}")
    print(f"  Old: {change.old_text[:100]}")
    print(f"  New: {change.new_text[:100]}")

# Export reports (PDF + DOCX)
export_all(result, Path("output/"))
```

## Configuration

Edit `config.toml` to adjust behavior:

```toml
[extraction]
# Header/footer detection sensitivity
repetition_threshold = 3

[diff]
# Word tokenization and matching
match_threshold = 0.5

[figures]
# Text density below which page is considered figure-heavy
text_density_threshold = 100

[tables]
# Enable table extraction and diffing
enable_table_diff = true
```

Environment overrides:
- `SPECDIFF_LLM_ENABLE=true`: Enable optional LLM categorization
- `SPECDIFF_LOG_LEVEL=DEBUG`: Set log level

## How It Works

### Two-Level Hierarchical Diff

**Level 1: Structural Alignment**
- Segments documents into clauses using numbering patterns (1, 1.1, A.1, etc.)
- Aligns segments by clause ID, handles renumbering gracefully
- Uses hash-based sequence alignment for unnumbered sections

**Level 2: Word-Level Diff**
- For modified segments, performs word-tokenized diff
- Uses diff-match-patch (Myers O(ND) algorithm)
- Semantic cleanup merges trivial edits into meaningful chunks

### Header/Footer Removal

- Detects text that repeats at same position across multiple pages
- Removes before diffing to avoid false positives
- Configurable margin bands and repetition threshold

### Table Diffing

- Extracts tables with pdfplumber
- Matches by caption and position
- Compares cell-by-cell, reports row/column changes
- Flags dimension changes for review

### Figure Detection

- Counts images per page
- Measures text density
- Flags pages where images changed or text is sparse
- **Never silently misses figure changes** - always flags for manual review

## Limitations

This tool is designed for **born-digital text PDFs** (specifications, standards documents). It does not handle:

- **Scanned PDFs**: OCR required first
- **CAD drawings**: Not text-based
- **Changes inside figures/images**: These are **detected and flagged** but not diffed
- **Complex layouts**: Tables with merged cells may not extract perfectly

When the tool cannot fully diff content (figures, complex tables), it explicitly **flags those pages for manual review**. You will never get an incomplete report without warnings.

## Optional: LLM Categorization

The core diff is deterministic. Optionally, changes can be categorized as "editorial" vs "technical" using a local LLM:

1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama3.2:3b`
3. Enable in config:

```toml
[llm]
enable = true
model = "llama3.2:3b"
base_url = "http://localhost:11434"
```

**This is localhost-only. No data leaves your machine.**

## API Server

Run the FastAPI backend:

```bash
# Start server
uvicorn api.main:app --reload
```

API endpoints:
- `POST /compare`: Upload two PDFs
- `GET /jobs/{id}`: Check progress
- `GET /result/{id}`: Get changes
- `GET /export/{id}?format=pdf`: Download report

See `api/README.md` for details.

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=specdiff --cov-report=html

# Type checking
mypy specdiff/

# Linting
ruff check .
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run type checker
mypy specdiff/ api/

# Format and lint
ruff check --fix .
ruff format .

# Run tests
pytest -v
```

## Performance

Tested on 300+ page specifications:
- Extraction: ~1-2 seconds per document
- Diff: ~2-5 seconds (depends on change density)
- Total: ~5-10 seconds for typical standard revision

Caches extraction by file hash, so re-comparing same files is instant.

## License

MIT

## Credits

- [PyMuPDF](https://pymupdf.readthedocs.io/): PDF parsing
- [diff-match-patch](https://github.com/google/diff-match-patch): Myers diff algorithm
- [pdfplumber](https://github.com/jsvine/pdfplumber): Table extraction
- [FastAPI](https://fastapi.tiangolo.com/): API framework
