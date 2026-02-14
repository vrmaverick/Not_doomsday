# Pandemic API Field Reference
Generated: 2026-02-14T15:12:14.811058

Quick lookup of every field from every API source.

---

## 1. WHO GHO API
Base: `https://ghoapi.azureedge.net/api`
Auth: None needed
Update frequency: Annual

Records in sample: 7142
Wrapper key: `value`

| Field | Type | Sample | Nullable |
|-------|------|--------|----------|
| `Id` | int | `100798` | False |
| `IndicatorCode` | str | `WHS3_49` | False |
| `SpatialDimType` | str | `COUNTRY` | False |
| `SpatialDim` | str | `CYP` | False |
| `ParentLocationCode` | str | `EUR` | False |
| `TimeDimType` | str | `YEAR` | False |
| `ParentLocation` | str | `Europe` | False |
| `Dim1Type` | null | `None` | True |
| `TimeDim` | int | `1992` | False |
| `Dim1` | null | `None` | True |
| `Dim2Type` | null | `None` | True |
| `Dim2` | null | `None` | True |
| `Dim3Type` | null | `None` | True |
| `Dim3` | null | `None` | True |
| `DataSourceDimType` | null | `None` | True |
| `DataSourceDim` | null | `None` | True |
| `Value` | str | `0` | False |
| `NumericValue` | float | `0.0` | False |
| `Low` | null | `None` | True |
| `High` | null | `None` | True |
| `Comments` | null | `None` | True |
| `Date` | str | `2019-09-11T08:28:01+02:00` | False |
| `TimeDimensionValue` | str | `1992` | False |
| `TimeDimensionBegin` | str | `1992-01-01T00:00:00+01:00` | False |
| `TimeDimensionEnd` | str | `1992-12-31T00:00:00+01:00` | False |

**Key fields for model:**
- `SpatialDim` → country code (ISO3)
- `ParentLocationCode` → region (EUR, AFR, etc)
- `TimeDim` → year (int)
- `NumericValue` → the actual measurement
- `Low` / `High` → confidence interval bounds
- `IndicatorCode` → which disease metric

---

## 2. Google Trends (pytrends)
Auth: None (but rate limited)
Update frequency: Weekly

**Output format:** pandas DataFrame, saved as CSV

| Field | Type | Description |
|-------|------|-------------|
| `date` (index) | datetime | Week start date |
| `<keyword>` | int (0-100) | Relative search interest — 100 = peak in timeframe |
| `isPartial` | bool | True if the week is incomplete (current week) |

**Regional output fields:**
| Field | Type | Description |
|-------|------|-------------|
| `geoName` (index) | str | Country name |
| `geoCode` | str | ISO2 country code |
| `<keyword>` | int (0-100) | Relative interest — 100 = highest country |

**Related queries output:**
| Field | Type | Description |
|-------|------|-------------|
| `query` | str | The related search term |
| `value` | int | Score (top) or % growth (rising) |

**Key for model:**
- Values are RELATIVE (0-100), not absolute search counts
- Compare across time, not across keywords in different pulls
- Rising queries with value > 1000 = breakout (potential emerging threat)
- Regional data = where to focus attention

---

## 3. GDELT API
Base: `https://api.gdeltproject.org/api/v2/doc/doc`
Geo: `https://api.gdeltproject.org/api/v2/geo/geo`
Auth: None
Update frequency: Every 15 minutes

**Article fields** (from artlist mode):

| Field | Type | Sample |
|-------|------|--------|
| `url` | str | `https://www.ecofinagency.com/news-services/1402-52` |
| `url_mobile` | str | `` |
| `title` | str | `Weekly Health Update | Africa CDC Advances Health ` |
| `seendate` | str | `20260214T181500Z` |
| `socialimage` | str | `https://www.ecofinagency.com/media/k2/items/cache/` |
| `domain` | str | `ecofinagency.com` |
| `language` | str | `English` |
| `sourcecountry` | str | `Nigeria` |

**Timeline volume fields** (from timelinevol mode):
```json
{
  "query_details": {"title": "...", "date_resolution": "day"},
  "timeline": [{
    "series": "Volume Intensity",
    "data": [{"date": "20260116T000000Z", "value": 0.123}, ...]
  }]
}
```

**GeoJSON fields** (from geo endpoint):
```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [lon, lat]},
  "properties": {"name": "Location Name", "count": 5}
}
```

**Constraints:**
- Geo endpoint: max timespan = `7d`
- Article list: max `250` records per call
- `seendate` format: `20260214T181500Z`
- `sourcecountry` = where the article was published, NOT where the outbreak is

---

## 4. disease.sh
Base: `https://disease.sh/v3`
Auth: None
Update frequency: Varies (COVID data mostly frozen)

**Country snapshot fields:**

| Field | Type | Description |
|-------|------|-------------|
| `country` | str | Country name |
| `countryInfo.iso2` | str | ISO2 code |
| `countryInfo.iso3` | str | ISO3 code |
| `countryInfo.lat` | float | Latitude |
| `countryInfo.long` | float | Longitude |
| `continent` | str | Continent name |
| `population` | int | Country population |
| `cases` | int | Total cumulative cases |
| `deaths` | int | Total cumulative deaths |
| `recovered` | int | Total recovered |
| `active` | int | Currently active cases |
| `critical` | int | Currently critical |
| `casesPerOneMillion` | float | Cases normalized by pop |
| `deathsPerOneMillion` | float | Deaths normalized by pop |
| `tests` | int | Total tests administered |
| `testsPerOneMillion` | float | Tests normalized by pop |

**Historical fields:** `{date: cumulative_count}` dict
- Dates formatted as `M/D/YY` (e.g., `2/8/23`)
- Values are CUMULATIVE — subtract consecutive days for daily counts

**Flu ILINet fields:**
| Field | Type | Description |
|-------|------|-------------|
| `week` | str | `YYYY - WW/52` format |
| `age 0-4` | int | ILI cases ages 0-4 |
| `age 5-24` | int | ILI cases ages 5-24 |
| `age 25-49` | int | ILI cases ages 25-49 |
| `age 50-64` | int | ILI cases ages 50-64 |
| `age 64+` | int | ILI cases ages 64+ |
| `totalILI` | int | Total influenza-like illness cases |

---

## Country Code Mapping

APIs use different country identifiers:
| API | Format | Example |
|-----|--------|---------|
| WHO GHO | ISO3 | `IND`, `USA`, `NGA` |
| pytrends | ISO2 | `IN`, `US`, `NG` |
| GDELT | Full name | `India`, `United States`, `Nigeria` |
| disease.sh | Full name + ISO2/3 | `India` + `IN` + `IND` |

**You'll need a mapping table to join data across sources.**
Use `pycountry` library or a static CSV for this.

---

## Data Gaps & Gotchas

- **WHO**: Yearly only. No real-time. Some indicators stop at 2022.
- **pytrends**: Relative values (0-100), NOT absolute counts. Rate limited.
- **GDELT**: `sourcecountry` ≠ outbreak location. Articles may be duplicates.
- **disease.sh**: COVID `todayCases: 0` everywhere = data is frozen. Historical stops at 2023 for most countries.
- **Date formats**: All different. Normalize early.
- **Country codes**: All different. Normalize early.
