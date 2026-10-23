"""Local-window yardstick: expected = station MN (ratio x reference's published MN) x f,
f = window range / published MN interpolated between the two nearest observed gauges."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from check_creek_tides import mean_range, creek_of
from agri_sfincs import config, runs, waterlevel
from pyproj import Transformer
t0, t1 = "2023-05-24", "2023-06-01"
MN = {"8557380": 1.242, "8536110": 1.478, "8537121": 1.698, "8551910": 1.628, "8540433": 1.712, "8545240": 1.859}
LL = {"8557380": (-75.1193, 38.7828), "8536110": (-74.96, 38.9683), "8537121": (-75.3767, 39.3054),
      "8551910": (-75.5719, 39.5583), "8540433": (-75.4095, 39.8118), "8545240": (-75.142, 39.9331)}
tr = Transformer.from_crs(4326, 32618, always_xy=True)
f = {}
for s in MN:
    o = pd.read_csv(f"data/gauges/noaa/{s}_hourly_mllw.csv.gz", index_col=0, parse_dates=True)["wl_m_mllw"][t0:t1]
    f[s] = np.subtract(*mean_range(o)) / MN[s]
G = {s: tr.transform(*LL[s]) for s in MN}
def fac(lon, lat):
    x, y = tr.transform(lon, lat)
    d = {s: np.hypot(G[s][0] - x, G[s][1] - y) for s in MN}
    a, b = sorted(d, key=d.get)[:2]
    return (f[a] * d[b] + f[b] * d[a]) / (d[a] + d[b])
off = pd.read_csv(config.CHANNELS_DIR / "coops_offsets.csv", dtype={"id": str, "ref": str})
off = off[off.ref.isin(MN)]
creek = creek_of()
runs_ = sys.argv[1:]
zs = {r: waterlevel.his_series(runs.resolve(r)) for r in runs_}
rows = []
for r in off.itertuples():
    k = f"coops_{r.id}"
    if not all(k in zs[x] for x in runs_):
        continue
    mn_st = r.h_high * MN[r.ref]
    o = pd.read_csv(f"data/gauges/noaa/{r.ref}_hourly_mllw.csv.gz", index_col=0, parse_dates=True)["wl_m_mllw"][t0:t1]
    old = r.h_high * np.subtract(*mean_range(o)) if r.ref in ("8551910", "8545240") else np.nan
    new = mn_st * fac(r.lon, r.lat)
    row = dict(creek=creek.get(r.id, "(bay shore)"), station=r.name[:30], ref=r.ref[-4:], old_exp=old, new_exp=new)
    for x in runs_:
        h, l = mean_range(zs[x][k][t0:t1].resample("1h").mean())
        row[x.split("_")[-1]] = (h - l) / new
    rows.append(row)
df = pd.DataFrame(rows).sort_values(["creek", "station"])
print({k[-4:]: round(v, 3) for k, v in f.items()})
print(df.round(2).to_string(index=False))
