"""Zone-level features from FEWS NET livelihood profiles / descriptions / baselines.

The reports (see scripts/fetch_livelihood_docs.py) are heterogeneous: 37 countries, 2003-2024,
four document types, zones labelled by code in some and by name only in others, and the
quantitative food / income breakdowns sometimes only in charts. Extraction is therefore done by
Claude in two stages, both cached as JSON so a run can be resumed or extended:

    segment   one call per document: given the table of contents and a heading index of every
              page, list the livelihood zones the report profiles and the pages of each.
    extract   one call per zone: given the text of its pages, fill ZoneProfile.

The schema keeps the narrative's own ranges (low/high) rather than forcing point values, and
records whether a number was stated in the text or read off a chart description.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .loaders import DATA_DIR

DOC_DIR = DATA_DIR / "external/fews_livelihood"
OUT_DIR = DATA_DIR / "derived/livelihood"

WealthGroup = Literal["very poor", "poor", "middle", "better off", "all"]
Month = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


# --------------------------------------------------------------------------- stage 1: segment

class ZoneSection(BaseModel):
    zone_code: Optional[str] = Field(description="Code as printed, e.g. 'GT01', 'NG09', 'LZ 39', 'SO15'; null if the report gives none")
    zone_name: str = Field(description="Zone name as printed in the report (English if the report is bilingual)")
    first_page: int = Field(description="Physical PDF page (1-based, as in the [p N] markers) where this zone's own profile starts")
    last_page: int = Field(description="Physical PDF page where this zone's profile ends (inclusive)")


class DocumentSegments(BaseModel):
    reference_year: Optional[int] = Field(description="Year of the field work / reference consumption year, if stated")
    zones: list[ZoneSection] = Field(description="Every zone that has its own profile section, in report order. Empty if the report has no per-zone sections.")
    overview_pages: list[int] = Field(description="Pages of national summary tables that compare zones (food/income by zone, wealth breakdown by zone)")
    notes: str = Field(description="One or two sentences on the structure, e.g. 'zones profiled by name only; one zone per 2-page fact sheet'")


SEGMENT_SYSTEM = """You index FEWS NET livelihood reports. You receive the full text of the first pages \
(title, table of contents, introduction) and then, for every physical page of the PDF, a marker [p N] \
followed by that page's first lines. Printed page numbers in the table of contents usually differ from \
physical page numbers by a fixed offset: work out the offset from the page headings, and always answer \
in physical page numbers.

List every livelihood zone that has its own profile section (a zone description, a baseline chapter, \
or a fact sheet). Do not list zones that only appear in national summary tables. If one section covers \
several zones together, list each zone with the same page range. Sections are contiguous and do not \
overlap other zones' sections, except when they are explicitly shared."""


def page_texts(txt_path: Path) -> list[str]:
    return txt_path.read_text(errors="ignore").split("\f")


def page_index(pages: list[str], head_pages: int = 8, lines_per_page: int = 5) -> str:
    """Full text of the first pages, then the first non-empty lines of every page, tagged [p N]."""
    out = ["=== FIRST PAGES (full text) ==="]
    for i, p in enumerate(pages[:head_pages], 1):
        out.append(f"[p {i}]\n{_squash(p)}")
    out.append("=== PAGE INDEX (first lines of every page) ===")
    for i, p in enumerate(pages, 1):
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        # skip the running header ("GUATEMALA Livelihood Profiles   November 2016") when present
        lines = [re.sub(r"\s{3,}", "  |  ", ln)[:140] for ln in lines[:lines_per_page + 1]]
        out.append(f"[p {i}] " + " // ".join(lines))
    return "\n".join(out)


def _squash(text: str) -> str:
    """pdftotext -layout output with runs of spaces collapsed (halves the tokens, keeps columns readable)."""
    return "\n".join(re.sub(r" {3,}", "   ", ln.rstrip()) for ln in text.splitlines() if ln.strip())


def section_text(pages: list[str], first: int, last: int) -> str:
    first, last = max(first, 1), min(last, len(pages))
    return "\n".join(f"[p {i}]\n{_squash(pages[i - 1])}" for i in range(first, last + 1))


# --------------------------------------------------------------------------- stage 2: extract

class Share(BaseModel):
    """A share of annual food (kcal) or cash income, in percent."""
    low: Optional[float] = Field(description="Lower bound in percent (equal to high for a point value)")
    high: Optional[float] = Field(description="Upper bound in percent")
    evidence: Literal["stated", "chart_text", "chart_visual", "inferred"] = Field(
        description="stated: number written in the prose or a table; chart_text: read from chart labels in the text; chart_visual: estimated from bar heights in the chart image; inferred: qualitative wording only")


class FoodSources(BaseModel):
    own_crops: Optional[Share]
    own_livestock: Optional[Share] = Field(description="Milk, meat, eggs from own animals")
    purchase: Optional[Share]
    payment_in_kind: Optional[Share] = Field(description="Food received as payment for labour")
    wild_food_fishing_hunting: Optional[Share]
    food_aid: Optional[Share] = Field(description="Food aid, school feeding, safety-net food transfers")
    gifts_other: Optional[Share]


class IncomeSources(BaseModel):
    crop_sales: Optional[Share]
    livestock_sales: Optional[Share] = Field(description="Livestock and livestock-product sales")
    agricultural_labor: Optional[Share] = Field(description="Local and migrant farm labour")
    other_casual_labor: Optional[Share] = Field(description="Non-farm casual labour: construction, portering, domestic work")
    formal_employment: Optional[Share] = Field(description="Salaried / wage employment")
    remittances: Optional[Share] = Field(description="Remittances and income from labour migration not counted above")
    self_employment_trade: Optional[Share] = Field(description="Petty trade, small business, crafts")
    natural_resources: Optional[Share] = Field(description="Firewood, charcoal, timber, wild products, fishing sales")
    transfers: Optional[Share] = Field(description="Cash transfers, safety nets, pensions, gifts")


class WealthGroupProfile(BaseModel):
    group: WealthGroup
    pct_households_low: Optional[float] = Field(description="Share of households in this group, percent (lower bound)")
    pct_households_high: Optional[float]
    household_size: Optional[float] = Field(description="Typical members per household (midpoint if a range)")
    land_cultivated_ha: Optional[float] = Field(description="Typical cultivated area in hectares (midpoint if a range); convert acres (x0.405) or manzanas (x0.7) and say so in notes")
    cattle: Optional[float] = Field(description="Typical number of cattle (midpoint)")
    shoats: Optional[float] = Field(description="Typical number of sheep plus goats (midpoint)")
    camels: Optional[float]
    food_sources: Optional[FoodSources] = Field(description="Percent of minimum annual food needs (kcal) by source; null if the report gives nothing for this group")
    income_sources: Optional[IncomeSources] = Field(description="Percent of annual cash income by source; null if not given")
    staple_self_sufficiency_months: Optional[float] = Field(description="Months per year the group lives on its own staple harvest")


Hazard = Literal["drought", "erratic_rainfall", "flood", "cyclone_hurricane", "frost_hail", "crop_pests", "crop_disease",
                 "livestock_disease", "price_spike", "market_disruption", "conflict_insecurity", "displacement",
                 "wildfire", "earthquake", "labor_demand_drop", "remittance_drop", "human_disease", "other"]

Coping = Literal["reduce_meals", "switch_to_cheaper_food", "increase_labor_sales", "labor_migration", "sell_livestock",
                 "distress_livestock_sales", "sell_assets", "borrow_credit", "gifts_from_kin", "wild_foods",
                 "charcoal_firewood_sales", "consume_seed_stock", "remove_children_school", "petty_trade", "other"]


class ZoneProfile(BaseModel):
    zone_code: Optional[str]
    zone_name: str
    livelihood_system: Literal["agricultural", "agropastoral", "pastoral", "fishing", "urban_periurban", "mixed_other"]
    population: Optional[float] = Field(description="Zone population if stated")
    main_crops: list[str] = Field(description="Main food and cash crops, most important first, lower case")
    main_livestock: list[str] = Field(description="Main livestock types, lower case")
    annual_rainfall_mm_low: Optional[float]
    annual_rainfall_mm_high: Optional[float]
    irrigation_importance: Literal["none", "low", "medium", "high", "unknown"]
    market_access: Literal["poor", "moderate", "good", "unknown"] = Field(description="Physical access to markets and roads as described")
    rainy_season_months: list[Month]
    main_harvest_months: list[Month] = Field(description="Months of the main staple harvest")
    lean_season_months: list[Month] = Field(description="Hunger / lean season months for poor households")
    peak_labor_demand_months: list[Month]
    migration_importance: Literal["none", "low", "medium", "high", "unknown"] = Field(description="Importance of labour migration and remittances to poorer households")
    hazards: list[Hazard] = Field(description="Hazards named for the zone, most frequent / severe first")
    chronic_hazards: list[Hazard] = Field(description="Subset of hazards described as frequent (e.g. every 2-3 years or more often)")
    coping_strategies: list[Coping] = Field(description="Responses households use in bad years, most common first")
    wealth_groups: list[WealthGroupProfile] = Field(description="One entry per wealth group the report defines (very poor / poor / middle / better off). Use 'all' only if the report gives zone-level shares without wealth groups.")
    food_sources_reference_year: Optional[str] = Field(description="Reference / consumption year the food and income shares describe, e.g. 'Sep 2021 - Aug 2022'")
    notes: str = Field(description="Caveats: unit conversions, numbers only in charts that the text does not give, ambiguous groups. One to three sentences.")


EXTRACT_SYSTEM = """You extract structured features from one livelihood-zone section of a FEWS NET \
livelihood report (text extracted from a PDF with its column layout; charts appear only as their axis \
and legend labels, so bar values are usually NOT in the text).

Rules:
- Record only what the section says. Use null for anything it does not give; never fill from general knowledge.
- Shares are percentages. Keep the report's ranges ("35-40%" -> low 35, high 40). A point value has low = high.
- evidence = "stated" for numbers written in prose or tables, "chart_text" for numbers you can read from \
chart labels in the text, "inferred" only for clearly quantified wording such as "about half" (-> 50).
- Food shares are of minimum annual food needs (kcal). Some reports exceed 100% for better-off groups; keep them.
- Income shares are of annual cash income. If the report gives income in currency per source, convert to shares.
- Map the report's wealth-group names onto very poor / poor / middle / better off (e.g. 'lower middle' -> middle, \
'rich' -> better off). If it only defines poor and middle, return those two.
- Months are 1-12. Read season and lean-season months from the seasonal calendar and narrative."""


# --------------------------------------------------------------------------- helpers

def doc_id(file: str) -> str:
    return Path(file).stem


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None
