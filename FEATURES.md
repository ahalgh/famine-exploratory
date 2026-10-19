# Feature dictionary

Every dataset under `data/` (git-ignored), with each column, its type and range, and what it means.
Loader names refer to [`famine/loaders.py`](famine/loaders.py). Facts below were checked against the
data, not assumed. Columns marked *derived* are added by the loader.

Countries: Guatemala, Kenya, Malawi, Nigeria, Somalia, Uganda. Overall time span: 2018-12 → 2026-09.

IPC phase scale (used by `ipc` / `predicted_ipc`): 1 Minimal · 2 Stressed · 3 Crisis · 4 Emergency · 5 Famine.
Phase 5 never appears in these files.

---

## Outputs

### `outputs/ml1.csv`, `outputs/ml2.csv` — FEWS NET Most-Likely IPC projections · `load_ml("ml1"|"ml2")`

One row per issue × zone. ML1 is the near-term projection (starts on the issue date). ML2 is the
medium-term projection (starts where ML1 ends, 1–4 months after issue, and covers about 4 months).

| column | type | values | meaning |
|---|---|---|---|
| `issued` | date | ml1: 82 dates, ml2: 78 dates (2018-12 → 2026-05 / 2026-01) | projection publication month |
| `valid_from` | date | ml1 = `issued`; ml2 = 30–123 days after issue | start of projection window |
| `valid_until` | date | month-end | end of projection window |
| `country` | cat | ml1: GTM, KEN, MWI, NGA, UGA; ml2: same without Guatemala | |
| `region` | str | ml1: 455 zones; ml2: 132 | livelihood-zone name (Guatemala: district/municipality name) |
| `area_type` | cat | `livelihood zone`, `district` (Guatemala only, ml1 only) | spatial unit type |
| `predicted_ipc` | ordinal 1–4 | ml1: 53% / 31% / 13% / 3%; ml2: 57% / 28% / 11% / 4% | projected IPC phase |
| `horizon` *derived* | str | `ml1` / `ml2` | |
| `lead_days` *derived* | int | ml1: 0; ml2: 30–123 | `valid_from − issued` |
| `window_days` *derived* | int | ml1: 30–122; ml2: about 120 | length of validity window |
| `region_key` *derived* | str | | accent- and punctuation-normalised region name for joins |

Coverage: Guatemala has only the 2018-12 issue (323 districts). Uganda stops at 2024-10. Nigeria starts 2019-06.
There are no duplicate (issued, country, region) keys.

### `outputs/smart_{80,120,180}_day.csv` — SMART soil-moisture trigger · `load_smart(window)`

Irregular satellite revisit time series (median gap 2–3 days) for one sub-national region per country.
The three files have **identical** base columns. Only the derived SMART columns depend on the window.

| column | type | range | meaning |
|---|---|---|---|
| `date` | date | 2019-01-03 → 2026-07-31 | observation date |
| `country` | cat | Kenya, Malawi, Nigeria, Uganda | |
| `region` | cat | `kenya_mandera2`, `malawi`, `nigeria`, `uganda_karamoja` | soil-moisture region (matches `soil_moisture.csv` region ids) |
| `soil_moisture` | float | 0.022–0.454 m³/m³ | soil moisture for that date |
| `raw_price` | float | 85–2,521 (local currency) | staple price carried forward to the date. Best-matching FAO series: KE Nairobi maize meal, MW Lunzu maize, NG North East imported rice, UG national cassava flour |
| `real_price_2025` | float | 120–2,894 | same price deflated to 2025 currency (raw column name `2025_inflation_adjusted_price`) |
| `smart_coefficient` | float | w80: −1.5–7.4; w120: 0.11–8.4; w180: 0.76–8.2 | SMART stress coefficient over the rolling window. Null for the first w−1 observations of each region |
| `smart_threshold` | float | one constant per region × window (e.g. w120: KE 1.55, MW 4.67, NG 3.05, UG 1.13) | trigger threshold |
| `days_above_threshold` | int | 0–762 | consecutive **calendar** days the coefficient has stayed above the threshold |
| `rolling_mean` | float | ≈0.05–0.25 | rolling mean of soil moisture over w observations |
| `rolling_mean_slope` | float | ≈±0.0014 | slope of the rolling mean (positive = getting wetter) |
| `variance` | float | ≈0.01–0.12 | rolling dispersion of soil moisture |
| `triggered` | bool | 12–16% True | **True iff `days_above_threshold` > 60** (verified 100%) |
| `predicted_change` | cat | `none` / `improve` / `worsen` | `none` if not triggered, otherwise `improve` if slope > 0 and `worsen` if slope < 0 (verified 100%) |
| `window` *derived* | int | 80/120/180 | |
| `above_threshold` *derived* | bool | | `smart_coefficient > smart_threshold` |

---

## Inputs

### `inputs/fews_current_situation.csv` — observed IPC (ground truth) · `load_fews()`

| column | type | values | meaning |
|---|---|---|---|
| `date` | date | 39 dates, 2019-02 → 2026-07 (every 4 months, then monthly from 2023) | assessment month |
| `country` | cat | GTM, KEN, MWI, NGA, UGA | |
| `region` | str | 459 | zone/district name, or the country name when `area_type == country` |
| `area_type` | cat | `livelihood zone` (2,275), `district` (323, Guatemala 2019-02 only), `country` (88, 2023+) | |
| `ipc` | ordinal 1–4 | 53% / 30% / 14% / 3% | observed current IPC phase |
| `region_key` *derived* | str | | normalised name |

Every ml1/ml2 zone appears here. `country`-level rows have no projection counterpart.

### `inputs/soil_moisture.csv` · `load_soil_moisture()`

| column | type | range | meaning |
|---|---|---|---|
| `date` | date | 2019-01-01 → 2026-09-02 (irregular) | |
| `country` | cat | all 6 | |
| `region` | cat | 34 ids: `national` per country, plus `<country>` and sub-regions such as `kenya_mandera2`, `somalia_01…18`, `uganda_karamoja` | aggregation area. `national` and `<country>` are **different** series |
| `soil_moisture` | float | 0.021–0.550 m³/m³ | area-mean volumetric soil moisture |
| `valid_cells` | int | 1–681 | grid cells contributing (low values mean a noisy estimate, e.g. `somalia_01` median 1) |

### `inputs/fao_prices.csv` — FAO GIEWS food prices · `load_prices()`

| column | type | values | meaning |
|---|---|---|---|
| `date` | date | monthly, 2019-01 → 2026-08 | |
| `country` | cat | all 6 (Nigeria 64% of rows, Somalia 80 rows) | |
| `region` | cat | 50 markets/zones, including `National Average` | market |
| `commodity` | cat | 37 (maize variants, rice variants, beans, sorghum, millet, cassava, gari, yam, wheat flour, oils, goats, beef, fish, eggs, milk, bread, potatoes, plantains) | |
| `price_type` | cat | Retail (86%), Wholesale | |
| `raw_price` | float | 25 → 5,040,000 | nominal local-currency price per `unit` |
| `real_price_2025` | float | 32 → 5.39M; **80 nulls (all Somalia, no CPI)** | deflated to 2025 currency (raw name `2025_inflation_adjusted_price`) |
| `unit` | cat | 20, e.g. `NGN/Kg`, `KES/1 unit`, `NGN/100 kg`, `GTQ/Spanish quintal (46 kg)` | currency/quantity. **Normalise before comparing series** |
| `currency` *derived* | cat | GTQ, KES, MWK, NGN, SOS, UGX | prefix of `unit` |

### `inputs/acled_conflict.csv` — monthly ACLED · `load_conflict("monthly")`

93 months × 6 countries (2019-01 → 2026-09), national level.

| column | type | range | meaning |
|---|---|---|---|
| `date` | date | month start | |
| `country` | cat | all 6 | |
| `political_violence_events` | int | 0–777 | battles, explosions/remote violence, violence against civilians |
| `political_violence_fatalities` | int | 0–1,947 | |
| `civilian_targeting_events` | int | 0–462 | events targeting civilians |
| `civilian_targeting_fatalities` | int | 0–789 | |
| `demonstration_events` | int | 0–679 | protests and riots |
| `conflict_index` | float | 0–14.1 | composite monthly index (0 in 11 Malawi months). Tracks fatalities more closely (r ≈ 0.87–0.93) than demonstrations |

### `inputs/acled_conflict_index.csv` — annual ACLED · `load_conflict("annual")`

The same five count columns summed over each year (2019–2026), plus:

| column | type | values | meaning |
|---|---|---|---|
| `year` | int | 2019–2026 | |
| `conflict_index` | float | 6.4–18.4 | annual index |
| `index_level` | ordinal cat | Low/Inactive < Turbulent < High < Extreme. **Only 2023–2025** | ACLED Conflict Index category |
| `index_ranking` | Int | 5–58. **Only 2023–2025, and missing for Malawi 2023–24** | global rank (1 = worst) |

### `inputs/world_bank_cpi.csv` · `load_cpi()`

| column | type | values | meaning |
|---|---|---|---|
| `year` | int | 2014–2025 | |
| `country` | cat | GTM, KEN, MWI, NGA, UGA (**no Somalia**) | |
| `cpi` | float | 119–1,313 (2010 = 100) | consumer price index used for the 2025 price deflation |

---

## Regions

### `regions/<country>.geojson` — geoBoundaries admin units · `load_regions(country, layer)`

EPSG:4326 polygons and multipolygons. Three layers per country.

| column | meaning |
|---|---|
| `shapeName`, `shapeISO`, `shapeID`, `shapeGroup`, `shapeType` | original geoBoundaries attributes (`shapeType` ADM0/1/2) |
| `country`, `country_key`, `iso3` | country name, lowercase key, ISO3 |
| `admin_level` | ADM0 / ADM1 / ADM2 |
| `layer` | `country` / `admin1` / `districts` |
| `region` | display name (`national` for ADM0) |
| `region_id` | `<country_key>_<snake_name>`, e.g. `kenya_mandera` |
| `region_key` *derived* | normalised name for joins |

| country | admin1 | districts |
|---|---|---|
| Guatemala | 22 | 342 |
| Kenya | 47 | 290 |
| Malawi | 3 | 28 |
| Nigeria | 37 | 774 |
| Somalia | 18 | 118 |
| Uganda | 4 | 151 |

**Join caveat:** FEWS/ML livelihood zones have **no geometry here**. Only Guatemala districts join
(316/323 via `region_key`). SMART/soil-moisture region ids (`kenya_mandera2`, `somalia_05`, …) are custom
areas and are not the same as geojson `region_id`.

### `regions/livelihood_zones/…current_Livelihood Zone.shp` — FEWS NET livelihood zones · `load_livelihood_zones(country)`

The current zone map for every FEWS NET country (926 zones, 41 countries), downloaded from fews.net. It ships without a `.prj` file; the coordinates are in degrees (read as EPSG:4326). Columns kept by the loader: `country`, `fnid`, `lzcode`, `zone` (English name), `eff_year`, `map_version` (e.g. `KE_LHZ_2011`), plus a derived `zone_key`.

| country | map version | zones | FEWS/ML rows that join |
|---|---|---|---|
| Kenya | KE_LHZ_2011 | 24 | 100% |
| Malawi | MW_LHZ_2015 | 19 | 100% |
| Uganda | UG_LHZ_2013 | 42 (incl. "National Park") | 100% |
| Nigeria | NG_LHZ_2023 (22 zones from 2018, 14 revised in 2023) | 36 | 100% from 2020 on via `NIGERIA_ZONE_RENAMES`; **0% for 2019** (2014 map) |
| Guatemala | GT_LHZ_2016 | 13 | n/a (our Guatemala IPC data is by district) |
| Somalia | SO_LHZ_2015 | 19 | n/a (no IPC data) |

Join FEWS/ML rows with `zone_key(country, region)`. The three renamed Nigeria zones may also have been redrawn in 2023, so their current shapes may not exactly match the areas assessed in 2020–2023.

---

## External sources (`data/external/`, git-ignored)

### `external/wfp/` — WFP market prices (HDX, CC BY-IGO) · `load_wfp_prices()`, `load_wfp_markets()`

Per-country `wfp_food_prices_<iso3>.csv` and `wfp_markets_<iso3>.csv` from the HDX datasets "WFP food prices for <country>".

| column | meaning |
|---|---|
| `date`, `market_id`, `market`, `admin1`, `admin2`, `latitude`, `longitude` | monthly observation at a geolocated market |
| `category`, `commodity`, `commodity_id`, `unit`, `pricetype` (Retail/Wholesale), `currency`, `price`, `usdprice` | price |
| `priceflag` | `actual` = a single observation; `aggregate` = WFP's monthly average of that market's own observations. Most data since 2019 is `aggregate`; both are market-level |

972 markets have coordinates. Markets with at least one price since 2019: Kenya 225, Malawi 128, Nigeria 65, Somalia 44, Uganda 42, Guatemala 3. **Market placement follows WFP operations**: zones with more WFP markets have *higher* observed IPC (Kenya ρ = +0.47, Nigeria +0.43), so market density and travel time to a WFP market partly measure humanitarian presence, not access.

### `external/map_accessibility/` — MAP 2019 friction surfaces · `famine.access.CostGrid`

`friction_2019_{motorized,walking}_{africa,guatemala}.tif`: minutes per metre, 30 arc-seconds, EPSG:4326. Downloaded from MAP's GeoServer (layers `Accessibility__202001_Global_{Motorized,Walking_Only}_Friction_Surface`) for two boxes: Africa (2–52°E, 18°S–15°N) and Guatemala (93–88°W, 13–18.5°N). **Oceans are given a speed (~19 km/h)**, so travel is masked to the country's land; inland lakes are kept.

### `external/geonames/<CC>.txt` — GeoNames gazetteer (CC-BY)

Used for cities with population ≥ 50,000 (accessibility targets) and for geocoding the FAO markets.

---

## Derived

### `reports/zone_access_2019.csv` — travel time per livelihood zone · `famine.access.load_zone_access()`, `attach_zone_access(df)`

One row per livelihood zone (153). Built by `scripts/compute_accessibility.py`. Travel is within the country only.

| column | meaning |
|---|---|
| `country`, `zone`, `zone_key`, `fnid`, `lzcode`, `map_version`, `eff_year`, `area_km2`, `pixels` | zone identity |
| `wfp_markets_in_zone` | WFP markets active since 2019 that fall inside the zone |
| `{market,city}_{motorized,walking}_{median,p90}_h` | travel time in hours from the zone's pixels to the nearest WFP market or the nearest city of 50k+ (median and 90th percentile, weighted by area) |

Use the times to rank zones, not as literal hours: nominal road speeds make absolute times optimistic. Prefer the `city_*` columns; the `market_*` columns inherit WFP's market-placement bias.

### `reports/access_validation_{pairs,summary}.csv` — friction surface vs price co-movement

Built by `scripts/validate_access_prices.py`. Market pairs in each country, with motorized travel time, straight-line distance and the correlation of local monthly staple-price changes; Mantel tests. Result: travel time predicts co-movement (r ≈ −0.15 to −0.47, p < 0.01 in all five countries) but **no better than straight-line distance**, and adds little or nothing beyond it.

---

## Join keys at a glance

| from → to | key |
|---|---|
| ml1/ml2 ↔ fews | (`country`, `region`) with fews `date` inside [`valid_from`, `valid_until`] — `ml_vs_observed()` |
| ml1 ↔ ml2 | (`country`, `region`, `valid_from`) — the same period projected at different leads |
| smart ↔ soil_moisture | (`country`, `region`, `date`) |
| smart ↔ prices | `country` + the staple series listed above, by month |
| anything ↔ conflict / cpi | `country` + month / year |
| fews/ml (Guatemala) ↔ regions | (`country`, `region_key`) on `layer == "districts"` |
| fews/ml ↔ livelihood zones, zone access | (`country`, `zone_key(country, region)`) |
| WFP prices ↔ WFP markets | `market_id` |
