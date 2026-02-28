# WHO-ddd-search

A Python scraper for the [WHO ATC/DDD Index](https://atcddd.fhi.no/atc_ddd_index/).

## What it collects

For every drug entry in the index the scraper extracts:

| Field | Chinese | Description |
|-------|---------|-------------|
| `atc_code` | ATC编码 | ATC classification code |
| `drug_name` | 药品名称 | International non-proprietary name |
| `ddd_value` | DDD值 | Defined Daily Dose value |
| `ddd_unit` | DDD单位 | Unit of measurement for the DDD |
| `adm_route` | 给药途径 | Route of administration |
| `note` | 备注 | Additional notes |

Results are saved to **`atc_ddd_data.csv`**.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python scraper.py
```

The script will traverse the full ATC hierarchy (levels 1–5) and write all
records to `atc_ddd_data.csv` in the current directory.

## Running tests

```bash
python -m pytest test_scraper.py -v
```
