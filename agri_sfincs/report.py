"""Tiny report helpers (the shared env has no ``tabulate``, so no DataFrame.to_markdown)."""

from __future__ import annotations

import pandas as pd


def md_table(df: pd.DataFrame, floatfmt: str = "{:,.3f}") -> str:
    """A GitHub markdown table of ``df`` including its index."""
    d = df.reset_index()
    cells = [[floatfmt.format(v) if isinstance(v, float) else str(v) for v in row]
             for row in d.itertuples(index=False)]  # fmt: skip
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    rule = "|" + "|".join("---" for _ in d.columns) + "|"
    return "\n".join([head, rule, *("| " + " | ".join(r) + " |" for r in cells)])
