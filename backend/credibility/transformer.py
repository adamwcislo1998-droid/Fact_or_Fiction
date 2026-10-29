"""Optional transformer analysis.

The main program works without this file downloading a model. The model is only
loaded when transformer mode is enabled.
"""


# Wrapper isolates every heavy/optional dependency from the standard engine.
# Importing this module does not import PyTorch or Transformers by itself.
class OptionalTransformerClassifier:
    # Natural-language candidate labels used for zero-shot classification.
    LABELS = [
        "careful evidence-based claim",
        "sensational or potentially misleading claim",
        "personal opinion or anecdote",
    ]

    def __init__(self, enabled, model_name):
        # Pipeline starts unloaded. This lazy strategy keeps standard startup
        # fast and avoids downloads unless the optional mode is actually used.
        self.enabled = enabled
        self.model_name = model_name
        self.pipeline = None
        self.load_error = None

    def assess(self, text):
        # Always return the same result shape, including when the feature is
        # disabled or unavailable, so callers do not need exception handling.
        if not self.enabled:
            return self._result("disabled")

        pipeline = self._load_pipeline()
        if pipeline is None:
            return self._result("unavailable", error=self.load_error)

        try:
            # Limit input length to bound inference cost. Zero-shot classification
            # compares the same text with each candidate description.
            output = pipeline(
                text[:4000],
                candidate_labels=self.LABELS,
                hypothesis_template="This text is best described as a {}.",
                multi_label=False,
            )

            scores = {}
            for label, score in zip(output["labels"], output["scores"]):
                scores[label] = float(score)

            evidence_score = scores.get("careful evidence-based claim", 0.0)
            sensational_score = scores.get(
                "sensational or potentially misleading claim", 0.0
            )
            # Only the evidence-versus-sensational difference affects scoring.
            # Clamping prevents this optional model from dominating transparent
            # rule-based indicators.
            contribution = (evidence_score - sensational_score) * 0.18
            contribution = max(-0.18, min(0.12, contribution))

            return self._result(
                "active",
                contribution=contribution,
                labels=scores,
            )
        except Exception as exc:
            return self._result(
                "error",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _load_pipeline(self):
        # Cache both successful pipelines and failures. Repeated requests should
        # not repeatedly download a model or retry the same missing dependency.
        if self.pipeline is not None:
            return self.pipeline
        if self.load_error is not None:
            return None

        try:
            # Local import is intentional: standard mode works even when the
            # optional transformers package is not installed.
            from transformers import pipeline

            self.pipeline = pipeline(
                "zero-shot-classification",
                model=self.model_name,
            )
            return self.pipeline
        except Exception as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"
            return None

    def _result(self, status, contribution=0.0, labels=None, error=None):
        # Centralised result construction guarantees JSON-serialisable values
        # and consistent rounding across every status path.
        rounded_labels = {}
        for label, value in (labels or {}).items():
            rounded_labels[label] = round(value, 4)

        return {
            "status": status,
            "model": self.model_name if self.enabled else None,
            "contribution": round(contribution, 4),
            "labels": rounded_labels,
            "error": error,
        }
