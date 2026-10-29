"""Public interface for the credibility-analysis package.

Re-exporting the main classes here lets callers import from ``credibility``
instead of depending on the package's internal file layout.
"""

# Relative imports refer to modules inside this package.
from .engine import CredibilityEngine
from .models import AnalysisInput, InputValidationError

# ``__all__`` documents which names are intended as the package's public API.
__all__ = ["AnalysisInput", "CredibilityEngine", "InputValidationError"]
