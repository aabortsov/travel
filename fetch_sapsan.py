#!/usr/bin/env python3
"""Fetch Sapsan train prices from RZD and build an HTML table.

This script calls the public RZD timetable endpoint to retrieve timetable and
pricing information between Moscow and Saint Petersburg. The data is filtered to
Sapsan trains (numbered above 700) whose travel time does not exceed 4 hours and
30 minutes. For each day in the selected date range, the minimal price across
the specified fare classes (Эконом, Эконом+, Базовый, Вагон-бистро) is captured.
The script then generates a responsive HTML table that can be embedded into a
website.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests

BASE_URL = "https://pass.rzd.ru/timetable/public/ru"
ALLOWED_FARE_NAMES = {
    "эконом",
    "эконом+",
    "базовый",
    "вагон-бистро",
}
MOSCOW_CODE = "2000000"
SAINT_P_CODE = "2004000"
MAX_TRAVEL_MINUTES = 4 * 60 + 30
DATE_FORMAT = "%d.%m.%Y"


@dataclasses.dataclass
class FareQuote:
    departure: dt.datetime
    weekday: str
    price: float


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date",
        type=lambda s: dt.datetime.strptime(s, DATE_FORMAT).date(),
        default=dt.date.today(),
        help="Start date (inclusive) in DD.MM.YYYY format. Defaults to today.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to fetch (starting from start-date). Defaults to 7.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sapsan_table.html"),
        help="Output HTML file.",
    )
    return parser.parse_args(argv)


def fetch_day(date: dt.date) -> Dict[str, FareQuote]:
    """Fetch timetable info for a single date.

    Returns a mapping from departure time string (HH:MM) to fare quote.
    """
    params = {
        "layer_id": "5827",
        "dir": "0",
        "tfl": "3",
        "checkSeats": "1",
        "code0": MOSCOW_CODE,
        "code1": SAINT_P_CODE,
        "dt0": date.strftime(DATE_FORMAT),
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    departures: Dict[str, FareQuote] = {}

    for segment in payload.get("tp", []):
        for train in segment.get("list", []):
            number = train.get("number")
            if not number:
                continue
            if int("".join(filter(str.isdigit, number))) <= 700:
                continue

            travel_time = train.get("timeInWay") or train.get("timeInWayMin")
            minutes = _parse_travel_minutes(travel_time)
            if minutes is None or minutes > MAX_TRAVEL_MINUTES:
                continue

            depart_str = f"{train.get('time0')}"
            depart_date_str = train.get("date0") or segment.get("date0")
            if not depart_date_str or not depart_str:
                continue

            depart_dt = _combine_date_time(depart_date_str, depart_str)
            weekday = depart_dt.strftime("%A")

            min_price = _extract_min_price(train.get("cars", []))
            if min_price is None:
                continue

            quote = FareQuote(departure=depart_dt, weekday=weekday, price=min_price)
            departures[depart_str] = quote

    return departures


def _parse_travel_minutes(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    raw = str(raw)
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 2:
            hours, minutes = parts
        elif len(parts) == 3:
            hours, minutes = parts[0], parts[1]
        else:
            return None
        try:
            return int(hours) * 60 + int(minutes)
        except ValueError:
            return None
    try:
        return int(raw)
    except ValueError:
        return None


def _combine_date_time(date_str: str, time_str: str) -> dt.datetime:
    try:
        date = dt.datetime.strptime(date_str, DATE_FORMAT).date()
    except ValueError:
        # Some responses use ISO format.
        date = dt.date.fromisoformat(date_str)
    hour, minute = map(int, time_str.split(":"))
    return dt.datetime.combine(date, dt.time(hour=hour, minute=minute))


def _extract_min_price(cars: Iterable[Dict]) -> Optional[float]:
    min_price: Optional[float] = None
    for car in cars or []:
        name_candidates = [
            str(car.get(key, ""))
            for key in ("service", "type", "tariffType", "typeLoc", "category")
        ]
        normalized = {
            candidate.strip().lower() for candidate in name_candidates if candidate
        }
        if not normalized.intersection(ALLOWED_FARE_NAMES):
            continue
        tariff = car.get("tariff") or car.get("tariffValue") or car.get("tariffFull")
        if tariff is None:
            continue
        try:
            price = float(tariff)
        except (TypeError, ValueError):
            continue
        if min_price is None or price < min_price:
            min_price = price
    return min_price


def build_table(quotes: Dict[str, Dict[str, FareQuote]]) -> str:
    """Return HTML table markup with responsive design."""
    all_departures = sorted(quotes.keys(), key=_time_key)
    weekday_order = [
        ("Monday", "Понедельник"),
        ("Tuesday", "Вторник"),
        ("Wednesday", "Среда"),
        ("Thursday", "Четверг"),
        ("Friday", "Пятница"),
        ("Saturday", "Суббота"),
        ("Sunday", "Воскресенье"),
    ]

    def render_cell(dep: str, key: str, label: str) -> str:
        quote = quotes.get(dep, {}).get(key)
        if not quote:
            return "<td class=\"empty\">—</td>"
        price_text = f"{int(quote.price):,}".replace(",", " ")
        return f"<td data-label=\"{label}\">{price_text} ₽</td>"

    rows_html = []
    for dep in all_departures:
        cells = [render_cell(dep, key, label) for key, label in weekday_order]
        rows_html.append(
            "<tr>"
            f"<th scope=\"row\" data-label=\"Время отправления\">{dep}</th>"
            + "".join(cells)
            + "</tr>"
        )

    return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      color-scheme: light dark;
      --accent: #e53935;
      --bg: #ffffff;
      --bg-dark: #121212;
      --text: #1a1a1a;
      --text-dark: #f5f5f5;
      font-family: "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 1rem;
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background: var(--bg-dark);
        color: var(--text-dark);
      }}
      table {{
        background: #1f1f1f;
      }}
    }}
    .table-wrapper {{
      max-width: 100%;
      overflow-x: auto;
      border-radius: 16px;
      box-shadow: 0 20px 45px rgba(20, 30, 55, 0.12);
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(12px);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }}
    caption {{
      text-align: left;
      padding: 1rem;
      font-size: 1.3rem;
      font-weight: 600;
      color: var(--accent);
    }}
    th,
    td {{
      padding: 0.9rem 1rem;
      border-bottom: 1px solid rgba(0, 0, 0, 0.08);
      text-align: left;
      font-size: 0.95rem;
    }}
    th {{
      font-weight: 600;
      background: rgba(229, 57, 53, 0.08);
    }}
    tbody tr:hover {{
      background: rgba(229, 57, 53, 0.12);
      transition: background 0.3s ease;
    }}
    .empty {{
      color: rgba(0, 0, 0, 0.45);
      font-style: italic;
    }}
    @media (max-width: 768px) {{
      table {{
        min-width: unset;
        border-collapse: separate;
        border-spacing: 0;
      }}
      thead {{
        display: none;
      }}
      tbody tr {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
        padding: 1rem;
        border-bottom: 1px solid rgba(0, 0, 0, 0.12);
      }}
      tbody tr th {{
        display: block;
        background: none;
        padding: 0;
        font-size: 1.1rem;
        color: var(--accent);
      }}
      tbody tr td {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.35rem 0;
        border: none;
      }}
      tbody tr td::before {{
        content: attr(data-label);
        font-weight: 600;
        margin-right: 0.75rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="table-wrapper">
    <table>
      <caption>Минимальные тарифы «Сапсан» Москва → Санкт-Петербург</caption>
      <thead>
        <tr>
          <th scope="col">Время отправления</th>
          <th scope="col">Понедельник</th>
          <th scope="col">Вторник</th>
          <th scope="col">Среда</th>
          <th scope="col">Четверг</th>
          <th scope="col">Пятница</th>
          <th scope="col">Суббота</th>
          <th scope="col">Воскресенье</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def _time_key(time_str: str) -> tuple:
    hour, minute = map(int, time_str.split(":"))
    return hour, minute


def consolidate_quotes(quotes_by_day: Dict[str, Dict[str, FareQuote]]) -> Dict[str, Dict[str, FareQuote]]:
    aggregated: Dict[str, Dict[str, FareQuote]] = defaultdict(dict)
    for weekday, departures in quotes_by_day.items():
        for dep_time, quote in departures.items():
            existing = aggregated[dep_time].get(weekday)
            if existing is None or quote.price < existing.price:
                aggregated[dep_time][weekday] = quote
    return aggregated


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    quotes_by_day: Dict[str, Dict[str, FareQuote]] = {}

    for offset in range(args.days):
        current_date = args.start_date + dt.timedelta(days=offset)
        try:
            departures = fetch_day(current_date)
        except requests.HTTPError as exc:
            print(f"Failed to fetch data for {current_date:%d.%m.%Y}: {exc}", file=sys.stderr)
            continue
        quotes_by_day[current_date.strftime("%A")] = departures

    consolidated = consolidate_quotes({
        weekday: {
            dep: dataclasses.replace(quote, weekday=weekday)
            for dep, quote in departures.items()
        }
        for weekday, departures in quotes_by_day.items()
    })

    html = build_table(consolidated)
    args.output.write_text(html, encoding="utf-8")
    print(f"Saved table to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
