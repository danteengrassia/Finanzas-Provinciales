"""Contrato SQLite de entrada para el consolidador de provincias."""

import argparse
import csv
import re
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path

from actualizar_datos import as_float, norm_text, period_end, readonly_connection

BASE = Path(r"E:\bkpdante26\Documentos\Trabajo\Analisis Provincias")
ROOT = Path(__file__).resolve().parents[1]
OOII = "FINANCIAMIENTO DE ORGANISMOS INTERNACIONALES DE CREDITO"
BONOS = "TITULOS PUBLICOS INTERNACIONALES"
DIRECTOS = "PRESTAMOS DIRECTOS CON ORGANISMOS INTERNACIONALES"
FIELDS = (
    "uso_credito_cum", "amort_dev_cum", "intereses_dev_cum",
    "amort_pag_cum", "intereses_pag_cum",
)


def quarter(period, *, monthly_flow=False):
    text = str(period).replace("-T", "Q")
    if re.fullmatch(r"\d{4}Q[1-4]", text):
        return text
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text):
        return None
    year, month = text.split("-")
    month = int(month)
    if monthly_flow or month % 3 == 0:
        return f"{year}Q{(month - 1) // 3 + 1}"
    return None


def local_path(path):
    if path and str(path).lower().startswith("f:\\documentos\\trabajo\\analisis provincias\\"):
        return str(BASE / str(path)[len("F:\\Documentos\\Trabajo\\Analisis Provincias\\"):])
    return path or None


def fiscal_row(entity, period, key, value, source=(None, None)):
    return entity, "trimestral", "Dev", period, period_end(period), key, value, *source


def debt_row(period, key, label, level, *, category=None, group=None, currency=None,
             kind="Flujo", stock=None, flows=None):
    return (
        period, "quarterly", period_end(period), kind, int(kind == "Total"),
        int(kind in {"Detalle", "Flujo especializado"}), category or label,
        group, level, label, currency, stock,
        *((flows or {}).get(field) for field in (FIELDS[0], FIELDS[3], FIELDS[4], FIELDS[1], FIELDS[2])),
        key, level,
    )


def aggregate(values):
    return sum(values) if values and all(v is not None for v in values) else None


def build_hierarchical(source, province, auxiliary):
    cordoba = province == "cordoba"
    fiscal_tables = ("APNOF Dev Trim", "SS Dev Trim" if cordoba else "Seguridad Social Dev Trim")
    stock_table = "Stock" if cordoba else "Deuda Stock"
    detail_table = stock_table + " detalle"
    flow_tables = dict(zip(
        ("Uso credito", "Amort dev", "Intereses dev") if cordoba else
        ("Uso del credito", "Amort Dev", "Int y acc Dev", "Amort Caja", "Int y acc Caja"),
        FIELDS,
    ))
    floating_table = stock_table if cordoba else "Deuda flotante"
    tables = (*fiscal_tables, stock_table, detail_table, *flow_tables, floating_table)
    params = ",".join("?" for _ in tables)
    if cordoba:
        query = f"""
            SELECT s.*, s.currency AS origin_currency, f.url AS linked_url,
                   f.archivo_local AS linked_path
            FROM series s LEFT JOIN fuentes f USING(source_id)
            WHERE s.table_name IN ({params})
        """
    else:
        query = f"""
            SELECT s.*, f.download_endpoint AS linked_url, f.local_file AS linked_path
            FROM series s
            LEFT JOIN series_fuentes sf ON sf.series_id=s.series_id
            LEFT JOIN fuentes f ON f.source_id=sf.source_id
            WHERE s.table_name IN ({params})
        """
    by_table = defaultdict(dict)
    paths = set()
    ss_to_apnof = {}
    for row in source.execute(query, tables):
        table = row["table_name"]
        period = quarter(row["period"])
        if period is None:
            continue
        label = row["concept"].strip()
        key = row["concept_id"]
        path = tuple(part.strip() for part in (
            row["full_path"] if cordoba else " > ".join(filter(None, (row["parent_path"], label)))
        ).split(" > ") if part.strip())
        if table == detail_table:
            paths.add(path)
        if cordoba and table == fiscal_tables[0]:
            ss_to_apnof[row["excel_row"]] = key
        value = as_float(row["value"])
        if value is None:
            continue
        src = row["linked_url"], local_path(row["linked_path"])
        if cordoba:
            src = src[0] or row["source_url"], src[1] or local_path(row["source_file"])
        records = by_table[table]
        point = (period, key)
        if point in records and records[point][0] != value:
            raise ValueError(f"{province}: duplicado en {table}, {point}")
        if point not in records or not any(records[point][3]):
            records[point] = value, row, path, src

    fiscal = []
    for entity, table in zip(("APNOF", "SS"), fiscal_tables):
        for (period, key), (value, row, _, src) in by_table[table].items():
            if cordoba and entity == "SS":
                if row["excel_row"] not in {6, 42, 45, 46}:
                    continue
                key = ss_to_apnof[row["excel_row"]]
            fiscal.append(fiscal_row(entity, period, key, value, src))

    parents = {path[:size] for path in paths for size in range(1, len(path))}
    debt, floating, sources = [], [], {}
    flows = defaultdict(dict)
    for table, field in flow_tables.items():
        for (period, key), (value, row, path, _) in by_table[table].items():
            label = norm_text(row["concept"])
            level = row["level"]
            if level is None or level > 2:
                continue
            if (cordoba and level == 0) or key == "ER_DEUDA_TOTAL":
                target = "total"
            elif (cordoba and level == 1 and label == OOII) or key == "ER_DEUDA_MULTI":
                target = "multilateral"
            elif level == 2 and BONOS in label:
                target = "bonos"
            else:
                target = path if cordoba else key
            flows[period, target][field] = value

    def category(label):
        return DIRECTOS if norm_text(label) == OOII else label

    for (period, key), (value, row, path, src) in by_table[stock_table].items():
        label, level = row["concept"].strip(), row["level"]
        if (cordoba and level == 0) or key == "ER_DEUDA_TOTAL":
            debt.append(debt_row(period, "total", "TOTAL GENERAL", 0, kind="Total",
                                 stock=value, flows=flows[period, "total"]))
            sources[period] = src
        elif level == 1 and not key.startswith("ER_FLOT") and norm_text(label) != "DEUDA FLOTANTE":
            target = path if cordoba else key
            debt.append(debt_row(period, key + "|||", category(label), 1, kind="Categoria",
                                 stock=value, flows=flows[period, target]))

    for (period, key), (value, row, path, _) in by_table[detail_table].items():
        level = row["level"]
        if level is None or level < 2 or path in parents or key.startswith("ER_FLOT"):
            continue
        currency = row["origin_currency"]
        if norm_text(currency).startswith("NO INFORMADA") or currency == "ARS / USD":
            currency = None
        top = path[1] if cordoba else path[0]
        if norm_text(top) == "DEUDA FLOTANTE":
            continue
        debt.append(debt_row(period, "instrumento:" + key, row["concept"].strip(), level,
                             category=category(top), kind="Detalle", currency=currency, stock=value))

    for (period, key), fields in flows.items():
        if key in ("multilateral", "bonos"):
            label = OOII if key == "multilateral" else BONOS
            debt.append(debt_row(period, key, label, 2, kind="Flujo especializado",
                                 group=label, flows=fields))
        elif key != "total":
            debt.append(debt_row(period, "flujo:" + str(key), str(key), 2, flows=fields))

    for (period, key), (value, row, _, src) in by_table[floating_table].items():
        label = row["concept"].strip()
        if (cordoba and norm_text(label) == "DEUDA FLOTANTE") or key == "ER_FLOT_TOTAL":
            floating.append((period, "Total Deuda Flotante", value, *src))
        elif not cordoba and row["level"] == 2 and key.startswith("ER_FLOT"):
            floating.append((period, label, value, *src))
    if cordoba:
        lookup = {r["archivo_relativo"].replace("\\", "/"): (r["url"], local_path(r["archivo_local"]))
                  for r in source.execute("SELECT archivo_relativo, url, archivo_local FROM fuentes")
                  if r["archivo_relativo"]}
        with auxiliary.open(encoding="utf-8-sig", newline="") as file:
            totals = {period: (label, value, url, path) for period, label, value, url, path in floating}
            floating = []
            for row in csv.DictReader(file):
                period = quarter(row["period"])
                value = as_float(row["value_millions_pesos"])
                if period is None or value is None:
                    continue
                path = row["source_file"].split("#", 1)[0].replace("\\", "/")
                src = lookup.get(path, (None, local_path(path)))
                if norm_text(row["item"]) == "DEUDA FLOTANTE":
                    totals[period] = ("Total Deuda Flotante", value, *src)
                elif row["full_path"].count(" > ") == 1:
                    floating.append((period, row["item"], value, *src))
            floating.extend((period, *row) for period, row in totals.items())
    return fiscal, debt, sources, {}, floating


def write_bridge(province, builder, *, default_source=None, source_version="20261109", quarterly_flows=None):
    parser = argparse.ArgumentParser(description=f"Genera el puente SQLite de {province}.")
    parser.add_argument("--source", type=Path, default=default_source or BASE / {
        "mendoza": "Mendoza", "cordoba": "Cordoba", "entre_rios": "Entre Rios",
    }[province] / "database" / f"{province}_data.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "fuentes_congeladas" / f"{province}_{source_version}")
    args = parser.parse_args()
    with readonly_connection(args.source) as source:
        fiscal, debt, sources, fx, floating = builder(source, args.source)
        direct_flows = quarterly_flows(source) if quarterly_flows else {}
    if not fiscal or not debt:
        raise ValueError(f"{province}: puente sin datos fiscales o de deuda")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output) as temp:
        db_path = Path(temp) / f"{province}_data.sqlite"
        with sqlite3.connect(db_path) as db:
            db.executescript("""
                CREATE TABLE fiscal_aif_metrics_long (
                    entity TEXT, construction TEXT, basis TEXT, period TEXT,
                    period_end TEXT, item_key TEXT, value REAL, source_url TEXT,
                    local_path TEXT, PRIMARY KEY(entity, period, item_key));
                CREATE TABLE deuda_publica_long (
                    period TEXT, frequency TEXT, period_end TEXT, tipo_fila TEXT,
                    is_total INTEGER, is_detail INTEGER, acreedor TEXT, subgrupo TEXT,
                    nivel INTEGER, instrumento TEXT, moneda_instrumento TEXT,
                    stock_pesos REAL, uso_credito_cum REAL, amort_pag_cum REAL,
                    intereses_pag_cum REAL, amort_dev_cum REAL, intereses_dev_cum REAL,
                    row_key TEXT, orden INTEGER, PRIMARY KEY(period, row_key));
                CREATE TABLE fuentes (period TEXT PRIMARY KEY, source_url TEXT, local_path TEXT);
                CREATE TABLE tipo_cambio_deuda (
                    period TEXT PRIMARY KEY, frequency TEXT, rate REAL,
                    reported_rate_available INTEGER, currency_from TEXT, currency_to TEXT);
            """)
            for table, rows, count in (
                ("fiscal_aif_metrics_long", fiscal, 9), ("deuda_publica_long", debt, 19),
                ("fuentes", [(p, *s) for p, s in sources.items()], 3),
                ("tipo_cambio_deuda", [(p, "quarterly", v, 1, "USD", "ARS") for p, v in fx.items()], 6),
            ):
                placeholders = ",".join("?" for _ in range(count))
                db.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            if quarterly_flows:
                db.execute("""CREATE TABLE quarterly_debt_flows (
                    period TEXT, metric TEXT, value REAL, PRIMARY KEY(period, metric))""")
                db.executemany("INSERT INTO quarterly_debt_flows VALUES (?, ?, ?)", (
                    (period, metric, value)
                    for period, metrics in direct_flows.items() for metric, value in metrics.items()
                ))
        db.close()
        if floating:
            csv_path = Path(temp) / "deuda_flotante.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("period", "item", "value_millions_pesos", "source_url", "local_path"))
                writer.writerows(floating)
            csv_path.replace(args.output / csv_path.name)
        db_path.replace(args.output / db_path.name)
    print(f"{province}: {len(fiscal)} filas fiscales, {len(debt)} de deuda, {len(floating)} de flotante")
