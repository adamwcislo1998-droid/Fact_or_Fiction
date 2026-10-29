"""Unit tests for validation and scoring behaviour without HTTP transport."""

from credibility import AnalysisInput, CredibilityEngine


# Keep transformer mode disabled so unit tests are fast, offline and repeatable.
def build_engine():
    return CredibilityEngine(
        enable_transformer=False,
        transformer_model="unused-in-tests",
    )


# Behavioural comparison is more meaningful than locking the project to one
# exact score: the evidence-oriented example should rank above the sensational one.
def test_evidence_based_post_scores_above_sensational_post():
    evidence_payload = {
        "title": "Study reports an estimated change",
        "body": (
            "According to the report, the data show an approximately ten percent change. "
            "The result may change with a larger dataset. https://example.org/report"
        ),
        "comments": ["The methodology is available in the report."],
    }
    sensational_payload = {
        "title": "SHOCKING BOMBSHELL THEY NEVER WANT YOU TO KNOW!!!",
        "body": "This is obviously a guaranteed cover-up. Everyone knows it is 100% true!!!",
        "comments": ["This is misleading. Source?", "There is no evidence for this claim."],
    }

    engine = build_engine()
    evidence = engine.analyse(
        AnalysisInput.from_payload(evidence_payload, max_comments=75, max_text_chars=50000)
    )
    sensational = engine.analyse(
        AnalysisInput.from_payload(sensational_payload, max_comments=75, max_text_chars=50000)
    )

    assert evidence["score"] > sensational["score"]
    assert evidence["score"] <= 1
    assert sensational["score"] >= -1


# Ensure both accepted comment text keys and nested metadata structures reach
# the feature extractor correctly.
def test_structured_comments_are_counted_and_analysed():
    payload = {
        "title": "Example post",
        "body": "A claim is made here.",
        "comments": [
            {"text": "This is false. Source?", "score": 10, "depth": 0},
            {"body": "According to this report: https://example.org", "depth": 1},
        ],
    }
    result = build_engine().analyse(
        AnalysisInput.from_payload(payload, max_comments=75, max_text_chars=50000)
    )

    assert result["comment_analysis"]["captured_count"] == 2
    assert result["comment_analysis"]["challenge_count"] >= 1
    assert result["comment_analysis"]["evidence_count"] >= 1


# Even disabled optional components must be reported transparently in output.
def test_transformer_is_reported_as_disabled_by_default():
    payload = {"title": "Example", "body": "Some text for analysis."}
    result = build_engine().analyse(
        AnalysisInput.from_payload(payload, max_comments=75, max_text_chars=50000)
    )
    assert result["models"]["transformer"]["status"] == "disabled"
