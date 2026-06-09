"""Figure detection and manual review flagging."""

import logging
import uuid
from pathlib import Path

import fitz

from specdiff.config import get_config
from specdiff.models import Change, ChangeKind, Location, PageInfo

logger = logging.getLogger(__name__)


def analyze_pages(pdf_path: Path) -> list[PageInfo]:
    """
    Analyze each page for figure content.

    Returns page info with text density and image counts.
    """
    config = get_config()
    pages: list[PageInfo] = []

    try:
        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc):
            # Get text and count characters
            text = page.get_text()
            text_density = len(text.strip())

            # Count images
            image_count = len(page.get_images())

            # Determine if figure-heavy
            is_figure_heavy = (
                text_density < config.figures.text_density_threshold or image_count > 2
            )

            pages.append(
                PageInfo(
                    page_num=page_num,
                    text_density=text_density,
                    image_count=image_count,
                    is_figure_heavy=is_figure_heavy,
                )
            )

        doc.close()
        logger.info(f"Analyzed {len(pages)} pages from {pdf_path.name}")
        return pages

    except Exception as e:
        logger.error(f"Failed to analyze pages in {pdf_path}: {e}")
        return []


def detect_figure_changes(
    old_pdf: Path, new_pdf: Path
) -> tuple[list[Change], list[int]]:
    """
    Detect pages with figures that may have changed.

    Returns figure-flag changes and list of pages needing manual review.
    """
    config = get_config()
    logger.info("Detecting figure changes")

    old_pages = analyze_pages(old_pdf)
    new_pages = analyze_pages(new_pdf)

    changes: list[Change] = []
    manual_review_pages: list[int] = []

    # Compare page counts
    if len(old_pages) != len(new_pages):
        changes.append(
            Change(
                id=str(uuid.uuid4()),
                kind=ChangeKind.FIGURE_FLAG,
                location=Location(page=0),
                old_text=f"Document had {len(old_pages)} pages",
                new_text=f"Document now has {len(new_pages)} pages",
                needs_manual_review=True,
            )
        )

    # Compare each page
    min_pages = min(len(old_pages), len(new_pages))

    for page_num in range(min_pages):
        old_page = old_pages[page_num]
        new_page = new_pages[page_num]

        # Check for image count changes
        image_change = abs(old_page.image_count - new_page.image_count)

        # Flag if:
        # 1. Image count changed beyond threshold
        # 2. Either version is figure-heavy (sparse text)
        needs_flag = (
            image_change >= config.figures.image_count_change_threshold
            or old_page.is_figure_heavy
            or new_page.is_figure_heavy
        )

        if needs_flag:
            changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.FIGURE_FLAG,
                    location=Location(page=page_num),
                    old_text=(
                        f"Page {page_num + 1}: {old_page.image_count} images, "
                        f"{old_page.text_density:.0f} chars"
                    ),
                    new_text=(
                        f"Page {page_num + 1}: {new_page.image_count} images, "
                        f"{new_page.text_density:.0f} chars"
                    ),
                    needs_manual_review=True,
                )
            )
            manual_review_pages.append(page_num)

    # Check pages that exist in only one version
    if len(new_pages) > len(old_pages):
        for page_num in range(len(old_pages), len(new_pages)):
            changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.FIGURE_FLAG,
                    location=Location(page=page_num),
                    old_text="",
                    new_text=f"New page {page_num + 1} added",
                    needs_manual_review=True,
                )
            )
            manual_review_pages.append(page_num)

    elif len(old_pages) > len(new_pages):
        for page_num in range(len(new_pages), len(old_pages)):
            changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.FIGURE_FLAG,
                    location=Location(page=page_num),
                    old_text=f"Page {page_num + 1} existed",
                    new_text="",
                    needs_manual_review=True,
                )
            )

    logger.info(
        f"Figure detection complete: {len(changes)} flags, "
        f"{len(manual_review_pages)} pages need review"
    )

    return changes, manual_review_pages
