"""Exporta las jerarquías provinciales para las pestañas de detalle offline."""

import csv
import json
from collections import defaultdict
from pathlib import Path

from actualizar_datos import (
    CONFIG_PATH, ROOT, as_float, atomic_write, load_ipc, load_macro, load_reported_debt_fx,
    load_santa_fe_debt, norm_text, period_month_key, readonly_connection, trailing_periods,
)
from puente_provincial import BASE, quarter


def clean(label):
    return str(label or "").strip().lstrip(".- ").strip()


def paths_by_level(rows, label_key, level_key, root_level=1):
    trail = []
    for row in rows:
        label = clean(row[label_key])
        if not label or row[level_key] is None:
            continue
        level = max(0, int(row[level_key]) - root_level)
        trail = trail[:level]
        trail.append(label)
        yield tuple(trail), row


def put(output, series, period, path, value):
    value = as_float(value)
    if period and path and value is not None:
        output[series][period].setdefault(path, value)


def old_fiscal(db, output):
    sql = """
        SELECT entity, basis, period, item, nivel, value
        FROM fiscal_aif_metrics_long
        WHERE construction='trimestral' AND entity IN ('APNOF','SS')
        ORDER BY entity, basis, period, CAST([order] AS INTEGER), rowid
    """
    grouped = defaultdict(list)
    for row in db.execute(sql):
        basis = "dev" if row["basis"] == "Dev" else "caja"
        grouped[f"{row['entity']}_{basis}", row["period"]].append(row)
    for (series, period), rows in grouped.items():
        for path, row in paths_by_level(rows, "item", "nivel"):
            put(output, series, period, path, row["value"])


def native_hierarchy(db, output, province):
    cordoba = province == "cordoba"
    table_map = {
        "APNOF Dev Trim": "APNOF_dev",
        "SS Dev Trim" if cordoba else "Seguridad Social Dev Trim": "SS_dev",
        "Stock detalle" if cordoba else "Deuda Stock detalle": "stock",
        "Uso credito Trim" if cordoba else "Uso del credito Trim": "use",
        "Amort dev Trim" if cordoba else "Amort Dev Trim": "amort_dev",
        "Intereses dev Trim" if cordoba else "Int y acc Dev Trim": "interest_dev",
    }
    if not cordoba:
        table_map.update({
            "APNOF Caja Trim": "APNOF_caja", "Seguridad Social Caja Trim": "SS_caja",
            "Amort Caja Trim": "amort_caja", "Int y acc Caja Trim": "interest_caja",
        })
    params = ",".join("?" for _ in table_map)
    for row in db.execute(
        f"SELECT * FROM series WHERE table_name IN ({params}) AND value IS NOT NULL "
        "ORDER BY table_name, period, excel_row", tuple(table_map)
    ):
        series = table_map[row["table_name"]]
        if str(row["concept_id"]).startswith("ER_FLOT"):
            continue
        label = clean(row["concept"])
        if cordoba:
            path = tuple(clean(part) for part in row["full_path"].split(" > "))
            if series not in {"APNOF_dev", "SS_dev"}:
                path = path[1:] if row["level"] else (label,)
            path = path or (label,)
        else:
            path = (*filter(None, map(clean, (row["parent_path"] or "").split(" > "))), label)
        put(output, series, quarter(row["period"]), path, row["value"])


def mendoza_detail(db, output):
    for table, basis in (("fiscal_aif_long", "dev"), ("fiscal_aif_caja_long", "caja")):
        groups = defaultdict(list)
        for row in db.execute(f"SELECT * FROM {table} ORDER BY period, CAST(orden AS INTEGER)"):
            groups[row["period"]].append(row)
        fiscal = defaultdict(dict)
        for month, rows in groups.items():
            period = quarter(month, monthly_flow=True)
            for path, row in paths_by_level(rows, "concepto", "nivel", 0):
                value = as_float(row["value"])
                if period and value is not None:
                    fiscal[period, path][month] = value
        for (period, path), values in fiscal.items():
            if len(values) != 3:
                continue
            value = sum(values.values())
            put(output, f"APNOF_{basis}", period, path, value)
    debt_categories = defaultdict(list)
    for row in db.execute("SELECT * FROM deuda_stock_ars_a3500_long"):
        period = quarter(row["period"])
        creditor = row["acreedor"]
        value = as_float(row["value"])
        if row["tipo_fila"] == "subtotal_acreedor" and value is not None:
            debt_categories[period].append(value)
            path = (creditor,)
        elif row["tipo_fila"] == "detalle":
            subgroup = clean(row["subacreedor"])
            label = clean(row["descripcion"])
            path = (creditor, subgroup, label) if subgroup and subgroup != label else (creditor, label)
        else:
            continue
        put(output, "stock", period, path, value)
    for period, values in debt_categories.items():
        put(output, "stock", period, ("Total deuda pública",), sum(values))
    for period, rows in output["APNOF_dev"].items():
        for path, value in rows.items():
            label = norm_text(path[-1])
            if label == "AMORTIZACION DE LA DEUDA CONSOLIDADA":
                put(output, "amort_dev", period, path, value)
            if label == "INTERESES Y GASTOS DE LA DEUDA":
                put(output, "interest_dev", period, path, value)
            if label == "USO DEL CREDITO":
                put(output, "use", period, path, value)


def emit_debt_flows(output, accumulated):
    for (series, period, path), current in accumulated.items():
        previous = accumulated.get((series, trailing_periods(period, 2)[0], path))
        value = current if period.endswith("Q1") else current - previous if previous is not None else None
        put(output, series, period, path, value)


def santa_fe_debt(db, output):
    groups, _ = load_santa_fe_debt(db)
    accumulated = {}
    fields = {"use": "uso_credito_cum", "amort_dev": "amort_dev_cum",
              "interest_dev": "intereses_dev_cum", "amort_caja": "amort_pag_cum",
              "interest_caja": "intereses_pag_cum"}
    for period, rows in groups.items():
        ordered = sorted(rows, key=lambda row: as_float(row["orden"]) or 0)
        for path, row in paths_by_level(ordered, "instrument_raw", "level"):
            put(output, "stock", period, path, row["stock_pesos"])
            for series, field in fields.items():
                value = as_float(row[field])
                if value is not None:
                    accumulated[series, period, path] = value
    emit_debt_flows(output, accumulated)


def neuquen_debt(spec, output):
    accumulated = {}
    fields = {"uso_credito": "use", "amortizacion_devengado": "amort_dev",
              "intereses_devengados": "interest_dev", "amortizacion_base_caja": "amort_caja",
              "intereses_base_caja": "interest_caja", "stock_pesos": "stock"}
    with (ROOT/spec["debt_metrics_file"]).open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            series = fields.get(row["metric"])
            period = quarter(row["period"])
            value = as_float(row["value"])
            if not series or not period or value is None or row["construction"] != "reportado":
                continue
            emitter, group, instrument = (clean(row[key]) for key in ("emisor", "subgrupo", "emision_en_particular"))
            kind = norm_text(row["tipo_fila"])
            if kind == "TOTAL":
                path = ("Total deuda pública",)
            elif kind == "SUBTOTAL":
                path = (emitter,)
            elif kind == "SUBTOTAL SUBGRUPO":
                path = (emitter, group)
            else:
                path = tuple(filter(None, (emitter, group, instrument)))
            if series == "stock":
                put(output, series, period, path, value)
            else:
                accumulated[series, period, path] = value
    emit_debt_flows(output, accumulated)


def build_details(config, macro, ipc):
    for province, spec in config["provinces"].items():
        output = defaultdict(lambda: defaultdict(dict))
        fx = {}
        if province in {"mendoza", "cordoba", "entre_rios"}:
            folder = {"mendoza": "Mendoza", "cordoba": "Cordoba", "entre_rios": "Entre Rios"}[province]
            with readonly_connection(BASE/folder/"database"/f"{province}_data.sqlite") as db:
                if province == "mendoza":
                    mendoza_detail(db, output)
                else:
                    native_hierarchy(db, output, province)
            if province == "mendoza":
                with readonly_connection(ROOT/spec["debt_db"]) as db:
                    fx = load_reported_debt_fx(db)
        else:
            with readonly_connection(ROOT/spec["fiscal_db"]) as db:
                old_fiscal(db, output)
            if province == "santa_fe":
                with readonly_connection(ROOT/spec["debt_db"]) as db:
                    santa_fe_debt(db, output)
                    fx = load_reported_debt_fx(db)
            else:
                neuquen_debt(spec, output)
        data = {
            "reference": ipc["reference"],
            "referenceDate": ipc["reference_date"],
            "rates": {
                p: [macro.get(p, {}).get("average"), fx.get(p) or macro.get(p, {}).get("end"),
                    ipc["quarterly"].get(p), ipc["monthly"].get(period_month_key(p)[:7])]
                for p in sorted({p for series in output.values() for p in series})
            },
            "series": {
                key: {period: [[*path, value] for path, value in rows.items()]
                      for period, rows in sorted(series.items()) if rows}
                for key, series in output.items() if series
            },
        }
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        atomic_write(ROOT/"data"/"detalle"/f"{province}.js",
                     f"window.PROVINCIAS_DETALLE ??= {{}};\nwindow.PROVINCIAS_DETALLE[{json.dumps(province)}] = {payload};\n")
        print(province, {key: len(series) for key, series in data["series"].items()})


if __name__ == "__main__":
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    build_details(config, load_macro(ROOT/config["macro_file"]), load_ipc(ROOT/config["ipc_file"]))
