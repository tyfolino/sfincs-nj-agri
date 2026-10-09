"""Per-field flood class from the dike x sea-level scenario runs (pure pieces).

A field "floods" in a run when at least ``SHARE`` of its 10 m pixels see a month-max depth
above 5 cm. For each field we know, per dike scenario, the lowest sea-level rise (of
``LEVELS``) at which it floods: ``first_level``. ``classify`` turns the as-built and
dikes-removed answers into one class, earliest threat first:

  flooded today          floods with today's dikes at today's sea level
  dike-dependent today   floods today only if the dikes are removed
  dike-dependent +L      first floods at +L, and only without the dikes there
  overtopped +L          first floods at +L even with the dikes; behind an NLD levee
  exposed +L             the same, not behind a levee (no dike to help)
  safe to +1.0 m         dry in every run

Removing the dikes can (rarely) leave a field drier, when a bank held water in. Then the
as-built level decides and the class is overtopped / exposed.
"""

from __future__ import annotations

import math

import numpy as np

LEVELS = (0.0, 0.3, 0.6, 1.0)
SHARE = 0.10
SAFE = "safe to +1.0 m"


def first_level(shares, levels=LEVELS, share: float = SHARE) -> float:
    """Lowest level whose flooded share is >= ``share``; NaN if none. ``shares`` aligns with
    ``levels``; a NaN share (run missing) never counts as flooded."""
    for lev, s in zip(levels, shares):
        if s is not None and np.isfinite(s) and s >= share:
            return float(lev)
    return math.nan


def _lev(x: float) -> str:
    return f"+{x:.1f} m"


def classify(with_dikes: float, without_dikes: float, behind_levee: bool) -> str:
    w, wo = with_dikes, without_dikes
    if w == 0.0:
        return "flooded today"
    if wo == 0.0:
        return "dike-dependent today"
    if math.isnan(w) and math.isnan(wo):
        return SAFE
    if math.isnan(w) or (not math.isnan(wo) and wo < w):
        return f"dike-dependent {_lev(wo)}"
    return f"{'overtopped' if behind_levee else 'exposed'} {_lev(w)}"


def class_order() -> list[str]:
    """Every class, earliest threat first (for tables and legends)."""
    out = ["flooded today", "dike-dependent today"]
    for lev in LEVELS[1:]:
        out += [f"dike-dependent {_lev(lev)}", f"overtopped {_lev(lev)}", f"exposed {_lev(lev)}"]
    return out + [SAFE]


def longest_run(wet) -> int:
    """Longest run of consecutive True values in a 1-D boolean sequence (days)."""
    best = cur = 0
    for w in wet:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    return best
