"""Checks and stores data received from the extension.

The browser page is untrusted input. These data classes normalise its values,
apply limits and ensure the rest of the engine receives a stable structure.
"""


from dataclasses import dataclass, field
from typing import Any


# Separate exception type lets the HTTP layer return status 400 for invalid
# input while treating unrelated programming failures as status 500.
class InputValidationError(ValueError):
    """Used when the extension sends invalid input."""


# Dataclass generates the constructor and readable representation. Metadata is
# retained even though the current score primarily analyses comment text.
@dataclass
class Comment:
    text: str
    author: str | None = None
    score: int | None = None
    depth: int | None = None

    # Accept either a simple string or the structured dictionary produced by
    # Reddit extraction. Returning None means "skip this unusable entry".
    @classmethod
    def from_value(cls, value: Any, max_chars: int) -> "Comment | None":
        # Supporting strings keeps the API convenient for tests/manual payloads.
        if isinstance(value, str):
            text = value.strip()
            return cls(text=text[:max_chars]) if text else None

        # Numbers, lists and other unexpected comment types are ignored rather
        # than making one bad comment invalidate the complete Reddit thread.
        if not isinstance(value, dict):
            return None

        # ``body`` is accepted as an alias for compatibility with Reddit-like
        # structures. str() gives a predictable text value before trimming.
        text = str(value.get("text") or value.get("body") or "").strip()
        if not text:
            return None

        score = _optional_int(value.get("score"))
        depth = _optional_int(value.get("depth"))
        author = str(value.get("author") or "").strip() or None
        return cls(
            text=text[:max_chars],
            author=author,
            score=score,
            depth=depth,
        )


# Complete validated input used by the engine. Tuples discourage accidental
# modification after validation; default factories avoid shared mutable values.
@dataclass
class AnalysisInput:
    url: str
    title: str
    body: str
    comments: tuple[Comment, ...] = field(default_factory=tuple)
    extraction: dict[str, Any] = field(default_factory=dict)

    # The linguistic analysis treats title and body as one document while the
    # original fields remain available for summaries and character counts.
    @property
    def post_text(self) -> str:
        return "\n".join(part for part in (self.title, self.body) if part).strip()

    # Main boundary between raw JSON and trusted internal data. Keyword-only
    # limits make it clear that callers must deliberately supply them.
    @classmethod
    def from_payload(
        cls,
        payload: Any,
        *,
        max_comments: int,
        max_text_chars: int,
    ) -> "AnalysisInput":
        if not isinstance(payload, dict):
            raise InputValidationError("The request body must be a JSON object.")

        # Defensive slicing prevents individual fields from growing without
        # bound even if the complete HTTP request is below Flask's 1 MB limit.
        url = str(payload.get("url") or "").strip()[:2048]
        title = str(payload.get("title") or "").strip()[:1000]
        body = str(payload.get("body") or "").strip()[:max_text_chars]

        raw_comments = payload.get("comments") or []
        if not isinstance(raw_comments, list):
            raise InputValidationError("The comments field must be a list.")

        # Only inspect the configured number of entries. Each valid value is
        # converted into the same Comment type before reaching feature code.
        comments: list[Comment] = []
        for value in raw_comments[:max_comments]:
            parsed = Comment.from_value(value, max_chars=5000)
            if parsed is not None:
                comments.append(parsed)

        # Extraction metadata is diagnostic information, not trusted scoring
        # input. Non-object values are replaced by an empty dictionary.
        extraction = payload.get("extraction")
        if not isinstance(extraction, dict):
            extraction = {}

        if not title and not body:
            raise InputValidationError(
                "No Reddit post title or body was captured. Open an individual Reddit post and try again."
            )

        return cls(
            url=url,
            title=title,
            body=body,
            comments=tuple(comments),
            extraction=extraction,
        )


# Reddit metadata can be missing or represented as strings. Invalid numeric
# values become None because score/depth metadata should never break analysis.
def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
