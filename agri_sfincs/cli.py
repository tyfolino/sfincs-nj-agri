"""Small command-line helpers shared by the scripts."""

from __future__ import annotations


def parse_years(s: str) -> list[int]:
    """``"2008-2025"`` -> every year in the range; ``"2022,2024"`` -> those years."""
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in s.split(",")]
