"""Exporta las jerarquías provinciales para las pestañas de detalle offline."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from actualizar_datos import (
    CONFIG_PATH, ROOT, as_float, atomic_write, load_ipc, load_macro, load_reported_debt_fx,
    load_santa_fe_debt, load_monthly_macro, norm_text, period_month_key, readonly_connection, trailing_periods,
)
from puente_provincial import BASE, quarter
from generar_rio_negro_puente import FLOW_FIELDS, NATIVE as RIO_NEGRO_DB, STOCK as RIO_NEGRO_STOCK


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


def put(output, series, period, path, value, construction="trimestral"):
    value = as_float(value)
    if period and path and value is not None:
        key = series if construction == "trimestral" else construction + "|" + series
        existing = output[key][period].get(path)
        if existing is not None and abs(existing - value) > max(0.01, abs(value) * 1e-8):
            raise ValueError(f"Detalle duplicado con valores distintos: {key} {period} {path}")
        output[key][period].setdefault(path, value)


def closing_month(period):
    return period_month_key(period)[:7] if re.fullmatch(r"\d{4}Q[1-4]", period) else period[:7]


def old_fiscal(db, output):
    sql = """
        SELECT entity, basis, construction, period, item, nivel, value
        FROM fiscal_aif_metrics_long
        WHERE construction IN ('trimestral','mensual','reportado') AND entity IN ('APNOF','SS')
        ORDER BY entity, basis, construction, period, CAST([order] AS INTEGER), rowid
    """
    grouped = defaultdict(list)
    for row in db.execute(sql):
        basis = "dev" if row["basis"] == "Dev" else "caja"
        construction = {"reportado": "acumulado", "mensual": "mensual", "trimestral": "trimestral"}[row["construction"]]
        period = closing_month(row["period"]) if construction == "acumulado" else row["period"]
        grouped[f"{row['entity']}_{basis}", construction, period].append(row)
    for (series, construction, period), rows in grouped.items():
        for path, row in paths_by_level(rows, "item", "nivel"):
            put(output, series, period, path, row["value"], construction)


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
    table_options = {table: (series, "trimestral") for table, series in table_map.items()}
    for table, series in table_map.items():
        if table.endswith(" Trim"):
            base = table.removesuffix(" Trim")
            table_options[base + " Periodo"] = series, "mensual"
            table_options[base] = series, "acumulado"
        elif series == "stock":
            table_options[table] = series, "stock"
    params = ",".join("?" for _ in table_options)
    for row in db.execute(
        f"SELECT * FROM series WHERE table_name IN ({params}) AND value IS NOT NULL "
        "ORDER BY table_name, period, excel_row", tuple(table_options)
    ):
        series, construction = table_options[row["table_name"]]
        if str(row["concept_id"]).startswith("ER_FLOT"):
            continue
        label = clean(row["concept"])
        if cordoba:
            path = tuple(clean(part) for part in row["full_path"].split(" > "))
            if series not in {"APNOF_dev", "SS_dev"}:
                if any(norm_text(part) == "DEUDA FLOTANTE" for part in path):
                    continue
                path = path[1:] if row["level"] else (label,)
            path = path or (label,)
        else:
            path = (*filter(None, map(clean, (row["parent_path"] or "").split(" > "))), label)
        if construction == "mensual":
            is_month = row["interval_months"] == 1 if cordoba else row["interval_start"] == row["period"][:7] + "-01"
            if is_month:
                put(output, series, row["period"][:7], path, row["value"], "mensual")
        elif construction == "acumulado":
            put(output, series, closing_month(row["period"]), path, row["value"], construction)
        elif construction == "stock":
            put(output, series, quarter(row["period"]), path, row["value"])
            put(output, series, row["period"][:7], path, row["value"], "mensual")
        else:
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
                    put(output, f"APNOF_{basis}", month, path, value, "mensual")
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
    for month, rows in output["mensual|APNOF_dev"].items():
        for path, value in rows.items():
            series = {
                "AMORTIZACION DE LA DEUDA CONSOLIDADA": "amort_dev",
                "INTERESES Y GASTOS DE LA DEUDA": "interest_dev",
                "USO DEL CREDITO": "use",
            }.get(norm_text(path[-1]))
            if series:
                put(output, series, month, path, value, "mensual")


def emit_debt_flows(output, accumulated, monthly=False):
    for (series, period, path), current in accumulated.items():
        month = closing_month(period)
        put(output, series, month, path, current, "acumulado")
        if monthly:
            year, number = map(int, month.split("-"))
            previous_period = f"{year}-{number-1:02d}"
            first = number == 1
        else:
            previous_period = trailing_periods(period, 2)[0]
            first = period.endswith("Q1")
        previous = accumulated.get((series, previous_period, path))
        value = current if first else current - previous if previous is not None else None
        put(output, series, period, path, value, "mensual" if monthly else "trimestral")


def santa_fe_paths(rows):
    intermediate = {}
    currencies = defaultdict(set)
    for row in rows:
        key = tuple(clean(row[k]) for k in ("acreedor", "subgrupo", "instrumento"))
        currencies[key].add(clean(row.get("moneda_instrumento")))
    for row in rows:
        category, group, instrument = (clean(row[key]) for key in ("acreedor", "subgrupo", "instrumento"))
        level = int(row["nivel"] or 0)
        if level == 0:
            path = (instrument or category,)
        elif level == 1:
            path = (category,)
        elif level == 2:
            base = tuple(filter(None, (category, group)))
            path = base if instrument == group else (*base, instrument)
            if len(currencies[category, group, instrument]) > 1:
                path = (*path[:-1], path[-1] + " · " + clean(row.get("moneda_instrumento")))
            intermediate[category, group] = path
        else:
            base = intermediate.get((category, group), tuple(filter(None, (category, group))))
            currency = clean(row.get("moneda_instrumento"))
            label = instrument + (f" · {currency}" if currency else "")
            path = (*base, label)
        yield path, row


def santa_fe_debt(db, output):
    groups, _ = load_santa_fe_debt(db)
    accumulated = {}
    fields = {"use": "uso_credito_cum", "amort_dev": "amort_dev_cum",
              "interest_dev": "intereses_dev_cum", "amort_caja": "amort_pag_cum",
              "interest_caja": "intereses_pag_cum"}
    for period, rows in groups.items():
        ordered = sorted(rows, key=lambda row: as_float(row["orden"]) or 0)
        for path, row in santa_fe_paths(ordered):
            put(output, "stock", period, path, row["stock_pesos"])
            for series, field in fields.items():
                value = as_float(row[field])
                if value is not None:
                    accumulated[series, period, path] = value
    emit_debt_flows(output, accumulated)
    monthly = {}
    query = """
        SELECT * FROM deuda_publica_long
        WHERE frequency='monthly'
        ORDER BY period, CAST(orden AS INTEGER), rowid
    """
    groups = defaultdict(list)
    for row in db.execute(query):
        groups[row["period"]].append(dict(row))
    for period, rows in groups.items():
        for path, row in santa_fe_paths(rows):
            put(output, "stock", period, path, row["stock_pesos"], "mensual")
            for series, field in fields.items():
                value = as_float(row[field])
                if value is not None:
                    monthly[series, period, path] = value
    emit_debt_flows(output, monthly, monthly=True)


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


def rio_negro_detail(db, output):
    constructions = {"Trim": "trimestral", "Periodo": "mensual", "Acumulado": "acumulado"}
    for row in db.execute("""
        SELECT * FROM series_fiscales WHERE serie IN ('Trim','Periodo','Acumulado')
        ORDER BY periodo, nivel, rowid
    """):
        basis = "dev" if row["base"] == "Devengado" else "caja"
        label = clean(row["concepto"])
        occurrence = row["concepto_id"].rsplit("|", 1)[-1]
        if occurrence.isdecimal() and int(occurrence) > 1:
            label += f" ({occurrence})"
        path = tuple(filter(None, map(clean, (row["grupo"] or "").split(" > ")))) + (label,)
        put(output, "APNOF_" + basis, row["periodo"], path, row["valor_millones_ars"], constructions[row["serie"]])

    def stock_token(value):
        return re.sub(r"[^A-Z0-9]", "", norm_text(value))

    groups = defaultdict(list)
    for row in db.execute(RIO_NEGRO_STOCK + " ORDER BY s.periodo, s.grupo, s.nivel, s.rowid"):
        groups[row["periodo"], row["grupo"]].append(row)
    for (month, origin), rows in groups.items():
        subtotal = {tuple(r["concepto_id"].split("|")[2:]): clean(r["concepto"])
                    for r in rows if r["nivel"] == 2}
        seen = defaultdict(int)
        for row in rows:
            key = row["concepto_id"].split("|")
            label = clean(row["concepto"])
            if row["nivel"] == 1:
                path = (origin,)
            elif row["nivel"] == 2:
                category, subgroup = key[2:]
                category_label = subtotal.get((category, category), category)
                path = (origin, category_label) if category == subgroup else (origin, category_label, label)
            else:
                category, subgroup = key[1:3]
                if category == "LETRASDECORTOPLAZOFUERADELTOTAL":
                    # Sibling of the reported Anexo II total, not part of it.
                    path = ("Anexo II: letras fuera del total", label)
                else:
                    match = next((token for token in (category, "1" + category)
                                  if (token, token) in subtotal), category)
                    category_label = subtotal.get((match, match), clean(row["emisor"]) or category)
                    subgroup_label = subtotal.get((match, subgroup), clean(row["subgrupo"]))
                    subgroup_path = (subgroup_label,) if subgroup_label and stock_token(subgroup_label) != stock_token(category_label) else ()
                    path = (origin, category_label, *subgroup_path, label)
            if row["nivel"] == 2 and key[2] == "LETRASDECORTOPLAZO":
                if key[3] != key[2]:
                    continue
                path = ("Anexo II: letras fuera del total",)
            if row["nivel"] == 3:
                seen[path] += 1
                if seen[path] > 1:
                    path = (*path[:-1], f"{path[-1]} ({seen[path]})")
            value = row["valor_millones_ars"]
            put(output, "stock", month, path, value, "mensual")
            put(output, "stock", quarter(month), path, value)

    hierarchy = {}
    siblings = defaultdict(int)
    for row in db.execute("SELECT * FROM jerarquia_flujos_deuda WHERE origen='Anexo II' ORDER BY concepto_id"):
        parent, label = row["concepto_superior_id"], clean(row["concepto"])
        siblings[parent, label] += 1
        index = siblings[parent, label]
        hierarchy[row["concepto_id"]] = parent, label if index == 1 else f"{label} ({index})"

    def flow_path(key):
        parent, label = hierarchy[key]
        return (*flow_path(parent), label) if parent else (label,)

    paths = {key: flow_path(key) for key in hierarchy}
    for row in db.execute("""
        SELECT s.* FROM series_deuda s JOIN jerarquia_flujos_deuda h USING(concepto_id)
        WHERE h.origen='Anexo II' AND s.serie IN ('Trim','Periodo','Acumulado')
        ORDER BY s.periodo, h.nivel, s.rowid
    """):
        measure = FLOW_FIELDS.get(row["base"])
        if measure:
            put(output, measure, row["periodo"], paths[row["concepto_id"]],
                row["valor_millones_ars"], constructions[row["serie"]])


def add_accumulated(output):
    monthly_keys = [key for key in output if key.startswith("mensual|") and key != "mensual|stock"]
    for key in monthly_keys:
        series = key.split("|", 1)[1]
        points = output[key]
        for month, rows in list(points.items()):
            year, number = month.split("-")
            months = [f"{year}-{m:02d}" for m in range(1, int(number)+1)]
            for path in rows:
                values = [points.get(p, {}).get(path) for p in months]
                if all(v is not None for v in values):
                    target = output["acumulado|" + series][month]
                    target.setdefault(path, sum(values))
    for series in list(output):
        if "|" in series or series == "stock":
            continue
        points = output[series]
        for period, rows in list(points.items()):
            quarters = [f"{period[:4]}Q{q}" for q in range(1, int(period[-1])+1)]
            for path in rows:
                values = [points.get(p, {}).get(path) for p in quarters]
                if all(v is not None for v in values):
                    output["acumulado|" + series][closing_month(period)].setdefault(path, sum(values))


def export_series(output):
    paths = []
    ids = {}
    constructions = defaultdict(dict)
    for key, series in output.items():
        construction, measure = key.split("|", 1) if "|" in key else ("trimestral", key)
        periods = {}
        for period, rows in sorted(series.items()):
            if not rows:
                continue
            encoded = []
            for path, value in rows.items():
                if path not in ids:
                    ids[path] = len(paths)
                    paths.append(path)
                encoded.append([ids[path], value])
            periods[period] = encoded
        if periods:
            constructions[construction][measure] = periods
    return paths, dict(constructions)


def build_details(config, macro, ipc):
    monthly_macro = load_monthly_macro(ROOT/config["monthly_macro_file"])
    with (ROOT/config["monthly_macro_file"]).open(encoding="utf-8-sig", newline="") as file:
        weights = {r["mes"][:7]: max(1, int(r.get("observaciones_diarias") or 1)) for r in csv.DictReader(file)}
    for province, spec in config["provinces"].items():
        output = defaultdict(lambda: defaultdict(dict))
        fx = {}
        if province == "rio_negro":
            with readonly_connection(RIO_NEGRO_DB) as db:
                rio_negro_detail(db, output)
        elif province in {"mendoza", "cordoba", "entre_rios"}:
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
                    for row in db.execute("SELECT period, rate FROM tipo_cambio_deuda WHERE currency_from='USD' AND currency_to='ARS' AND reported_rate_available=1 AND rate>0"):
                        fx[row["period"]] = row["rate"]
            else:
                neuquen_debt(spec, output)
        add_accumulated(output)
        paths, constructions = export_series(output)
        periods = sorted({p for series in output.values() for p in series})
        rates = {}
        accumulated_rates = {}
        for period in periods:
            month = closing_month(period)
            is_monthly = bool(re.fullmatch(r"\d{4}-\d{2}", period))
            currency = monthly_macro.get(month, {}) if is_monthly else macro.get(period, {})
            rates[period] = [
                currency.get("average"), fx.get(period) or currency.get("end"),
                ipc["monthly"].get(month) if is_monthly else ipc["quarterly"].get(period),
                ipc["monthly"].get(month),
            ]
            months = [f"{month[:4]}-{m:02d}" for m in range(1, int(month[-2:])+1)]
            fx_values = [monthly_macro.get(m, {}).get("average") for m in months]
            ipc_values = [ipc["monthly"].get(m) for m in months]
            fx_average = None
            if all(v is not None for v in fx_values):
                fx_average = sum(v * weights.get(m, 1) for m, v in zip(months, fx_values)) / sum(weights.get(m, 1) for m in months)
            ipc_average = sum(ipc_values)/len(months) if all(v is not None for v in ipc_values) else None
            accumulated_rates[month] = [fx_average, ipc_average]
        data = {
            "format": 2,
            "paths": paths,
            "reference": ipc["reference"],
            "referenceDate": ipc["reference_date"],
            "rates": rates,
            "accumulatedRates": accumulated_rates,
            "series": constructions.get("trimestral", {}),
            "constructions": constructions,
        }
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        atomic_write(ROOT/"data"/"detalle"/f"{province}.js",
                     f"window.PROVINCIAS_DETALLE ??= {{}};\nwindow.PROVINCIAS_DETALLE[{json.dumps(province)}] = {payload};\n")
        print(province, {construction: {key: len(series) for key, series in grouped.items()}
                         for construction, grouped in constructions.items()})


if __name__ == "__main__":
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    build_details(config, load_macro(ROOT/config["macro_file"]), load_ipc(ROOT/config["ipc_file"]))
