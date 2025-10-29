# Travel Data Utilities

This repository provides a helper script to retrieve current fares for Sapsan trains
between Moscow and Saint Petersburg and render them as a responsive HTML table.

## Prerequisites

Install dependencies with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run the script to fetch prices for the next 7 days starting from today:

```bash
python fetch_sapsan.py
```

Command-line arguments:

- `--start-date DD.MM.YYYY` – first date in the range (defaults to today).
- `--days N` – number of days to fetch (defaults to 7).
- `--output PATH` – where to store the resulting HTML (defaults to `sapsan_table.html`).

The generated HTML file contains a modern, mobile-friendly table ready for embedding into a
website.
