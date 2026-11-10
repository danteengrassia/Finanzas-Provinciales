"""Adapta el AIF mensual y el tablero de deuda de Mendoza."""

from collections import defaultdict

from puente_provincial import (
    DIRECTOS, aggregate, as_float, debt_row, fiscal_row, local_path, quarter, write_bridge,
)

CATEGORIES = {
    "Gobierno Federal": "GOBIERNO NACIONAL",
    "Banco de la Nación Argentina": "ENTIDADES FINANCIERAS",
    "Bancos Nacionales e Internacionales": "ENTIDADES FINANCIERAS",
    "Multilateral": DIRECTOS,
    "Tenedores de Bonos": "TITULOS PUBLICOS",
}


def build(source, _path):
    monthly = defaultdict(dict)
    provenance = {}
    for row in source.execute("SELECT orden, period, value, source_url, source_file FROM fiscal_aif_long WHERE basis='Devengado' AND value IS NOT NULL"):
        period = quarter(row["period"], monthly_flow=True)
        key = f"mza_o{int(row['orden']):02}"
        value = as_float(row["value"])
        if period is None or value is None:
            continue
        months = monthly[period, key]
        if row["period"] in months and months[row["period"]] != value:
            raise ValueError(f"AIF duplicado: {period} {key} {row['period']}")
        months[row["period"]] = value
        provenance[period, key] = row["source_url"], local_path(row["source_file"])
    fiscal = []
    quarterly = defaultdict(dict)
    for (period, key), months in monthly.items():
        if len(months) == 3:
            quarterly[period][key] = sum(months.values())
    for period, values in quarterly.items():
        for key, first, second, sign in (
            ("mza_deriv_gastos_primarios", "56", "25", -1),
            ("mza_deriv_resultado_primario", "57", "25", 1),
            ("mza_deriv_inversion_real_directa", "44", "45", 1),
        ):
            a, b = "mza_o" + first, "mza_o" + second
            if a in values and b in values:
                values[key] = values[a] + sign * values[b]
                provenance[period, key] = provenance[period, a]
        fiscal.extend(fiscal_row("APNOF", period, key, v, provenance[period, key]) for key, v in values.items())

    ytd = {}
    for table, field in (
        ("deuda_amort_ars_a3500_long", "amort_pag_cum"),
        ("deuda_interes_ars_a3500_long", "intereses_pag_cum"),
    ):
        months = defaultdict(dict)
        for row in source.execute(f"SELECT period, acreedor, value FROM {table} WHERE tipo_fila='subtotal_acreedor'"):
            months[row["acreedor"], row["period"][:4]][row["period"]] = as_float(row["value"])
        ytd[field] = months

    sources = {quarter(r["periodo"]): (r["url"] or None, local_path(r["archivo"]))
               for r in source.execute("SELECT * FROM fuentes WHERE dataset='deuda_publica'") if quarter(r["periodo"])}
    categories = defaultdict(dict)
    debt = []
    for row in source.execute("SELECT * FROM deuda_stock_ars_a3500_long"):
        period = quarter(row["period"])
        value = as_float(row["value"])
        if value is None or period is None:
            continue
        creditor = row["acreedor"]
        category = CATEGORIES[creditor]
        if row["tipo_fila"] == "subtotal_acreedor":
            if creditor in categories[period]:
                raise ValueError(f"Subtotal repetido: {period} {creditor}")
            categories[period][creditor] = value
        elif row["tipo_fila"] == "detalle":
            currency = row["moneda_original"]
            if currency in {"UVA", "Pesos Ajustados"}:
                currency = "ARS"
            debt.append(debt_row(period, f"instrumento:{row['id']}:{len(debt)}", row["descripcion"], 2,
                                 category=category, kind="Detalle", currency=currency, stock=value))
    for period, stock in sorted(categories.items()):
        year, q = period[:4], int(period[-1])
        fields = defaultdict(list)
        for creditor, amount in stock.items():
            flows = {}
            for field, months in ytd.items():
                by_month = months[creditor, year]
                flows[field] = aggregate([by_month.get(f"{year}-{m:02}") for m in range(1, 3*q+1)])
                fields[field].append(flows[field])
            debt.append(debt_row(period, creditor + "|||", CATEGORIES[creditor], 1,
                                 kind="Categoria", stock=amount, flows=flows))
        total = {field: aggregate(values) for field, values in fields.items()}
        total["uso_credito_cum"] = aggregate([quarterly[f"{year}Q{i}"].get("mza_o58") for i in range(1, q+1)])
        debt.append(debt_row(period, "total", "TOTAL GENERAL", 0,
                             kind="Total", stock=sum(stock.values()), flows=total))
    fx = {quarter(r["period"]): v for r in source.execute(
        "SELECT period,value FROM deuda_variables_trimestral WHERE unit='ARS por USD'"
    ) if (v := as_float(r["value"])) and v > 0 and quarter(r["period"])}
    return fiscal, debt, sources, fx, []


if __name__ == "__main__":
    write_bridge("mendoza", build)
