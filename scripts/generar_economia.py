"""Build the static economy dataset without changing the provincial sources."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sqlite3

from actualizar_datos import atomic_write


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "Series_macro/Economia/base_pib_provincias_subtotales_monedas.json"
REAL, NOMINAL = "Pesos 2004", "Pesos Corrientes"


def percent(value, denominator):
    if value is None or not denominator:
        return None
    return round(100 * value / denominator, 8)


def growth(current, previous):
    return percent(current - previous, previous) if current is not None and previous else None


def load_source(path, names):
    series = {}
    for row in json.loads(path.read_text(encoding="utf-8-sig")):
        name = row["provincia"]
        if name not in names:
            continue
        year, unit, level = row["anio"], row["moneda"], row["clasificacion"]
        activity = row["sector_actividad_economica"]
        if level.startswith("Total "):
            key = (name, year, unit, "", "")
        elif level == "Subtotal":
            key = (name, year, unit, activity, "")
        elif level in ("Detalle", "Detalle inferido"):
            key = (name, year, unit, row["sector_al_que_pertenece"], activity)
        else:
            raise ValueError(f"Unknown classification: {level}")
        if key in series:
            raise ValueError(f"Duplicate PBG row: {key}")
        value = row["dato"]
        if value is not None and not math.isfinite(value):
            raise ValueError(f"Invalid PBG value: {key}")
        series[key] = value
    return series


def fiscal_data(database):
    fiscal = defaultdict(dict)
    debt = {}
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        for province, period, amount in connection.execute("""
            SELECT province_id, period, nominal_ars_m FROM fiscal_flows
            WHERE entity = 'APNOF' AND concept_id = 'resultado_financiero'
              AND nominal_ars_m IS NOT NULL
        """):
            fiscal[province][period] = amount
        for province, period, amount in connection.execute("""
            SELECT province_id, period, gross_debt_ars_m FROM debt_liquidity
            WHERE period LIKE '%Q4' AND gross_debt_ars_m IS NOT NULL
        """):
            debt[province, int(period[:4])] = amount
    return fiscal, debt


def build_economy(source, database, provinces):
    series = load_source(source, {*provinces.values(), "Nacional"})
    fiscal, debt = fiscal_data(database)
    coverage = defaultdict(set)
    groups = defaultdict(lambda: defaultdict(set))
    for name, year, unit, sector, activity in series:
        if not sector and unit == REAL:
            coverage[name].add(year)
        elif sector:
            groups[name][sector].add(activity)
    if not coverage["Nacional"]:
        raise ValueError("No national real aggregate found in PBG source")

    result = {}
    for province, name in provinces.items():
        if not coverage[name]:
            continue
        annual = []
        for year in sorted(coverage[name]):
            real = series[name, year, REAL, "", ""]
            nominal = series.get((name, year, NOMINAL, "", ""))
            prior = series.get((name, year - 1, REAL, "", ""))

            def activity_row(sector, activity=""):
                value = series.get((name, year, NOMINAL, sector, activity))
                current = series.get((name, year, REAL, sector, activity))
                previous = series.get((name, year - 1, REAL, sector, activity))
                return {
                    "name": activity or sector,
                    "nominal": value,
                    "share": percent(value, nominal),
                    "growth": growth(current, previous),
                    "contribution": percent(current - previous, prior)
                    if current is not None and previous is not None else None,
                }

            sectors = [
                {**activity_row(sector), "detail": [
                    activity_row(sector, activity) for activity in sorted(activities - {""})
                ]}
                for sector, activities in groups[name].items() if "" in activities
            ]
            values = [row["nominal"] for row in sectors]
            contributions = [row["contribution"] for row in sectors]
            real_growth = growth(real, prior)
            quarterly = [fiscal[province].get(f"{year}Q{q}") for q in range(1, 5)]
            annual_balance = math.fsum(quarterly) if None not in quarterly else None
            national_real = series.get(("Nacional", year, REAL, "", ""))
            annual.append({
                "year": year,
                "nominal": nominal,
                "real": real,
                "nationalReal": national_real,
                "growth": real_growth,
                "nationalGrowth": growth(national_real, series.get(("Nacional", year - 1, REAL, "", ""))),
                "nationalShare": percent(nominal, series.get(("Nacional", year, NOMINAL, "", ""))),
                "debtRatio": percent(debt.get((province, year)), nominal),
                "balanceRatio": percent(annual_balance, nominal),
                "sectors": sectors,
                "nominalResidual": nominal - math.fsum(values) if nominal is not None and None not in values else None,
                "contributionResidual": real_growth - math.fsum(contributions)
                if real_growth is not None and None not in contributions else None,
            })
        result[province] = annual
    if not result:
        raise ValueError("No PBG coverage matched the dashboard provinces")
    return {"provinces": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbg", type=Path, default=SOURCE)
    parser.add_argument("--database", type=Path, default=ROOT / "data/base_consolidada.sqlite")
    parser.add_argument("--dashboard", type=Path, default=ROOT / "data/dashboard_data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/economia.js")
    args = parser.parse_args()
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    provinces = {key: value["name"] for key, value in dashboard["provinces"].items()}
    data = build_economy(args.pbg, args.database, provinces)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    atomic_write(args.output, f"window.PROVINCIAL_ECONOMY = {encoded};\n")
    for province, rows in data["provinces"].items():
        print(f"{province}: {rows[0]['year']}-{rows[-1]['year']}; "
              f"debt {sum(r['debtRatio'] is not None for r in rows)} years, "
              f"balance {sum(r['balanceRatio'] is not None for r in rows)} years")


if __name__ == "__main__":
    main()
