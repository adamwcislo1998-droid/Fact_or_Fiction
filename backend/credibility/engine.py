"""Calculates the explainable credibility-signal score.

Feature extraction happens in ``features.py``. This module applies explicit,
bounded weights, combines the indicators and constructs the complete API result.
The score describes communication signals and must not be read as truth probability.
"""


from dataclasses import dataclass
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .features import (
    CommentFeatures,
    PostFeatures,
    analyse_comments,
    analyse_post,
    phrase_highlights,
    total_matches,
)
from .models import AnalysisInput
from .transformer import OptionalTransformerClassifier


# Each Indicator records one explainable influence on the score. Keeping the raw
# value, direction and prose explanation makes the result inspectable in the UI.
@dataclass
class Indicator:
    identifier: str
    category: str
    direction: str
    value: Any
    contribution: float
    explanation: str

    # Convert to a JSON-friendly dictionary and round only the public output.
    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "category": self.category,
            "direction": self.direction,
            "value": self.value,
            "contribution": round(self.contribution, 4),
            "explanation": self.explanation,
        }


class CredibilityEngine:
    """Combines the post and comment measurements into one result."""

    # Returned by health and analysis endpoints to identify scoring behaviour.
    VERSION = "1.0.0"

    def __init__(self, *, enable_transformer: bool, transformer_model: str) -> None:
        # VADER is a lightweight lexicon/rule sentiment analyser. One instance
        # is reused for post and comment measurements.
        self.vader = SentimentIntensityAnalyzer()
        self.transformer = OptionalTransformerClassifier(
            enabled=enable_transformer,
            model_name=transformer_model,
        )

    # Public orchestration method: measure text, build indicators, combine
    # weights, label the result and expose diagnostics/limitations.
    def analyse(self, data: AnalysisInput) -> dict[str, Any]:
        # Measurement is separated from weighting so each stage can be tested
        # and explained independently.
        post_features = analyse_post(data.post_text, self.vader)
        comment_features = analyse_comments(data.comments, self.vader)
        transformer = self.transformer.assess(data.post_text)

        # Rule-based indicators form the complete default score.
        indicators = self._build_indicators(post_features, comment_features)
        # Add the optional model only when it completed successfully. Disabled,
        # unavailable or failed models never prevent the normal analysis.
        if transformer["status"] == "active":
            direction = "supports" if transformer["contribution"] >= 0 else "questions"
            indicators.append(
                Indicator(
                    identifier="transformer_classification",
                    category="model",
                    direction=direction,
                    value=transformer["labels"],
                    contribution=transformer["contribution"],
                    explanation=(
                        "An optional zero-shot transformer compared evidence-based, "
                        "sensational and anecdotal descriptions of the post."
                    ),
                )
            )

        # Sum contributions and clamp to the documented -1..+1 range. Mapping
        # with (score + 1) * 50 gives a UI scale of 0..100 with neutral at 50.
        raw_score = sum(indicator.contribution for indicator in indicators)
        score = max(-1.0, min(1.0, raw_score))
        score_percent = round((score + 1.0) * 50)
        label = self._label(score)
        confidence = self._assessment_confidence(post_features, comment_features)

        # Show the largest absolute influences first regardless of whether they
        # support or question the post.
        sorted_indicators = sorted(
            indicators,
            key=lambda item: abs(item.contribution),
            reverse=True,
        )

        # The response deliberately includes both a concise display result and
        # lower-level measurements for transparency, debugging and evaluation.
        return {
            "ok": True,
            "engine_version": self.VERSION,
            "score": round(score, 3),
            "score_percent": score_percent,
            "label": label,
            "assessment_confidence": confidence,
            "summary": self._summary(label, confidence),
            "indicators": [indicator.as_dict() for indicator in sorted_indicators],
            "highlights": phrase_highlights(post_features),
            "post_analysis": {
                "token_count": post_features.token_count,
                "sentence_count": post_features.sentence_count,
                "link_count": post_features.link_count,
                "unique_domains": list(post_features.unique_domains),
                "uppercase_ratio": post_features.uppercase_ratio,
                "emphasis_ratio": post_features.emphasis_ratio,
                "readability_ease": post_features.readability_ease,
                "sentiment": post_features.sentiment,
            },
            "comment_analysis": {
                "captured_count": comment_features.captured_count,
                "mean_sentiment": comment_features.mean_sentiment,
                "sentiment_stddev": comment_features.sentiment_stddev,
                "positive_share": comment_features.positive_share,
                "negative_share": comment_features.negative_share,
                "challenge_count": comment_features.challenge_count,
                "evidence_count": comment_features.evidence_count,
                "link_count": comment_features.link_count,
                "challenge_examples": list(comment_features.challenge_examples),
            },
            "models": {
                "vader": {"status": "active", "purpose": "sentiment and emotional intensity"},
                "transformer": transformer,
            },
            "input_summary": {
                "url": data.url,
                "title_chars": len(data.title),
                "body_chars": len(data.body),
                "comments_count": len(data.comments),
                "extraction": data.extraction,
            },
            "limitations": [
                "This is a credibility-signal aid, not an automated fact checker.",
                "A high or low score does not prove that a claim is true or false.",
                "Comment analysis only covers comments available to the extension at analysis time.",
                "Source quality is not inferred from domain reputation; only visible sourcing behaviour is measured.",
            ],
        }

    # Translate measured features into bounded, human-readable contributions.
    # Every maximum prevents repetition of one feature from dominating the score.
    def _build_indicators(
        self,
        post: PostFeatures,
        comments: CommentFeatures,
    ) -> list[Indicator]:
        indicators: list[Indicator] = []

        # SOURCING: +0.06 per distinct visible post domain, capped at +0.18.
        # Distinct domains are used instead of raw link count to reduce gaming.
        domain_count = len(post.unique_domains)
        source_contribution = min(0.18, domain_count * 0.06)
        if domain_count:
            indicators.append(
                Indicator(
                    "external_sources",
                    "sourcing",
                    "supports",
                    {"links": post.link_count, "domains": list(post.unique_domains)},
                    source_contribution,
                    "The post includes links across one or more distinct domains.",
                )
            )
        else:
            indicators.append(
                Indicator(
                    "external_sources",
                    "sourcing",
                    "neutral",
                    {"links": 0, "domains": []},
                    0.0,
                    "No visible external source link was captured from the post.",
                )
            )

        # EVIDENCE WORDING: +0.03 per detected phrase, capped at +0.12. This
        # recognises inspectable language but does not verify the source itself.
        evidence_count = total_matches(post.evidence_matches)
        indicators.append(
            Indicator(
                "evidence_language",
                "sourcing",
                "supports" if evidence_count else "neutral",
                evidence_count,
                min(0.12, evidence_count * 0.03),
                "Evidence-oriented wording can make claims easier for a reader to inspect.",
            )
        )

        # CONTEXT: longer text gives the analyser more material. Very short text
        # receives a small caution, not a judgement that the claim is false.
        if post.token_count >= 120:
            context_contribution = 0.08
            context_note = "The post contains enough text for a broader linguistic assessment."
            context_direction = "supports"
        elif post.token_count >= 50:
            context_contribution = 0.04
            context_note = "The post contains a moderate amount of context."
            context_direction = "supports"
        elif post.token_count < 25:
            context_contribution = -0.06
            context_note = "Very little post text was available, so claims are difficult to assess."
            context_direction = "questions"
        else:
            context_contribution = 0.0
            context_note = "The post contains limited context."
            context_direction = "neutral"
        indicators.append(
            Indicator(
                "context_amount",
                "content",
                context_direction,
                post.token_count,
                context_contribution,
                context_note,
            )
        )

        # UNCERTAINTY: +0.02 per hedge phrase, capped at +0.08, because qualified
        # language can acknowledge limitations and estimates.
        hedge_count = total_matches(post.hedge_matches)
        indicators.append(
            Indicator(
                "uncertainty_language",
                "language",
                "supports" if hedge_count else "neutral",
                hedge_count,
                min(0.08, hedge_count * 0.02),
                "Qualified wording can show that uncertainty is being acknowledged.",
            )
        )

        # SENSATIONAL LANGUAGE: -0.05 per match, capped at -0.20.
        sensational_count = total_matches(post.sensational_matches)
        indicators.append(
            Indicator(
                "sensational_language",
                "language",
                "questions" if sensational_count else "neutral",
                sensational_count,
                -min(0.20, sensational_count * 0.05),
                "Sensational wording can prioritise attention over careful qualification.",
            )
        )

        # ABSOLUTE LANGUAGE: -0.04 per certainty phrase, capped at -0.15.
        absolute_count = total_matches(post.absolute_matches)
        indicators.append(
            Indicator(
                "absolute_language",
                "language",
                "questions" if absolute_count else "neutral",
                absolute_count,
                -min(0.15, absolute_count * 0.04),
                "Repeated certainty terms can hide uncertainty or exceptions.",
            )
        )

        # UPPERCASE EMPHASIS: no penalty for the first 8% of letters; beyond that
        # the scaled deduction is capped at -0.10.
        uppercase_penalty = -min(0.10, max(0.0, post.uppercase_ratio - 0.08) * 0.8)
        indicators.append(
            Indicator(
                "uppercase_emphasis",
                "style",
                "questions" if uppercase_penalty < 0 else "neutral",
                post.uppercase_ratio,
                uppercase_penalty,
                "A high proportion of capital letters can indicate rhetorical emphasis.",
            )
        )

        # REPEATED PUNCTUATION: sentence-normalised emphasis, capped at -0.08.
        punctuation_penalty = -min(0.08, post.emphasis_ratio * 0.04)
        indicators.append(
            Indicator(
                "punctuation_emphasis",
                "style",
                "questions" if punctuation_penalty < 0 else "neutral",
                post.emphasis_ratio,
                punctuation_penalty,
                "Repeated exclamation, question or ellipsis marks can indicate emotional framing.",
            )
        )

        # EMOTIONAL INTENSITY: only absolute VADER compound above 0.55 is
        # penalised, so both very positive and very negative framing are treated
        # as style signals rather than evidence of falsehood.
        compound = post.sentiment["compound"]
        emotion_penalty = -min(0.12, max(0.0, abs(compound) - 0.55) * 0.27)
        indicators.append(
            Indicator(
                "emotional_intensity",
                "sentiment",
                "questions" if emotion_penalty < 0 else "neutral",
                compound,
                emotion_penalty,
                "Strong sentiment is treated as a framing signal, not as evidence of falsehood.",
            )
        )

        # DISCUSSION indicators are calculated only when a comment sample exists;
        # otherwise a neutral availability indicator explains the missing data.
        if comments.captured_count:
            # Challenge share * -0.32, capped at -0.16. Commenters are not treated
            # as automatically correct; this is only a caution signal.
            challenge_ratio = comments.challenge_count / comments.captured_count
            challenge_penalty = -min(0.16, challenge_ratio * 0.32)
            indicators.append(
                Indicator(
                    "community_challenges",
                    "discussion",
                    "questions" if challenge_penalty < 0 else "neutral",
                    {
                        "count": comments.challenge_count,
                        "share": round(challenge_ratio, 3),
                    },
                    challenge_penalty,
                    "Captured comments containing correction, source-request or challenge language are surfaced as a caution signal.",
                )
            )

            # Evidence-oriented comment share * +0.20, capped at +0.08.
            evidence_ratio = comments.evidence_count / comments.captured_count
            indicators.append(
                Indicator(
                    "comment_evidence",
                    "discussion",
                    "supports" if comments.evidence_count else "neutral",
                    {
                        "count": comments.evidence_count,
                        "share": round(evidence_ratio, 3),
                    },
                    min(0.08, evidence_ratio * 0.20),
                    "Some captured comments use evidence-oriented wording or provide links.",
                )
            )

            # A fixed -0.05 applies when at least 20% of comments are strongly
            # positive and at least 20% are strongly negative.
            polarised = comments.positive_share >= 0.2 and comments.negative_share >= 0.2
            indicators.append(
                Indicator(
                    "discussion_polarisation",
                    "discussion",
                    "questions" if polarised else "neutral",
                    {
                        "positive_share": comments.positive_share,
                        "negative_share": comments.negative_share,
                        "sentiment_stddev": comments.sentiment_stddev,
                    },
                    -0.05 if polarised else 0.0,
                    "A strongly split discussion reduces confidence in a simple interpretation of the post.",
                )
            )
        else:
            indicators.append(
                Indicator(
                    "comments_available",
                    "discussion",
                    "neutral",
                    0,
                    0.0,
                    "No comments were available, so community discussion did not affect the score.",
                )
            )

        return indicators

    # Thresholds deliberately use cautious wording and avoid true/false labels.
    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.25:
            return "more supportive signals"
        if score <= -0.25:
            return "more caution signals"
        return "mixed or limited signals"

    # This is information-availability confidence, not statistical certainty.
    # Points come from post length, visible links and comment-sample size.
    @staticmethod
    def _assessment_confidence(post: PostFeatures, comments: CommentFeatures) -> str:
        evidence_points = 0
        if post.token_count >= 80:
            evidence_points += 1
        if post.link_count >= 1:
            evidence_points += 1
        if comments.captured_count >= 5:
            evidence_points += 1
        if comments.captured_count >= 20:
            evidence_points += 1
        if evidence_points >= 3:
            return "higher"
        if evidence_points >= 2:
            return "moderate"
        return "limited"

    # Compose one short sentence for the popup from the already calculated label
    # and information level.
    @staticmethod
    def _summary(label: str, confidence: str) -> str:
        return (
            f"The captured post contains {label}. "
            f"The amount of information available for this assessment is {confidence}."
        )
