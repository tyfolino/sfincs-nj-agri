"""Dark "cyberpunk" figure style for slides and talks (mplcyberpunk, installed in the shared env
2026-10-17 with the user's OK).

mplcyberpunk 0.7.6 calls matplotlib.style.core.read_style_directory / update_nested_dict at
import; matplotlib 3.11 removed both, so ``cyberpunk()`` puts equivalents back before importing
it. Use:  mcp = plotstyle.cyberpunk()  (applies the style; returns the module for its glow
helpers, e.g. mcp.make_lines_glow(ax)).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.style.core as style_core

# the stylesheet's neon cycle, named, for direct use
CYAN, PINK, YELLOW, GREEN, VIOLET = "#08F7FE", "#FE53BB", "#F5D300", "#00ff41", "#9467bd"
BG, GRID, INK, MUTED = "#212946", "#2A3459", "#e6e6e6", "#8b93b8"


def _read_style_directory(path) -> dict:
    return {p.stem: mpl.rc_params_from_file(p, use_default_template=False)
            for p in Path(path).glob(f"*.{style_core.STYLE_EXTENSION}")}  # fmt: skip


def _update_nested_dict(main: dict, new: dict) -> dict:
    for name, rc in new.items():
        main.setdefault(name, {}).update(rc)
    return main


def cyberpunk():
    """Apply the cyberpunk style and return the mplcyberpunk module."""
    if not hasattr(style_core, "read_style_directory"):
        style_core.read_style_directory = _read_style_directory
        style_core.update_nested_dict = _update_nested_dict
    import mplcyberpunk

    plt.style.use("cyberpunk")
    return mplcyberpunk
