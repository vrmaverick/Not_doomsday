# Pandemic Data Pull

Full data extraction from all 4 APIs. Run in order.

## Setup
```bash
pip install -r requirements.txt
```

## Run order
```bash
python 01_who_full_pull.py              # ~2 min — pulls all disease indicators
python 02_pytrends_full_pull.py         # ~10 min — rate limited, be patient
python 03_gdelt_full_pull.py            # ~3 min — articles + geo + timelines
python 04_diseasesh_full_pull.py        # ~3 min — COVID + flu + vaccines
python 05_build_field_reference.py      # instant — generates FIELD_REFERENCE.md
```

## Output structure
```
data/
├── who/
│   ├── ALL_COMBINED.csv          ← all indicators in one file
│   ├── cholera_cases.csv
│   ├── cholera_cases_raw.json
│   ├── tb_incidence.csv
│   └── ...
├── pytrends/
│   ├── symptoms_respiratory_5y.csv
│   ├── diseases_batch0_12m.csv
│   ├── regional_fever_cough.csv
│   ├── related_disease_outbreak_rising.csv
│   ├── country_India.csv
│   └── ...
├── gdelt/
│   ├── articles_bird_flu.json
│   ├── geo_outbreak.json
│   ├── timeline_dengue_90d.json
│   ├── tone_bird_flu.json
│   └── ...
└── diseasesh/
    ├── covid_all_countries.csv
    ├── covid_historical_global.csv
    ├── covid_historical_india.csv
    ├── flu_ILINet.csv
    ├── vaccine_global.csv
    └── ...

FIELD_REFERENCE.md  ← cheat sheet of every field from every API
```
