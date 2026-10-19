"""Data loaders for the famine early-warning exploratory dataset.

Every loader returns a tidy pandas DataFrame (or GeoDataFrame) with parsed
dates, consistent column names and categorical dtypes where useful.

Layout expected under DATA_DIR (default: <repo>/data, override with $FAMINE_DATA_DIR):
    inputs/   acled_conflict.csv, acled_conflict_index.csv, fao_prices.csv,
              fews_current_situation.csv, soil_moisture.csv, world_bank_cpi.csv
    outputs/  ml1.csv, ml2.csv, smart_{80,120,180}_day.csv
    regions/  <country>.geojson
"""

from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.environ.get("FAMINE_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))

COUNTRIES = ["Guatemala", "Kenya", "Malawi", "Nigeria", "Somalia", "Uganda"]
SMART_WINDOWS = [80, 120, 180]
# FEWS NET "Most Likely" scenario projections (not machine learning).
ML_HORIZONS = {"ml1": "near-term projection (current period)", "ml2": "medium-term projection (next period)"}

IPC_PHASES = {1: "Minimal", 2: "Stressed", 3: "Crisis", 4: "Emergency", 5: "Famine"}
IPC_DTYPE = pd.CategoricalDtype([1, 2, 3, 4, 5], ordered=True)
CHANGE_DTYPE = pd.CategoricalDtype(["improve", "none", "worsen"], ordered=True)

# Short alias for the long inflation-adjusted price column name.
REAL_PRICE = "real_price_2025"
_RENAME = {"2025_inflation_adjusted_price": REAL_PRICE}


def norm_region(name: str) -> str:
    """Accent/punctuation-insensitive key for joining region names across sources."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _read(rel: str, dates: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / rel).rename(columns=_RENAME)
    for c in dates or []:
        df[c] = pd.to_datetime(df[c])
    if "country" in df:
        df["country"] = df["country"].astype("category")
    return df


def _ipc(s: pd.Series) -> pd.Series:
    return s.round().astype("Int64").astype(IPC_DTYPE)


# --------------------------------------------------------------------------- outputs

@lru_cache
def load_ml(horizon: str = "ml1") -> pd.DataFrame:
    """FEWS NET Most-Likely IPC-phase projections. horizon: 'ml1' (period starting at issue) or 'ml2' (following period).

    Adds lead_days (valid_from - issued) and window_days (valid_until - valid_from).
    """
    if horizon not in ML_HORIZONS:
        raise ValueError(f"horizon must be one of {list(ML_HORIZONS)}")
    df = _read(f"outputs/{horizon}.csv", ["issued", "valid_from", "valid_until"])
    df["predicted_ipc"] = _ipc(df["predicted_ipc"])
    df["area_type"] = df["area_type"].astype("category")
    df["lead_days"] = (df["valid_from"] - df["issued"]).dt.days
    df["window_days"] = (df["valid_until"] - df["valid_from"]).dt.days + 1
    df["region_key"] = df["region"].map(norm_region)
    df.insert(0, "horizon", horizon)
    return df


def load_ml_all() -> pd.DataFrame:
    return pd.concat([load_ml("ml1"), load_ml("ml2")], ignore_index=True)


@lru_cache
def load_smart(window: int = 120) -> pd.DataFrame:
    """SMART soil-moisture trigger output for a rolling window (80/120/180).

    Note: the rolling window is counted in observations, not calendar days
    (exactly window-1 leading NaNs per region), and observations are ~2-3 days apart.
    """
    if window not in SMART_WINDOWS:
        raise ValueError(f"window must be one of {SMART_WINDOWS}")
    df = _read(f"outputs/smart_{window}_day.csv", ["date"])
    df["region"] = df["region"].astype("category")
    df["predicted_change"] = df["predicted_change"].astype(CHANGE_DTYPE)
    df["above_threshold"] = df["smart_coefficient"] > df["smart_threshold"]
    df.insert(0, "window", window)
    return df.sort_values(["region", "date"], ignore_index=True)


def load_smart_all() -> pd.DataFrame:
    return pd.concat([load_smart(w) for w in SMART_WINDOWS], ignore_index=True)


# --------------------------------------------------------------------------- inputs

@lru_cache
def load_fews() -> pd.DataFrame:
    """FEWS NET observed current-situation IPC phase (ground truth for ML outputs)."""
    df = _read("inputs/fews_current_situation.csv", ["date"])
    df["ipc"] = _ipc(df["ipc"])
    df["area_type"] = df["area_type"].astype("category")
    df["region_key"] = df["region"].map(norm_region)
    return df


@lru_cache
def load_soil_moisture() -> pd.DataFrame:
    """Satellite soil moisture (m3/m3) averaged over region; valid_cells = grid cells contributing."""
    df = _read("inputs/soil_moisture.csv", ["date"])
    df["region"] = df["region"].astype("category")
    return df.sort_values(["country", "region", "date"], ignore_index=True)


@lru_cache
def load_prices() -> pd.DataFrame:
    """FAO GIEWS monthly food prices; real_price_2025 is deflated to 2025 local currency."""
    df = _read("inputs/fao_prices.csv", ["date"])
    for c in ["region", "commodity", "price_type", "unit"]:
        df[c] = df[c].astype("category")
    df["currency"] = df["unit"].astype(str).str.split("/").str[0].astype("category")
    return df


@lru_cache
def load_conflict(freq: str = "monthly") -> pd.DataFrame:
    """ACLED conflict counts. freq='monthly' (acled_conflict.csv) or 'annual' (acled_conflict_index.csv)."""
    if freq == "monthly":
        return _read("inputs/acled_conflict.csv", ["date"])
    if freq == "annual":
        df = _read("inputs/acled_conflict_index.csv")
        df["index_level"] = df["index_level"].astype(
            pd.CategoricalDtype(["Low/Inactive", "Turbulent", "High", "Extreme"], ordered=True))
        df["index_ranking"] = df["index_ranking"].astype("Int64")
        return df
    raise ValueError("freq must be 'monthly' or 'annual'")


@lru_cache
def load_cpi() -> pd.DataFrame:
    """World Bank annual CPI (2010 = 100). Somalia is not included."""
    return _read("inputs/world_bank_cpi.csv")


# --------------------------------------------------------------------------- regions

def load_regions(country: str | None = None, layer: str | None = None):
    """Admin boundaries (geoBoundaries) as a GeoDataFrame in EPSG:4326.

    layer: 'country' (ADM0), 'admin1' (ADM1) or 'districts' (ADM2). Livelihood zones used
    by FEWS/ML are NOT present here; only Guatemala districts join (via region_key).
    """
    import geopandas as gpd

    names = [country] if country else COUNTRIES
    gdf = pd.concat([gpd.read_file(DATA_DIR / "regions" / f"{c.lower()}.geojson") for c in names],
                    ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    if layer:
        gdf = gdf[gdf["layer"] == layer].reset_index(drop=True)
    gdf["region_key"] = gdf["region"].map(norm_region)
    return gdf


LZ_SHAPEFILE = "regions/livelihood_zones/feature_livelihood_zone_current_Livelihood Zone.shp"

# FEWS/ML zone name (2018 Nigeria map) -> name in the current (2023-revised) shapefile.
# These three zones were renamed and may have been redrawn in 2023; 2019 Nigeria reports use the
# 2014 map, whose zones are not in the current shapefile at all.
NIGERIA_ZONE_RENAMES = {
    "Central sorghum, maize, groundnuts, cowpeas, and sesame": "Central sorghum, maize, groundnut, cowpeas, sesame and rice",
    "Cocoa dominant with oil palm, cereals, and tubers": "Cocoa dominant with oil palms, cereals, and tubers",
    "Chad Basin: masakwa flood-recession sorghum and wheat": "Masakwa flood-recession sorghum, cowpea, groundnut, and onion",
}


def zone_key(country: str, region: str) -> str:
    """Join key from a FEWS/ML (country, region) to the livelihood-zone shapefile."""
    if country == "Nigeria":
        region = NIGERIA_ZONE_RENAMES.get(region, region)
    return norm_region(region)


def load_livelihood_zones(country: str | None = None):
    """Current FEWS NET livelihood zones (one shapefile, all countries) for COUNTRIES, EPSG:4326.

    The shapefile ships without a .prj; coordinates are geographic degrees. Adds `zone_key`, which
    matches `zone_key(country, region)` for FEWS/ML rows (Kenya, Malawi, Uganda: 100%; Nigeria
    2020+: 100% via NIGERIA_ZONE_RENAMES; Nigeria 2019: no match, older map).
    """
    import geopandas as gpd

    gdf = gpd.read_file(DATA_DIR / LZ_SHAPEFILE).set_crs(4326, allow_override=True)
    gdf = gdf[gdf["country"].isin([country] if country else COUNTRIES)]
    gdf = gdf[["country", "FNID", "LZCODE", "LZNAMEEN", "EFF_YEAR", "layer_name", "geometry"]].rename(
        columns={"FNID": "fnid", "LZCODE": "lzcode", "LZNAMEEN": "zone", "EFF_YEAR": "eff_year", "layer_name": "map_version"})
    gdf["zone_key"] = gdf["zone"].map(norm_region)
    return gdf.reset_index(drop=True)


# --------------------------------------------------------------------------- WFP (HDX)

WFP_ISO3 = {"Guatemala": "gtm", "Kenya": "ken", "Malawi": "mwi", "Nigeria": "nga", "Somalia": "som", "Uganda": "uga"}


@lru_cache
def load_wfp_prices() -> pd.DataFrame:
    """WFP VAM market prices from HDX (external/wfp/wfp_food_prices_<iso3>.csv), all COUNTRIES.

    `priceflag`: 'actual' = a single observed price; 'aggregate' = WFP's monthly average of that
    market's own observations (most data since 2019 carries this flag). Both are market-level.
    """
    frames = []
    for country, iso in WFP_ISO3.items():
        df = pd.read_csv(DATA_DIR / "external/wfp" / f"wfp_food_prices_{iso}.csv", parse_dates=["date"], low_memory=False)
        frames.append(df.assign(country=country))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["market_id"].notna()].astype({"market_id": int})
    for c in ["country", "admin1", "admin2", "category", "commodity", "unit", "priceflag", "pricetype", "currency"]:
        df[c] = df[c].astype("category")
    return df


@lru_cache
def load_wfp_markets(active_since: str | None = "2019-01-01") -> pd.DataFrame:
    """WFP markets with coordinates; optionally only those with at least one price since `active_since`."""
    frames = [pd.read_csv(DATA_DIR / "external/wfp" / f"wfp_markets_{iso}.csv").assign(country=c)
              for c, iso in WFP_ISO3.items()]
    m = pd.concat(frames, ignore_index=True).dropna(subset=["latitude", "longitude"])
    m = m[~((m["latitude"] == 0) & (m["longitude"] == 0))].astype({"market_id": int})
    if active_since:
        p = load_wfp_prices()
        active = set(p.loc[p["date"] >= active_since, "market_id"])
        m = m[m["market_id"].isin(active)]
    return m.reset_index(drop=True)


# --------------------------------------------------------------------------- joins

def ml_vs_observed(horizon: str = "ml1") -> pd.DataFrame:
    """Pair each forecast with FEWS observations whose date falls inside its validity window."""
    ml = load_ml(horizon)
    obs = load_fews()[["date", "country", "region", "ipc"]]
    m = ml.merge(obs, on=["country", "region"], how="inner")
    m = m[(m["date"] >= m["valid_from"]) & (m["date"] <= m["valid_until"])].copy()
    m["error"] = m["predicted_ipc"].astype(int) - m["ipc"].astype(int)
    return m.reset_index(drop=True)


def load_all() -> dict[str, pd.DataFrame]:
    """Every tabular dataset keyed by short name."""
    return {
        "ml1": load_ml("ml1"), "ml2": load_ml("ml2"),
        **{f"smart_{w}": load_smart(w) for w in SMART_WINDOWS},
        "fews": load_fews(), "soil_moisture": load_soil_moisture(), "prices": load_prices(),
        "conflict_monthly": load_conflict("monthly"), "conflict_annual": load_conflict("annual"),
        "cpi": load_cpi(),
    }
