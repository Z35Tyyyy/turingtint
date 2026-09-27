"""Measured binary paragraph-detector evaluation; uncertainty is not authorship."""

from .metrics import (
    FrozenThresholds,
    auroc,
    evaluate,
    select_thresholds,
    wilson_one_sided_bounds,
)

__all__ = ["FrozenThresholds", "auroc", "evaluate", "select_thresholds", "wilson_one_sided_bounds"]
