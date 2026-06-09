"""spec-diff: Production-grade offline PDF specification comparison tool."""

__version__ = "0.1.0"

from specdiff.models import Change, ChangeKind, ComparisonResult, Location

__all__ = ["Change", "ChangeKind", "ComparisonResult", "Location", "__version__"]
