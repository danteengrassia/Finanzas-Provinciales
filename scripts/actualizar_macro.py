"""Normaliza las descargas oficiales de BCRA e INDEC para el tablero."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import xlrd

from actualizar_datos import ROOT, load_macro, norm_text, period_end

PROVINCES = {
    "cordoba": "CORDOBA", "entre_rios": "ENTRE RIOS", "mendoza": "MENDOZA",
    "neuquen": "NEUQUEN", "santa_fe": "SANTA FE", "rio_negro": "RIO NEGRO",
}


def deposits(path):
    workbook = xlrd.open_workbook(path)
    amounts = defaultdict(dict)
    for suffix, offset, currency in (("nac", 2, "domestic"), ("ext", 1, "foreign")):
        sheet = workbook.sheet_by_name("Prov-Prest-Dep-" + suffix)
        for province, name in PROVINCES.items():
            matches = [i + offset for i, label in enumerate(sheet.row_values(6))
                       if norm_text(label).removesuffix(" PROVINCE") == name]
            if len(matches) != 1 or norm_text(sheet.cell_value(9, matches[0])) != "DEPOSITS":
                raise ValueError(f"Columna de depósitos no identificada: {province} {currency}")
            for row in sheet.get_rows():
                if row[0].ctype != xlrd.XL_CELL_NUMBER or row[matches[0]].ctype != xlrd.XL_CELL_NUMBER:
                    continue
                year, month = f"{row[0].value:.2f}".split(".")
                if 1990 <= int(year) <= 2100 and 1 <= int(month) <= 12:
                    amounts[province, f"{year}-{month}-01"][currency] = row[matches[0]].value
    records = []
    for (province, date), values in sorted(amounts.items()):
        domestic, foreign = values.get("domestic"), values.get("foreign")
        total = domestic + foreign if domestic is not None and foreign is not None else None
        records.append(dict(province_id=province, date=date, domestic_ars_thousands=domestic,
                            foreign_ars_thousands=foreign, total_ars_thousands=total))
    return dict(unit="miles de pesos", latest_date=max(r["date"] for r in records), records=records,
                source_url="https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/perser_pub.xls")


def ipc(path, previous):
    values = {row["date"]: row["index"] for row in previous["records"]}
    with path.open(encoding="latin-1", newline="") as file:
        for row in csv.DictReader(file, delimiter=";"):
            if row["Codigo"] == "0" and norm_text(row["Region"]) in {"NACIONAL", "TOTAL NACIONAL", "TOTAL PAIS"}:
                month = row["Periodo"]
                values[f"{month[:4]}-{month[4:]}-01"] = float(row["Indice_IPC"].replace(",", "."))
    latest = max(values)
    if latest < previous["latest_date"]:
        raise ValueError("La descarga INDEC no extendió la serie de IPC nacional.")
    return dict(latest_date=latest, latest_index=values[latest],
                source_url="https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
                records=[dict(date=date, index=value) for date, value in sorted(values.items())])


def update_fx(path, previous_monthly, previous_quarterly):
    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_index(0)
    months = defaultdict(list)
    quarters = defaultdict(list)
    for row in sheet.get_rows():
        if row[2].ctype != xlrd.XL_CELL_DATE or row[3].ctype != xlrd.XL_CELL_NUMBER:
            continue
        date = xlrd.xldate_as_datetime(row[2].value, workbook.datemode).date()
        months[date.strftime("%Y-%m")].append((date, row[3].value))
        quarters[f"{date.year}Q{(date.month-1)//3+1}"].append((date, row[3].value))
    if len(months) < 100:
        raise ValueError("Serie diaria de A3500 incompleta.")
    with previous_monthly.open(encoding="utf-8-sig", newline="") as file:
        monthly = {r["mes"][:7]: r for r in csv.DictReader(file)}
    quarterly = load_macro(previous_quarterly)
    for month, entries in sorted(months.items()):
        if month >= "2026-04" and month < max(months):
            end, close = max(entries)
            monthly[month] = dict(mes=month+"-01", a3500_promedio_mensual=mean(v for _, v in entries),
                                  a3500_fin_de_periodo=close, fecha_fin_de_periodo=end,
                                  observaciones_diarias=len(entries), tipo_dato="BCRA com3500.xls")
    for period, entries in sorted(quarters.items()):
        if period >= "2026Q2" and period < max(quarters):
            quarterly[period] = dict(average=mean(v for _, v in entries), end=max(entries)[1])
    return monthly, quarterly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("downloads", type=Path)
    args = parser.parse_args()
    cfg = json.loads((ROOT/"config/provincias.json").read_text(encoding="utf-8"))
    target = ROOT/"data/macro"
    dep = deposits(args.downloads/"perser_pub.xls")
    prices = ipc(args.downloads/"ipc_indec.csv", json.loads((target/"ipc_nacional_mensual.json").read_text(encoding="utf-8")))
    baseline = ROOT / cfg["macro_file"]
    if not baseline.is_file():
        baseline = Path(cfg["provinces"]["santa_fe"]["fiscal_db"]).parents[1] / "20260814_130319/macro_trimestral.csv"
    monthly, quarterly = update_fx(args.downloads/"com3500.xls", target/"a3500_mensual.csv", baseline)
    for filename, result in (("depositos_provinciales_mensual.json", dep), ("ipc_nacional_mensual.json", prices)):
        (target/filename).write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    with (target/"a3500_mensual.csv").open("w", encoding="utf-8", newline="") as file:
        columns = list(next(iter(monthly.values())))
        writer = csv.DictWriter(file, columns)
        writer.writeheader()
        writer.writerows(monthly.values())
    with (target/"a3500_trimestral.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("period_end", "period", "tcn_fin_a3500", "tcn_promedio_a3500"))
        writer.writerows((period_end(p), p, row["end"], row["average"]) for p, row in sorted(quarterly.items()))
    print(f"Depósitos: {dep['latest_date']} | IPC: {prices['latest_date']} | A3500: {max(quarterly)}")


if __name__ == "__main__":
    main()
