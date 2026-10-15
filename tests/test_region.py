"""Domain registry, ring builder, CDL legend and the pixel counter — no network."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from agri_sfincs import cdl, domain, region

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cropland_coverage  # noqa: E402


def _gdf(polys, crs=domain.EPSG):
    return gpd.GeoDataFrame({"huc12": [str(i) for i in range(len(polys))]},
                            geometry=polys, crs=crs)  # fmt: skip


class TestDomainRegistry(unittest.TestCase):
    def test_38_unique_twelve_digit_codes(self):
        codes = domain.huc12_codes()
        self.assertEqual(len(codes), 38)
        self.assertEqual(len(set(codes)), 38)
        self.assertTrue(all(len(c) == 12 and c.isdigit() for c in codes))

    def test_left_out_sets_do_not_overlap_the_domain(self):
        self.assertFalse(set(domain.GREAT_EGG_GLOUCESTER) & set(domain.HUC12))
        for east_of_west_creek in ("020402060701", "020402060702"):
            self.assertNotIn(east_of_west_creek, domain.HUC12)

    def test_study_and_fringe_counties_disjoint(self):
        self.assertFalse(set(domain.COUNTIES) & set(domain.COUNTIES_FRINGE))


class TestDissolveRing(unittest.TestCase):
    def test_adjacent_squares_with_a_sliver_become_one_polygon(self):
        # 0.3 m gap between neighbours: WBD-style mismatch, must be closed.
        ring = region.dissolve_ring(_gdf([box(0, 0, 1000, 1000),
                                          box(1000.3, 0, 2000, 1000)]))  # fmt: skip
        self.assertEqual(ring.geom_type, "Polygon")
        self.assertEqual(len(ring.interiors), 0)
        self.assertAlmostEqual(ring.area, 2.0e6, delta=2e3)

    def test_disjoint_parts_raise(self):
        with self.assertRaisesRegex(ValueError, "separate polygons"):
            region.dissolve_ring(_gdf([box(0, 0, 1000, 1000),
                                       box(5000, 0, 6000, 1000)]))  # fmt: skip

    def test_enclave_raises(self):
        # A frame of four HUCs around a missing 1 km2 centre.
        frame = [box(0, 0, 3000, 1000), box(0, 2000, 3000, 3000),
                 box(0, 1000, 1000, 2000), box(2000, 1000, 3000, 2000)]  # fmt: skip
        with self.assertRaisesRegex(ValueError, "interior hole"):
            region.dissolve_ring(_gdf(frame))


class TestCdlLegend(unittest.TestCase):
    def test_crops_in_cover_out(self):
        for c in (1, 5, 24, 61, 67, 242, 254):
            self.assertIn(c, cdl.CROPLAND, cdl.name(c))
        for c in (0, 63, 82, 111, 121, 141, 176, 190, 195):
            self.assertNotIn(c, cdl.CROPLAND, cdl.name(c))
        self.assertNotIn(176, cdl.CROPLAND)
        self.assertIn(176, cdl.PASTURE)


class TestCountYear(unittest.TestCase):
    """A 4x4 raster of 30 m pixels: left half county A, right half county B; one HUC
    over the top half. Classes laid out so every (county, huc, code) count is known."""

    def test_counts(self):
        a = np.array([[1, 1, 5, 5],
                      [1, 1, 5, 5],
                      [63, 63, 242, 242],
                      [63, 63, 242, 242]], dtype="uint8")  # fmt: skip
        crs = "EPSG:5070"
        tr = from_origin(0, 120, 30, 30)
        counties = gpd.GeoDataFrame({"fips": ["A", "B"]},
                                    geometry=[box(0, 0, 60, 120), box(60, 0, 120, 120)],
                                    crs=crs)  # fmt: skip
        hucs = gpd.GeoDataFrame({"huc12": ["H"]}, geometry=[box(0, 60, 120, 120)],
                                crs=crs)  # fmt: skip
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "CDL_2000_34.tif"
            with rasterio.open(p, "w", driver="GTiff", width=4, height=4, count=1,
                               dtype="uint8", crs=crs, transform=tr) as dst:  # fmt: skip
                dst.write(a, 1)
            t = cropland_coverage.count_year(p, counties, hucs)
        got = {(r.fips, r.huc12, r.code): r.px for r in t.itertuples()}
        self.assertEqual(got, {("A", "H", 1): 4, ("B", "H", 5): 4,
                               ("A", "", 63): 4, ("B", "", 242): 4})  # fmt: skip


class TestCountiesInsideBBox(unittest.TestCase):
    def test_whole_counties_inside_the_clip(self):
        from agri_sfincs import config, domain

        f = config.REGION_DIR / "counties.gpkg"
        if not f.exists():
            self.skipTest("no counties.gpkg")
        import geopandas as gpd

        import fetch_mrms

        c = gpd.read_file(f)
        b = c[c.fips.isin(domain.COUNTIES)].to_crs(4326).total_bounds
        w, s, e, n = fetch_mrms.BBOX
        self.assertTrue(w < b[0] and s < b[1] and e > b[2] and n > b[3], (b, fetch_mrms.BBOX))

    def test_mrms_bbox_matches_domain(self):
        """fetch_mrms.py (grib env, cannot import the package) keeps a copy of the clip."""
        import fetch_mrms

        from agri_sfincs import domain

        self.assertEqual(fetch_mrms.BBOX, domain.RAIN_BBOX)


if __name__ == "__main__":
    unittest.main()
