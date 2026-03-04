"""
ConformalBridge — simple conformal prediction bridge (open version).

Given a softmax score vector, produces a prediction set at ~95% coverage
using a threshold-based approach. If "human" appears in the set, the
observation is treated as human (conservative safety measure).

Advanced conformal prediction with guaranteed coverage is enterprise-only.
"""

from __future__ import annotations


_DEFAULT_THRESHOLD = 0.05  # Include classes with score >= threshold


class ConformalBridge:
    """
    Simple threshold-based conformal prediction.

    For each class whose softmax score >= threshold, include it in the
    prediction set. This approximates a conformal prediction set with
    coverage proportional to the threshold choice.

    Conservative by design: any uncertainty resolves toward safety.
    If 'human' appears in the prediction set, treat_as_human = True.
    """

    def __init__(self, threshold: float = _DEFAULT_THRESHOLD) -> None:
        """
        Args:
            threshold: Minimum score to include a class in the prediction set.
                       Lower = more inclusive = more conservative.
        """
        self.threshold = threshold

    def prediction_set(self, scores: dict[str, float]) -> list[str]:
        """
        Compute prediction set from class → score dict.

        Args:
            scores: Dict mapping class label → softmax probability.
                    Values should sum to 1.0 (but this is not enforced).

        Returns:
            List of class labels included in the prediction set.
        """
        return sorted(
            [cls for cls, score in scores.items() if score >= self.threshold],
            key=lambda c: scores[c],
            reverse=True,
        )

    def treat_as_human(self, scores: dict[str, float]) -> bool:
        """
        Return True if the prediction set contains 'human' or 'person'.

        This is the core safety rule: under uncertainty, assume human presence.
        """
        pred_set = self.prediction_set(scores)
        human_labels = {"human", "person"}
        return any(label in human_labels for label in pred_set)

    def annotate(self, scores: dict[str, float]) -> dict:
        """
        Return a full annotation dict for use in StructuredObservation.

        Returns:
            {
                "class_set": [...],
                "treat_as_human": bool,
                "class_best": str,   # highest scoring class
            }
        """
        pred_set = self.prediction_set(scores)
        class_best = max(scores, key=lambda c: scores[c]) if scores else "unknown"
        return {
            "class_set": pred_set,
            "treat_as_human": self.treat_as_human(scores),
            "class_best": class_best,
        }
