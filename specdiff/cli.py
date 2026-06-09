"""Command-line interface for spec-diff."""

import argparse
import logging
import sys
from pathlib import Path

from specdiff import __version__
from specdiff.config import get_config
from specdiff.engine import compare_pdfs
from specdiff.report import export_all

logger = logging.getLogger(__name__)


def prompt_pdf(label: str) -> Path:
    """Ask the user for a PDF path, validate it exists and is a PDF."""
    while True:
        raw = input(f"Enter {label} path: ").strip().strip('"')
        if not raw:
            print("  Path cannot be empty. Try again.")
            continue
        path = Path(raw)
        if not path.exists():
            print(f"  File not found: {path}. Try again.")
            continue
        if path.suffix.lower() != ".pdf":
            print(f"  Not a PDF file: {path}. Try again.")
            continue
        return path


def prompt_output_dir() -> Path:
    """Ask the user where to save the output files."""
    while True:
        raw = input("Enter output folder path (or press Enter for ./output): ").strip().strip('"')
        if not raw:
            return Path("output")
        path = Path(raw)
        if not path.exists():
            confirm = input(f"  '{path}' does not exist. Create it? [Y/n]: ").strip().lower()
            if confirm in ("", "y", "yes"):
                return path
            # Otherwise ask again
        else:
            return path


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="specdiff",
        description="Compare two revisions of a specification PDF and detect all changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (no arguments — prompts for all inputs)
  specdiff

  # Non-interactive mode
  specdiff old.pdf new.pdf -o reports/
        """,
    )

    parser.add_argument("old_pdf", type=Path, nargs="?", default=None, help="Path to old version PDF (optional, will prompt if omitted)")
    parser.add_argument("new_pdf", type=Path, nargs="?", default=None, help="Path to new version PDF (optional, will prompt if omitted)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory for reports (optional, will prompt if omitted)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to config.toml file (default: ./config.toml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"spec-diff {__version__}",
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        from specdiff.config import Config
        config = Config.load(args.config)
        config.setup_logging()
    else:
        config = get_config()

    # Override log level if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print(f"\nspec-diff v{__version__} — PDF Comparison Tool")
    print("-" * 50)

    # Prompt for inputs not supplied as arguments
    if args.old_pdf is None:
        old_pdf = prompt_pdf("old PDF")
    else:
        old_pdf = args.old_pdf
        if not old_pdf.exists():
            print(f"Error: Old PDF not found: {old_pdf}")
            return 1
        if old_pdf.suffix.lower() != ".pdf":
            print(f"Error: Not a PDF: {old_pdf}")
            return 1

    if args.new_pdf is None:
        new_pdf = prompt_pdf("new PDF")
    else:
        new_pdf = args.new_pdf
        if not new_pdf.exists():
            print(f"Error: New PDF not found: {new_pdf}")
            return 1
        if new_pdf.suffix.lower() != ".pdf":
            print(f"Error: Not a PDF: {new_pdf}")
            return 1

    output_dir = args.output if args.output is not None else prompt_output_dir()

    try:
        print(f"\nComparing:  {old_pdf.name}  ->  {new_pdf.name}")
        print(f"Output to:  {output_dir.absolute()}\n")

        logger.info(f"Comparing: {old_pdf} -> {new_pdf}")
        result = compare_pdfs(old_pdf, new_pdf)

        logger.info(f"Exporting results to {output_dir}")
        export_all(result, output_dir)

        # Summary
        print("\n" + "=" * 70)
        print("COMPARISON COMPLETE")
        print("=" * 70)
        print(f"\nTotal changes detected: {len(result.changes)}")
        print(f"  - Insertions:    {result.summary.insertions}")
        print(f"  - Deletions:     {result.summary.deletions}")
        print(f"  - Modifications: {result.summary.modifications}")
        print(f"  - Table changes: {result.summary.table_changes}")
        print(f"  - Figure flags:  {result.summary.figure_flags}")
        print(f"\nPages changed: {len(result.summary.pages_changed)}")

        if result.manual_review_pages:
            print(f"\n  {len(result.manual_review_pages)} pages require manual review (figures/images)")

        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")

        print(f"\nReports saved to: {output_dir.absolute()}")
        print("  - comparison.pdf  (printable report)")
        print("  - comparison.docx (Word with tracked changes)")

        return 0

    except Exception as e:
        logger.exception(f"Comparison failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())



if __name__ == "__main__":
    sys.exit(main())
