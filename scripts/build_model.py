"""Build a static SFINCS model under config.MODELS/<name> (agri_sfincs.build).

Usage:
  python scripts/build_model.py --name v0_100m [--res 100] [--subgrid 10] [--drained]

v0_100m (2026-10-02): uniform 100 m quadtree, 10 m subgrid, undrained soil groups — the
first, cheap model for the Sep 2023 / May 2025 event runs. Refinement comes after the
cost test (plan step 5).
"""

from __future__ import annotations

import argparse
import time

from agri_sfincs.build import StaticConfig, build_static


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--res", type=float, default=100.0)
    ap.add_argument("--subgrid", type=int, default=10, help="subgrid pixels per cell")
    ap.add_argument("--drained", action="store_true", help="dual HSGs as drained")
    a = ap.parse_args()
    cfg = StaticConfig(
        name=a.name, res=a.res, nr_subgrid_pixels=a.subgrid,
        hsg="hsg_drained" if a.drained else "hsg_undrained",
    )  # fmt: skip
    t0 = time.time()
    root = build_static(cfg)
    print(f"built {root} in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
