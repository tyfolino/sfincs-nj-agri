"""Build the static SFINCS model: quadtree grid, bed, mask + water-level boundary,
roughness, subgrid, curve-number-with-recovery infiltration.

Adapted from nj_bight_sfincs ``nj_sfincs/model.py`` ``build_static`` /
``apply_mask_and_boundary`` (2026-10-02), much simplified because this domain is
different in kind:

* everything inside the model outline (agri_sfincs.region) is ACTIVE at any depth;
* the only boundary is a WATER-LEVEL one, on edge cells in water deeper than
  ``WL_ZMAX`` — the mid-bay / mid-river edge and the river cross-sections at each end;
* the landward edge is a drainage divide, so it stays a CLOSED wall (SFINCS's default
  for an active cell next to inactive ground). Bight's rule that every dry edge cell is
  free outflow does NOT apply: no create_boundary(btype="outflow") here.

Two hydromt quirks are patched in ``sfincs.inp`` after writing (as bight does for
``cna``): hydromt names ``infiltration_file = infiltration.nc`` but writes smax / seff /
ks into the quadtree file, so the key is pointed at the quadtree file; and
``storecumprcp = 1`` is forced.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr

from agri_sfincs import config, domain, region

#: The bed is ONE pre-merged raster per model (``StaticConfig.elevation``), not a
#: first-wins list of tiers: a list cannot say "CUDEM only where it is deeper than the
#: lidar water surface", and CUDEM's flat ~0 m inland-water "beds" (Union Lake -0.20
#: under a 7.56 m surface) must never reach the model (user 2026-10-02; bight FINDINGS
#: §54a). ``bed_merged`` (scripts/build_bed.py, v0) carries the lidar water surface in
#: rivers above head of tide; ``bed_v1`` adds the river-bed burn (FINDINGS §11).
#: Water-level boundary on edge faces with bed below this (m NAVD88) ...
WL_ZMAX = -1.0
#: ... AND inside OPEN WATER = where the lidar has no data and CUDEM fills the bed
#: (bed_source code 3, scripts/build_bed.py), buffered by WL_ZONE_M. v0's first build
#: forced a -1.1 m pond on the inland West Creek / Dennis Creek divide (-74.907, 39.176);
#: ponds carry a lidar surface, so they are never code 3. (A zone from Census state
#: polygons failed: up the river NJ's polygon runs to mid-river, which removed the whole
#: river leg above Marcus Hook.)
WL_ZONE_M = 300.0
WL_ZONE_DECIMATE = 16  # bed_source pixels (~3.9 m) per zone pixel (~62 m)
ROUGHNESS_TABLE = config.BIGHT_DATA / "roughness" / "NLCD_CONUS_mapping.csv"


@dataclass
class StaticConfig:
    name: str
    res: float = 100.0  # base cell size, m
    nr_subgrid_pixels: int = 10  # -> 10 m subgrid at 100 m
    hsg: str = "hsg_undrained"  # or "hsg_drained" (dual groups as drained)
    effective: float = 0.5  # initial seff = effective * smax (spin-up adjusts)
    refinement: Path | None = None  # quadtree refinement polygons (later versions)
    elevation: str = "bed_merged"  # catalog source of the ONE pre-merged bed
    #: extra hydromt data catalogs (after config.CATALOG), e.g. for a test bed kept on scratch
    catalogs: tuple = ()
    #: catalog sources of Manning's n rasters that win over the land-cover roughness where they
    #: have data (hydromt merges the roughness list first-wins), e.g. open water on the carved
    #: channels, which 30 m NLCD often calls marsh or woods (FINDINGS §40)
    manning_first: tuple = ()
    #: Structure files staged into the model as sfincs.weir / sfincs.drn (FINDINGS §10):
    #: keys "weirfile" / "drnfile" -> source path. Empty = none (v0).
    structures: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return config.MODELS / self.name


def build_static(cfg: StaticConfig) -> Path:
    import geopandas as gpd
    from hydromt_sfincs import SfincsModel
    from hydromt_sfincs import DATADIR

    root = cfg.root
    if (root / "sfincs.inp").exists():
        raise FileExistsError(f"{root} already has a model; pick a new name")
    root.mkdir(parents=True, exist_ok=True)
    outline = region.load_outline().to_crs(domain.EPSG)

    sf = SfincsModel(data_libs=[str(config.CATALOG), *map(str, cfg.catalogs)], root=str(root), mode="w+",
                     write_gis=True)  # fmt: skip

    # 1. Grid ------------------------------------------------------------------
    sf.quadtree_grid.create_from_region(
        region={"geom": outline},
        res=cfg.res,
        crs=domain.EPSG,
        rotated=False,
        refinement_polygons=(gpd.read_file(cfg.refinement) if cfg.refinement else None),
    )
    print(f"[grid] {sf.quadtree_grid.data.grid.n_face:,} faces at base {cfg.res:.0f} m")

    # 2. Face elevation --------------------------------------------------------
    elevation_list = [{"elevation": cfg.elevation}]
    sf.quadtree_elevation.create(elevation_list=elevation_list, buffer_cells=0, nrmax=2000)

    # 3. Mask: everything inside the outline; water-level BC on deep edge faces --
    sf.quadtree_mask.create_active(include_polygon=outline, all_touched=False)
    wl_zone = open_water_zone(outline)
    sf.quadtree_mask.create_boundary(btype="waterlevel", zmax=WL_ZMAX,
                                     include_polygon=wl_zone, reset_bounds=True)  # fmt: skip
    mask = sf.quadtree_grid.data["mask"].values
    z = sf.quadtree_grid.data["z"].values
    n_act, n_wl = int((mask > 0).sum()), int((mask == 2).sum())
    if (mask == 3).any():
        raise RuntimeError("outflow cells present — the divide ring must be closed")
    if n_wl == 0:
        raise RuntimeError("no water-level boundary cells — check WL_ZMAX / the outline")
    if np.isnan(z[mask > 0]).any():
        raise RuntimeError(f"{int(np.isnan(z[mask > 0]).sum())} active faces have no bed")
    print(f"[mask] {n_act:,} active faces, {n_wl:,} water-level boundary faces "
          f"(bed {np.nanmin(z[mask == 2]):+.1f}..{np.nanmax(z[mask == 2]):+.1f} m)")  # fmt: skip

    # 4. Roughness + subgrid ---------------------------------------------------
    roughness_list = [{"manning": m} for m in cfg.manning_first]
    roughness_list.append({"lulc": "nlcd_2021", "reclass_table": str(ROUGHNESS_TABLE)})
    sf.quadtree_roughness.create(roughness_list=roughness_list, nrmax=200)
    sf.quadtree_subgrid.create(
        elevation_list=elevation_list,
        roughness_list=roughness_list,
        nr_subgrid_pixels=cfg.nr_subgrid_pixels,
        nrmax=2000,
        write_dep_tif=True,
        write_man_tif=True,
    )

    # 5. Infiltration: curve number with recovery (cnb) ------------------------
    sf.quadtree_infiltration.create_cn_with_recovery(
        lulc="nlcd_2021",
        hsg=cfg.hsg,
        ksat="ksat_um_s",
        reclass_table=cn_table(Path(DATADIR) / "lulc" / "NLCD_HSG.csv"),
        effective=cfg.effective,
    )

    # 6. Output settings that every run needs ----------------------------------
    sf.config.update({"storecumprcp": 1, "storetwet": 1, "twet_threshold": 0.05})

    sf.write()
    del sf
    gc.collect()
    patch_infiltration_keys(root)
    stage_structures(root, cfg.structures)
    return root


#: inp key -> the file name a model dir carries it under.
STRUCTURE_FILES = {"weirfile": "sfincs.weir", "drnfile": "sfincs.drn"}


def stage_structures(root: Path, sources: dict | None = None) -> list[str]:
    """Copy structure files into ``root`` (when ``sources`` names any) and make sure
    ``sfincs.inp`` carries the key of every structure file the dir holds.

    Call after EVERY ``sf.write()``: hydromt's writer drops keys it does not model, and
    SFINCS silently ignores a structure file without its key (bight
    ``model._ensure_weirfile_key``). Returns the keys present."""
    import shutil

    from agri_sfincs.dikes import ensure_inp_key

    for key, src in (sources or {}).items():
        if key not in STRUCTURE_FILES:
            raise KeyError(f"unknown structure key {key!r}; known: {sorted(STRUCTURE_FILES)}")
        shutil.copyfile(src, Path(root) / STRUCTURE_FILES[key])
    keys = [k for k, f in STRUCTURE_FILES.items() if ensure_inp_key(root, k, f)]
    if keys:
        print(f"[structures] {', '.join(f'{k} = {STRUCTURE_FILES[k]}' for k in keys)}")
    return keys


def open_water_zone(outline):
    """Open water (lidar NoData -> CUDEM, bed_source == 3) inside the outline, buffered
    by WL_ZONE_M, as a GeoDataFrame in the model CRS (see WL_ZONE_M)."""
    import geopandas as gpd
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import shapes
    from shapely.geometry import shape

    with rasterio.open(config.ELEV_DIR / "bed_source.tif") as src:
        h, w = src.height // WL_ZONE_DECIMATE, src.width // WL_ZONE_DECIMATE
        a = src.read(1, out_shape=(h, w), resampling=Resampling.mode)
        tr = src.transform * src.transform.scale(src.width / w, src.height / h)
        crs = src.crs
    polys = [shape(g) for g, v in shapes((a == 3).astype("uint8"), transform=tr) if v == 1]
    water = gpd.GeoSeries(polys, crs=crs).to_crs(domain.EPSG).union_all()
    zone = water.buffer(WL_ZONE_M).intersection(outline.geometry.iloc[0])
    return gpd.GeoDataFrame(geometry=[zone], crs=domain.EPSG)


def cn_table(path: Path):
    """The NLCD x HSG curve-number table in the shape hydromt_sfincs 2.0rc2's
    ``scs_recovery_determination`` actually needs.

    🔴 Its loop matches land-cover classes against ``df_map.index`` and reads HSG
    columns from position 1 on. Read from CSV by the data catalog, the index is
    0, 1, 2 ... (the class codes sit in column 0, "Unnamed: 0"), so almost no class ever
    matched and smax came out 0 — impervious — on 96% of active faces (v0 build,
    2026-10-02). Fix: index BY the class column and keep it as column 0, which the loop
    skips.
    """
    import pandas as pd

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.index = df.iloc[:, 0].astype(int)
    return df


def patch_infiltration_keys(root: Path) -> None:
    """Point ``infiltration_file`` at the quadtree file that actually holds smax / seff
    / ks, and check those fields (see module docstring)."""
    inp = root / "sfincs.inp"
    lines = inp.read_text().splitlines()
    qtr = next(ln.split("=", 1)[1].strip() for ln in lines if ln.strip().startswith("qtrfile"))
    with xr.open_dataset(root / qtr) as ds:
        missing = [v for v in ("smax", "seff", "ks") if v not in ds]
        if missing:
            raise RuntimeError(f"{qtr} lacks {missing}: cnb infiltration was not built")
        msk = ds["mask"].values > 0
        smax, ks = ds["smax"].values[msk], ds["ks"].values[msk]
        z = ds["z"].values[msk] if "z" in ds else None
    if z is not None:
        land = z > 1.0
        frac0 = float(np.mean(smax[land] == 0)) if land.any() else 0.0
        if frac0 > 0.3:
            raise RuntimeError(
                f"smax = 0 (impervious) on {frac0:.0%} of active faces above +1 m — the "
                "curve-number lookup failed (see cn_table)"
            )
    drop = ("infiltration_file", "infiltration_type", "storecumprcp")
    lines = [ln for ln in lines if not ln.strip().startswith(drop)]
    lines += [f"{'infiltration_file':<21}= {qtr}", f"{'infiltration_type':<21}= cnb",
              f"{'storecumprcp':<21}= 1"]  # fmt: skip
    inp.write_text("\n".join(lines) + "\n")
    print(f"[infiltration] cnb from {qtr}: active smax [m] p10/50/90 "
          f"{np.percentile(smax, [10, 50, 90]).round(3).tolist()}, smax=0 on "
          f"{np.mean(smax == 0):.0%}; ks [mm/h] median {np.median(ks):.1f}")  # fmt: skip
