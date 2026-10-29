"""Functions for extracting measurable features from posts and comments.

This module deliberately separates measurement from weighting. It counts links,
phrases and style patterns, calculates readability/sentiment, and returns data
objects. ``engine.py`` decides how strongly those measurements affect the score.
"""


import re
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import urlparse

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .models import Comment

# Precompiled regular expressions are reused for every request. They provide a
# lightweight approximation of words, visible URLs and sentence boundaries.
TOKEN_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"[.!?]+")

# Phrase dictionaries are transparent heuristics rather than claims of factual
# truth. Each group represents a communication signal the interface can explain.
# Absolute phrases may overstate certainty or hide exceptions.
ABSOLUTE_PHRASES = (
    "always",
    "never",
    "everyone",
    "nobody",
    "no one",
    "all of them",
    "100%",
    "guaranteed",
    "undeniable",
    "obviously",
    "definitely proves",
    "without a doubt",
)

# Sensational phrases are attention-oriented or emotionally loaded wording.
SENSATIONAL_PHRASES = (
    "shocking",
    "insane",
    "crazy",
    "exposed",
    "secret they don't want you to know",
    "cover-up",
    "bombshell",
    "destroyed",
    "wake up",
    "mainstream media won't tell you",
    "scam",
    "hoax",
)

# Evidence phrases indicate attempts to reference data, research or methods;
# the application does not verify that the claimed evidence is genuine.
EVIDENCE_PHRASES = (
    "according to",
    "data shows",
    "the data show",
    "research suggests",
    "research shows",
    "study found",
    "report states",
    "source:",
    "evidence",
    "methodology",
    "dataset",
    "official figures",
)

# Hedge phrases acknowledge uncertainty, estimates or incomplete knowledge.
HEDGE_PHRASES = (
    "may",
    "might",
    "could",
    "appears",
    "seems",
    "suggests",
    "likely",
    "possibly",
    "approximately",
    "estimated",
    "uncertain",
)

# Comment challenge phrases approximate corrections and requests for support.
CHALLENGE_PHRASES = (
    "not true",
    "isn't true",
    "false",
    "misleading",
    "incorrect",
    "source?",
    "citation?",
    "no evidence",
    "fact check",
    "fact-check",
    "actually",
    "this claim",
)

# Separate comment vocabulary identifies discussion that mentions supporting
# material or contains common academic/government URL fragments.
COMMENT_EVIDENCE_PHRASES = (
    "source:",
    "according to",
    "study",
    "report",
    "data",
    "evidence",
    "doi.org",
    "gov.uk",
    ".gov",
    ".edu",
)


# Small typed result objects make the later scoring code clearer than passing
# loosely structured dictionaries between internal functions.
@dataclass
class PhraseMatch:
    phrase: str
    count: int


# All measurements extracted from the combined post title and body.
@dataclass
class PostFeatures:
    token_count: int
    sentence_count: int
    link_count: int
    unique_domains: tuple[str, ...]
    uppercase_ratio: float
    emphasis_ratio: float
    readability_ease: float
    sentiment: dict[str, float]
    absolute_matches: tuple[PhraseMatch, ...]
    sensational_matches: tuple[PhraseMatch, ...]
    evidence_matches: tuple[PhraseMatch, ...]
    hedge_matches: tuple[PhraseMatch, ...]


# Aggregate measurements for the captured comment sample.
@dataclass
class CommentFeatures:
    captured_count: int
    mean_sentiment: float
    sentiment_stddev: float
    positive_share: float
    negative_share: float
    challenge_count: int
    evidence_count: int
    link_count: int
    challenge_examples: tuple[str, ...]


# Extract all post measurements in one pass-oriented function. The supplied
# VADER object is reused by the engine instead of recreated for each request.
def analyse_post(text: str, vader: SentimentIntensityAnalyzer) -> PostFeatures:
    # Token and sentence counts support context and readability calculations.
    tokens = TOKEN_RE.findall(text)
    sentences = [s for s in SENTENCE_RE.split(text) if s.strip()]
    # Remove punctuation commonly attached at the end of a written URL, then
    # reduce links to unique host names so repeated same-domain links do not
    # receive unlimited sourcing credit.
    urls = [url.rstrip(".,;:!?") for url in URL_RE.findall(text)]
    domains = sorted({_normalise_domain(url) for url in urls if _normalise_domain(url)})

    # Uppercase ratio uses letters only; digits and punctuation would distort
    # the denominator if all characters were included.
    alpha_chars = [char for char in text if char.isalpha()]
    uppercase_chars = sum(1 for char in alpha_chars if char.isupper())
    uppercase_ratio = uppercase_chars / len(alpha_chars) if alpha_chars else 0.0

    # Count groups such as "!!", "???" or "..." rather than every individual
    # punctuation character, then normalise by the number of sentences.
    emphasis_marks = len(re.findall(r"[!?]{2,}|\.{3,}", text))
    emphasis_ratio = emphasis_marks / max(1, len(sentences))

    # Round exposed measurements for stable, readable API output while keeping
    # all required categories together in one immutable-style dataclass value.
    return PostFeatures(
        token_count=len(tokens),
        sentence_count=max(1, len(sentences)),
        link_count=len(urls),
        unique_domains=tuple(domains),
        uppercase_ratio=round(uppercase_ratio, 4),
        emphasis_ratio=round(emphasis_ratio, 4),
        readability_ease=round(_flesch_reading_ease(tokens, sentences), 2),
        sentiment={key: round(value, 4) for key, value in vader.polarity_scores(text).items()},
        absolute_matches=_phrase_matches(text, ABSOLUTE_PHRASES),
        sensational_matches=_phrase_matches(text, SENSATIONAL_PHRASES),
        evidence_matches=_phrase_matches(text, EVIDENCE_PHRASES),
        hedge_matches=_phrase_matches(text, HEDGE_PHRASES),
    )


# Aggregate sentiment and phrase signals across the captured comment sample.
# The comments are contextual signals; they are not assumed to be correct.
def analyse_comments(
    comments: Sequence[Comment],
    vader: SentimentIntensityAnalyzer,
) -> CommentFeatures:
    # Returning a fully populated zero-value object keeps engine.py simple and
    # avoids repeated None checks when no comments were captured.
    if not comments:
        return CommentFeatures(
            captured_count=0,
            mean_sentiment=0.0,
            sentiment_stddev=0.0,
            positive_share=0.0,
            negative_share=0.0,
            challenge_count=0,
            evidence_count=0,
            link_count=0,
            challenge_examples=(),
        )

    compounds: list[float] = []
    challenge_count = 0
    evidence_count = 0
    link_count = 0
    examples: list[str] = []

    # Analyse each comment once, collecting the values needed for aggregate
    # statistics and a maximum of three short examples for transparency.
    for comment in comments:
        text = comment.text
        compound = vader.polarity_scores(text)["compound"]
        compounds.append(compound)

        has_challenge = any(_contains_phrase(text, phrase) for phrase in CHALLENGE_PHRASES)
        if has_challenge:
            challenge_count += 1
            if len(examples) < 3:
                examples.append(_truncate(text, 180))

        if any(_contains_phrase(text, phrase) for phrase in COMMENT_EVIDENCE_PHRASES):
            evidence_count += 1

        link_count += len(URL_RE.findall(text))

    # VADER thresholds classify only stronger sentiment as positive/negative;
    # values between them are treated as neutral/mixed for share calculations.
    positive = sum(1 for value in compounds if value >= 0.35)
    negative = sum(1 for value in compounds if value <= -0.35)

    return CommentFeatures(
        captured_count=len(comments),
        mean_sentiment=round(statistics.fmean(compounds), 4),
        sentiment_stddev=round(statistics.pstdev(compounds), 4),
        positive_share=round(positive / len(compounds), 4),
        negative_share=round(negative / len(compounds), 4),
        challenge_count=challenge_count,
        evidence_count=evidence_count,
        link_count=link_count,
        challenge_examples=tuple(examples),
    )


# Convert a sequence of individual phrase/count records into one category total.
def total_matches(matches: Iterable[PhraseMatch]) -> int:
    return sum(match.count for match in matches)


# Produce JSON-friendly phrase details for explanations. The cap prevents an
# unusually repetitive post from producing an excessively large response.
def phrase_highlights(features: PostFeatures) -> list[dict[str, str | int]]:
    groups = (
        ("sensational_language", features.sensational_matches),
        ("absolute_language", features.absolute_matches),
        ("evidence_language", features.evidence_matches),
        ("uncertainty_language", features.hedge_matches),
    )
    highlights: list[dict[str, str | int]] = []
    for category, matches in groups:
        for match in matches:
            highlights.append(
                {"category": category, "phrase": match.phrase, "count": match.count}
            )
    return highlights[:16]


# Leading underscore marks the following helpers as private implementation
# details of this module rather than its intended public interface.
def _phrase_matches(text: str, phrases: Iterable[str]) -> tuple[PhraseMatch, ...]:
    matches: list[PhraseMatch] = []
    for phrase in phrases:
        count = _count_phrase(text, phrase)
        if count:
            matches.append(PhraseMatch(phrase=phrase, count=count))
    return tuple(matches)


# Single words use word boundaries to avoid substring matches; multiword and
# punctuation phrases are escaped and searched literally, case-insensitively.
def _count_phrase(text: str, phrase: str) -> int:
    if re.fullmatch(r"[\w'-]+", phrase):
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    else:
        pattern = re.escape(phrase)
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _contains_phrase(text: str, phrase: str) -> bool:
    return _count_phrase(text, phrase) > 0


# URL parsing is safer than manually splitting strings. Ports and a leading
# "www." are removed so equivalent hosts count as one domain.
def _normalise_domain(url: str) -> str:
    try:
        domain = urlparse(url).netloc.lower().split(":", 1)[0]
    except ValueError:
        return ""
    return domain[4:] if domain.startswith("www.") else domain


# Approximate Flesch Reading Ease. The result is informational in the current
# version and is not directly included in the weighted credibility score.
def _flesch_reading_ease(tokens: Sequence[str], sentences: Sequence[str]) -> float:
    if not tokens:
        return 0.0
    syllables = sum(_estimate_syllables(token) for token in tokens)
    sentence_count = max(1, len(sentences))
    score = 206.835 - 1.015 * (len(tokens) / sentence_count) - 84.6 * (syllables / len(tokens))
    return max(-50.0, min(120.0, score))


# Lightweight vowel-group estimate avoids adding a large pronunciation
# dictionary. It is sufficient for a rough readability indicator, not linguistics.
def _estimate_syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 1
    groups = re.findall(r"[aeiouy]+", cleaned)
    count = len(groups)
    if cleaned.endswith("e") and count > 1 and not cleaned.endswith(("le", "ye")):
        count -= 1
    return max(1, count)


# Compact whitespace and shorten examples so raw comments cannot dominate the
# API response or the interface.
def _truncate(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else f"{compact[: limit - 1]}…"
