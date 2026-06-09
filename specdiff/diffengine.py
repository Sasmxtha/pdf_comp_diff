"""Hierarchical diff engine using Myers algorithm via diff-match-patch."""

import logging
import re
import uuid
from typing import Any

import diff_match_patch as dmp_module

from specdiff.config import get_config
from specdiff.models import Change, ChangeKind, Location, Segment

logger = logging.getLogger(__name__)


class DiffEngine:
    """Two-level hierarchical diff: structural + word-level."""

    def __init__(self) -> None:
        self.dmp = dmp_module.diff_match_patch()
        self.config = get_config()

    def align_segments(
        self, old_segments: list[Segment], new_segments: list[Segment]
    ) -> list[tuple[Segment | None, Segment | None, str]]:
        """
        Align segments between old and new versions.

        Returns list of (old_seg, new_seg, status) where status is:
        - 'matched': segments correspond (possibly modified)
        - 'added': new segment not in old
        - 'removed': old segment not in new

        Uses clause_id for matching when available, otherwise position + hash.
        """
        results: list[tuple[Segment | None, Segment | None, str]] = []

        # Build clause_id maps
        old_by_clause: dict[str, Segment] = {}
        new_by_clause: dict[str, Segment] = {}

        for seg in old_segments:
            if seg.clause_id:
                old_by_clause[seg.clause_id] = seg

        for seg in new_segments:
            if seg.clause_id:
                new_by_clause[seg.clause_id] = seg

        # Track which segments we've matched
        old_matched: set[int] = set()
        new_matched: set[int] = set()

        # Phase 1: Match by clause_id
        for clause_id in old_by_clause:
            if clause_id in new_by_clause:
                old_seg = old_by_clause[clause_id]
                new_seg = new_by_clause[clause_id]
                old_idx = old_segments.index(old_seg)
                new_idx = new_segments.index(new_seg)
                old_matched.add(old_idx)
                new_matched.add(new_idx)
                results.append((old_seg, new_seg, "matched"))

        # Phase 2: Match remaining segments by position + hash similarity
        old_unmatched = [i for i in range(len(old_segments)) if i not in old_matched]
        new_unmatched = [i for i in range(len(new_segments)) if i not in new_matched]

        # Use diff-match-patch on hashes for sequence alignment
        if old_unmatched or new_unmatched:
            # Create hash sequences
            old_hashes = "".join(
                chr(65 + (i % 26)) for i in old_unmatched  # Map to letters
            )
            new_hashes = "".join(chr(65 + (i % 26)) for i in new_unmatched)

            diffs = self.dmp.diff_main(old_hashes, new_hashes)
            self.dmp.diff_cleanupSemantic(diffs)

            old_pos = 0
            new_pos = 0

            for op, data in diffs:
                length = len(data)

                if op == 0:  # Equal - matched
                    for _ in range(length):
                        if old_pos < len(old_unmatched) and new_pos < len(new_unmatched):
                            old_idx = old_unmatched[old_pos]
                            new_idx = new_unmatched[new_pos]
                            results.append(
                                (old_segments[old_idx], new_segments[new_idx], "matched")
                            )
                            old_pos += 1
                            new_pos += 1

                elif op == -1:  # Delete
                    for _ in range(length):
                        if old_pos < len(old_unmatched):
                            old_idx = old_unmatched[old_pos]
                            results.append((old_segments[old_idx], None, "removed"))
                            old_pos += 1

                elif op == 1:  # Insert
                    for _ in range(length):
                        if new_pos < len(new_unmatched):
                            new_idx = new_unmatched[new_pos]
                            results.append((None, new_segments[new_idx], "added"))
                            new_pos += 1

        # Sort by original position
        results.sort(key=lambda x: (x[0].position if x[0] else x[1].position if x[1] else 0))

        logger.info(
            f"Aligned {len(results)} segment pairs: "
            f"{sum(1 for r in results if r[2] == 'matched')} matched, "
            f"{sum(1 for r in results if r[2] == 'added')} added, "
            f"{sum(1 for r in results if r[2] == 'removed')} removed"
        )

        return results

    def word_diff(self, old_text: str, new_text: str) -> list[Change]:
        """
        Perform word-level diff on matched segments.

        Uses diff-match-patch with word tokenization for semantic chunks.
        """
        changes: list[Change] = []

        # Tokenize into words
        word_pattern = re.compile(self.config.diff.word_pattern)
        old_words = word_pattern.findall(old_text)
        new_words = word_pattern.findall(new_text)

        # Hash words to characters for efficient diff
        word_to_char: dict[str, str] = {}
        char_to_word: dict[str, str] = {}
        next_char = 33  # Start at '!'

        def get_char(word: str) -> str:
            nonlocal next_char
            if word not in word_to_char:
                char = chr(next_char)
                word_to_char[word] = char
                char_to_word[char] = word
                next_char += 1
                if next_char > 126:  # Reset if we run out of printable chars
                    next_char = 33
            return word_to_char[word]

        old_str = "".join(get_char(w) for w in old_words)
        new_str = "".join(get_char(w) for w in new_words)

        # Run diff
        diffs = self.dmp.diff_main(old_str, new_str)
        self.dmp.diff_cleanupSemantic(diffs)

        # Convert back to words and create Change objects
        for op, data in diffs:
            words = [char_to_word.get(c, c) for c in data]
            text = " ".join(words)

            if op == -1:  # Deletion
                if text.strip():
                    changes.append(
                        Change(
                            id=str(uuid.uuid4()),
                            kind=ChangeKind.DELETION,
                            location=Location(page=0),  # Will be filled by caller
                            old_text=text,
                            new_text="",
                        )
                    )
            elif op == 1:  # Insertion
                if text.strip():
                    changes.append(
                        Change(
                            id=str(uuid.uuid4()),
                            kind=ChangeKind.INSERTION,
                            location=Location(page=0),
                            old_text="",
                            new_text=text,
                        )
                    )

        return changes

    def diff_segments(
        self, old_segment: Segment | None, new_segment: Segment | None, status: str
    ) -> list[Change]:
        """Create changes from a segment pair."""
        changes: list[Change] = []

        if status == "removed" and old_segment:
            # Entire segment deleted
            changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.DELETION,
                    location=Location(
                        clause_id=old_segment.clause_id,
                        page=old_segment.page_start,
                    ),
                    old_text=old_segment.text[:500],  # Limit for readability
                    new_text="",
                    confidence=1.0,
                )
            )

        elif status == "added" and new_segment:
            # Entire segment added
            changes.append(
                Change(
                    id=str(uuid.uuid4()),
                    kind=ChangeKind.INSERTION,
                    location=Location(
                        clause_id=new_segment.clause_id,
                        page=new_segment.page_start,
                    ),
                    old_text="",
                    new_text=new_segment.text[:500],
                    confidence=1.0,
                )
            )

        elif status == "matched" and old_segment and new_segment:
            # Check if content changed
            if old_segment.text_hash != new_segment.text_hash:
                # Perform word-level diff
                word_changes = self.word_diff(old_segment.text, new_segment.text)

                # Update location info
                for change in word_changes:
                    change.location.clause_id = new_segment.clause_id or old_segment.clause_id
                    change.location.page = new_segment.page_start
                    change.kind = ChangeKind.MODIFICATION

                changes.extend(word_changes)

        return changes

    def compare(
        self, old_segments: list[Segment], new_segments: list[Segment]
    ) -> list[Change]:
        """
        Compare two segmented documents and generate change list.

        Returns complete list of deterministically detected changes.
        """
        logger.info("Starting hierarchical diff")

        # Level 1: Structural alignment
        aligned = self.align_segments(old_segments, new_segments)

        # Level 2: Word-level diff for modified segments
        all_changes: list[Change] = []

        for old_seg, new_seg, status in aligned:
            segment_changes = self.diff_segments(old_seg, new_seg, status)
            all_changes.extend(segment_changes)

        logger.info(f"Diff complete: {len(all_changes)} changes detected")
        return all_changes
