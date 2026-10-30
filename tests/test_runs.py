"""Run helpers (agri_sfincs.runs) and CDL paths — synthetic grids, no network, no scratch."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from rasterio.transform import from_origin

from agri_sfincs import cdl, config, runs


def _map(n=3, m=3, dx=100.0, x0=1000.0, y0=2000.0, zsmax=None, days=2):
    """A tiny sfincs_map.nc lookalike: corners, and daily zsmax blocks."""
    cx, cy = np.meshgrid(x0 + np.arange(m + 1) * dx, y0 + np.arange(n + 1) * dx)
    tmax = pd.date_range("2024-10-02", periods=days, freq="D")
    if zsmax is None:
        zsmax = np.zeros((days, n, m))
    return xr.Dataset(
        {"zsmax": (("timemax", "n", "m"), zsmax)},
        coords={"corner_x": (("corner_n", "corner_m"), cx), "corner_y": (("corner_n", "corner_m"), cy),
                "timemax": tmax},
    )  # fmt: skip


class TestRunDirs(unittest.TestCase):
    def test_run_dir_and_resolve(self):
        r = runs.run_dir("tide2024oct", "intact", 0, "_rep")
        self.assertEqual(r, config.MODELS / "v1_100m" / "runs" / "tide2024oct_intact_slr000_rep")
        self.assertEqual(runs.resolve("v0_100m/sep2023"), config.MODELS / "v0_100m" / "runs" / "sep2023")
        self.assertEqual(runs.resolve("sep2023"), config.MODELS / "v1_100m" / "runs" / "sep2023")

    def test_finished(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            self.assertFalse(runs.finished(run))
            (run / "sfincs_log.txt").write_text("step 10\n")
            self.assertFalse(runs.finished(run))
            (run / "sfincs_log.txt").write_text("step 10\n Total time : 12.3\n")
            self.assertTrue(runs.finished(run))


class TestMapGrid(unittest.TestCase):
    def test_from_map_and_face(self):
        g = runs.MapGrid.from_map(_map())
        self.assertEqual((g.x0, g.y0, g.dx, g.n, g.m), (1000.0, 2000.0, 100.0, 3, 3))
        # cell (row 1, col 2) holds (1250, 2150); edges belong to the cell above / right
        f = g.face(np.array([1250.0, 1000.0, 999.9, 1300.0]), np.array([2150.0, 2000.0, 2050.0, 2050.0]))
        np.testing.assert_array_equal(f, [1 * 3 + 2, 0, -1, -1])

    def test_mesh_map_refined(self):
        """A UGRID map, active faces only and in any order: two 100 m cells and a third
        split into four 50 m cells; the fourth 100 m cell is inactive."""
        sq = [(0, 0, 100), (0, 100, 100)] + [(100 + i, j, 50) for i in (0, 50) for j in (0, 50)]
        order = [3, 0, 5, 1, 2, 4]  # face k = sq[order[k]]
        nx, ny, fn = [], [], []
        for x, y, w in (sq[k] for k in order):
            fn.append(np.arange(4) + len(nx) + 1)  # 1-based, counterclockwise
            nx += [1000 + x, 1000 + x + w, 1000 + x + w, 1000 + x]
            ny += [2000 + y, 2000 + y, 2000 + y + w, 2000 + y + w]
        fnv = xr.DataArray(np.array(fn, float), dims=("nmesh2d_face", "max_nmesh2d_face_nodes"), attrs={"start_index": 1})
        mesh = xr.Dataset({"mesh2d_face_nodes": fnv, "mesh2d_node_x": ("nmesh2d_node", np.array(nx, float)),
                           "mesh2d_node_y": ("nmesh2d_node", np.array(ny, float))})  # fmt: skip
        g = runs.MapGrid.from_map(mesh)
        self.assertEqual((g.x0, g.y0, g.dx, g.n, g.m), (1000.0, 2000.0, 50.0, 4, 4))
        face_of = {sq_i: k for k, sq_i in enumerate(order)}
        x = np.array([1010.0, 1090.0, 1050.0, 1125.0, 1175.0, 1175.0, 1150.0, 1150.0, 999.0])
        y = np.array([2010.0, 2090.0, 2150.0, 2025.0, 2025.0, 2075.0, 2150.0, 2050.0, 2010.0])
        want = [face_of[0], face_of[0], face_of[1], face_of[2], face_of[4], face_of[5], -1, face_of[5], -1]
        np.testing.assert_array_equal(g.face(x, y), want)
        grid = g.as_grid(np.arange(6.0))
        self.assertEqual(grid.shape, (4, 4))
        self.assertEqual(grid[0, 0], face_of[0])  # (row, col) of the 50 m slots
        self.assertEqual(grid[1, 3], face_of[5])
        self.assertTrue(np.isnan(grid[3, 3]))  # the inactive 100 m cell

    def test_pixel_cells(self):
        """10 m pixels, north-up, over the 3 x 3 grid of 100 m cells (row 0 = south)."""
        g = runs.MapGrid.from_map(_map())
        tr = from_origin(1000.0, 2300.0, 10.0, 10.0)  # 30 x 30 pixels cover the grid
        ids = np.zeros((32, 30), "uint32")  # two extra rows south of the grid
        ids[0, 0] = 1  # NW pixel -> cell (2, 0)
        ids[29, 29] = 2  # SE pixel -> cell (0, 2)
        ids[31, 5] = 3  # south of the grid: dropped
        ids[15, 15] = 4  # NaN ground: dropped
        dep = np.ones(ids.shape)
        dep[15, 15] = np.nan
        face, d, uid = runs.pixel_cells(ids, tr, dep, g)
        self.assertEqual(sorted(zip(uid.tolist(), face.tolist())), [(1, 6), (2, 2)])
        np.testing.assert_array_equal(d, [1.0, 1.0])


class TestCentrelineLinks(unittest.TestCase):
    def test_straight_and_diagonal(self):
        from shapely.geometry import LineString

        g = runs.MapGrid(0.0, 0.0, 100.0, 5, 5)
        straight = runs.centreline_links(g, LineString([(50, 50), (250, 50)]))
        self.assertEqual(straight, [((50.0, 50.0), (150.0, 50.0)), ((150.0, 50.0), (250.0, 50.0))])
        # through the corner (100, 100) the line steps diagonally: both detours, 4 links
        diag = runs.centreline_links(g, LineString([(50, 50), (150, 150)]), step=50 * 2**0.5)
        self.assertEqual(len(diag), 4)
        self.assertIn(((50.0, 50.0), (150.0, 50.0)), diag)
        self.assertIn(((50.0, 150.0), (150.0, 150.0)), diag)


class TestDepth(unittest.TestCase):
    def test_block_days_and_depth(self):
        z = np.zeros((2, 3, 3))
        z[1, 0, 0] = 0.3
        z[1, 0, 1] = np.nan
        mp = _map(zsmax=z)
        self.assertEqual(runs.block_days(mp)[0], pd.Timestamp("2024-10-01"))
        face = np.array([0, 0, 1, 4])
        dep = np.array([0.1, 0.5, 0.0, -0.2], "float64")
        h = runs.depth(mp, 1, face, dep)
        self.assertEqual(h.dtype, np.float32)
        np.testing.assert_allclose(h, [0.2, 0.0, 0.0, 0.2], rtol=1e-6)


class TestCdlPath(unittest.TestCase):
    def test_path(self):
        self.assertEqual(cdl.path(2024), config.CDL_DIR / "CDL_2024_34.tif")
        self.assertEqual(cdl.path(2024, "10"), config.FLOODPLAIN_DIR / "cdl" / "CDL_2024_10.tif")


if __name__ == "__main__":
    unittest.main()
