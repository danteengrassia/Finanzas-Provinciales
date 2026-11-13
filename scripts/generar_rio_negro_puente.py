"""Integra la entrega jerarquica de Rio Negro sin alterar el SQLite provincial."""

import json
from collections import defaultdict

from puente_provincial import BASE, DIRECTOS, debt_row, local_path, quarter, write_bridge


NATIVE = BASE / "Rio Negro/extraccion_fiscal_deuda_20261113_jerarquia/rio_negro_data.sqlite"
FLOW_FIELDS = {"uso_credito": "use", "amort_dev": "amort_dev", "int_dev": "interest_dev",
               "amort_pagado": "amort_caja", "int_pagado": "interest_caja"}
STOCK = """
    SELECT s.*, i.emisor, i.subgrupo, i.moneda
    FROM series_deuda s LEFT JOIN instrumentos_deuda i USING(concepto_id)
    WHERE s.serie='Stock' AND s.valor_millones_ars IS NOT NULL
"""


def build_bridge(source, _):
    documents = {r["document_id"]: (r["url"], local_path(r["local_path"]))
                 for r in source.execute("SELECT document_id,url,local_path FROM fuentes")}

    def provenance(row):
        refs = json.loads(row["fuentes"] or "[]")
        return next((documents[str(ref[0])] for ref in refs if str(ref[0]) in documents), (None, None))

    fiscal, debt, floating, sources = [], [], [], {}
    for row in source.execute("""
        SELECT * FROM series_fiscales
        WHERE base='Devengado' AND serie IN ('Trim','Periodo') AND valor_millones_ars IS NOT NULL
    """):
        period = row["periodo"]
        construction = "trimestral" if row["serie"] == "Trim" else "mensual"
        fiscal.append(("APNOF", construction, "Dev", period, row["period_end"], row["concepto_id"],
                       row["valor_millones_ars"], *provenance(row)))

    by_period = defaultdict(list)
    for row in source.execute(STOCK + " AND s.grupo='Anexo II'"):
        if period := quarter(row["periodo"]):
            by_period[period].append(row)
    for period, rows in by_period.items():
        total = next((row for row in rows if row["nivel"] == 1), None)
        if not total:
            continue
        sources[period] = provenance(total)
        debt.append(debt_row(period, "total", total["concepto"], 0, kind="Total",
                             stock=total["valor_millones_ars"]))
        category_ids = {r["concepto_id"] for r in rows if r["nivel"] == 2}
        by_floating_group = defaultdict(list)
        for row in rows:
            key, label, level, value = (row[k] for k in ("concepto_id", "concepto", "nivel", "valor_millones_ars"))
            parts = key.split("|")
            if level == 2 and parts[2] == parts[3] and parts[2] != "LETRASDECORTOPLAZO":
                # Early layouts can repeat the bond subtotal and list national
                # multilateral financing as a memorandum under national debt.
                if parts[2] == "TITULOSPUBLICOS" and "Anexo II|SUBTOTAL|TITULOSPUBLICOSPROVINCIALES|TITULOSPUBLICOSPROVINCIALES" in category_ids:
                    continue
                if parts[2] == "FINANCIAMIENTODEORGANISMOSINTERNACIONALESDECREDITO" and "Anexo II|SUBTOTAL|GOBIERNONACIONAL|GOBIERNONACIONAL" in category_ids:
                    continue
                category = DIRECTOS if "MULTILATERALDIRECTO" in parts[2] else label
                debt.append(debt_row(period, key + "|||", category, 1, kind="Categoria", stock=value))
            elif level == 2:
                by_floating_group[parts[2]].append(row)
            elif level == 3 and parts[1] != "LETRASDECORTOPLAZOFUERADELTOTAL":
                category = DIRECTOS if parts[1] == "MULTILATERALDIRECTO" else row["emisor"] or parts[1]
                debt.append(debt_row(period, key, label, 3, category=category,
                                     group=row["subgrupo"], currency=row["moneda"], kind="Detalle", stock=value))
        for items in by_floating_group.values():
            if not any(r["concepto_id"].endswith("|DEUDAFLOTANTE") for r in items):
                continue
            for row in items:
                key = row["concepto_id"].split("|")[-1]
                if key in {"DEUDAFLOTANTE", "PERSONAL", "PROVEEDORESYCONTRATISTAS", "TRANSFERENCIAS", "OTROS"}:
                    name = "Total Deuda Flotante" if key == "DEUDAFLOTANTE" else row["concepto"]
                    floating.append((period, name, row["valor_millones_ars"], *provenance(row)))
    return fiscal, debt, sources, {}, floating


def debt_flows(source):
    """Use comparable quarterly observations directly, never difference an unknown window."""
    totals = defaultdict(dict)
    components = defaultdict(list)
    for row in source.execute("""
        SELECT s.base, s.periodo, s.valor_millones_ars, h.concepto_id, h.nivel
        FROM series_deuda s JOIN jerarquia_flujos_deuda h USING(concepto_id)
        WHERE h.origen='Anexo II' AND h.alcance='deuda_publica' AND s.serie='Trim'
          AND s.valor_millones_ars IS NOT NULL
          AND s.base IN ('uso_credito','amort_dev','int_dev')
    """):
        base, period, value, key, level = row
        metric = {"uso_credito": "use", "amort_dev": "amort", "int_dev": "interest"}[base]
        if level == 0:
            totals[period]["total_" + metric] = value
        elif (level == 1 and key.endswith(("|MULTILATERALDIRECTO", "|FINANCIAMIENTODEORGANISMOSINTERNACIONALESDECREDITO"))
              or level == 2 and "|GOBIERNONACIONAL|SUBGRUPO|" in key and key.endswith(("|BID", "|BIRF", "|FIDA", "|FONPLATA", "|CAF"))):
            components[period, "ooii_" + metric].append(value)
        elif level == 3 and base == "uso_credito" and key.endswith("|BONOPLANCASTELLO"):
            components[period, "intl_bond_use"].append(value)
    for (period, metric), values in components.items():
        totals[period][metric] = sum(values)
    return dict(totals)


if __name__ == "__main__":
    write_bridge("rio_negro", build_bridge, default_source=NATIVE, source_version="20261113",
                 quarterly_flows=debt_flows)
