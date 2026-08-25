#!/usr/bin/env python3
"""Regenera la capa consolidada del dashboard sin modificar las bases fuente."""

from __future__ import annotations

import csv
import calendar
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "provincias.json"
DATA_DIR = ROOT / "data"
VERSION_DIR = DATA_DIR / "versiones"
PERIOD_RE = re.compile(r"^(\d{4})Q([1-4])$")
MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


INDICATOR_DEFINITIONS = [
    {
        "id": "balance_operativo_pct",
        "label": "Balance operativo",
        "section": "Balances fiscales",
        "description": "Resultado económico / ingresos corrientes de los últimos cuatro trimestres; ambos flujos se reexpresan al IPC nacional más reciente antes de agregarse.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_primario_pct",
        "label": "Balance primario",
        "section": "Balances fiscales",
        "description": "Resultado primario / ingresos totales de los últimos cuatro trimestres; ambos flujos se reexpresan al IPC nacional más reciente antes de agregarse.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_financiero_pct",
        "label": "Balance financiero",
        "section": "Balances fiscales",
        "description": "Resultado financiero / ingresos totales de los últimos cuatro trimestres; ambos flujos se reexpresan al IPC nacional más reciente antes de agregarse.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_post_amortizaciones_pct",
        "label": "Balance post amortizaciones",
        "section": "Balances fiscales",
        "description": "(Resultado financiero LTM - amortización de deuda y disminución de otros pasivos LTM) / ingresos totales LTM.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_post_endeudamiento_pct",
        "label": "Balance post endeudamiento",
        "section": "Balances fiscales",
        "description": "(Resultado financiero LTM - amortizaciones LTM + endeudamiento e incremento de pasivos LTM) / ingresos totales LTM.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_seguridad_social_operativo_pct",
        "label": "Balance de seguridad social",
        "section": "Seguridad social",
        "description": "Resultado económico LTM / ingresos corrientes LTM. Se utiliza la base APNOF según el criterio metodológico definido.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_seguridad_social_sin_aportes_pct",
        "label": "Seguridad social sin aportes tributarios directos",
        "section": "Seguridad social",
        "description": "(Contribuciones a la seguridad social LTM - gastos corrientes LTM) / ingresos corrientes LTM. Base APNOF.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "APNOF",
    },
    {
        "id": "balance_seguridad_social_entidad_pct",
        "label": "Balance financiero de la entidad previsional",
        "section": "Seguridad social",
        "description": "Resultado financiero previo a figurativas LTM / ingresos totales LTM de la entidad de seguridad social.",
        "unit": "percent",
        "direction": "higher",
        "source_scope": "SS",
    },
    {
        "id": "contribuciones_seguridad_social_pct",
        "label": "Contribuciones de seguridad social",
        "section": "Seguridad social",
        "description": "Contribuciones a la seguridad social LTM / (ingresos totales LTM + contribuciones figurativas LTM) de la entidad.",
        "unit": "percent",
        "direction": "neutral",
        "source_scope": "SS",
    },
    {
        "id": "capex_pct_gasto_total",
        "label": "CAPEX / gasto total",
        "section": "Inversión pública",
        "description": "Inversión real directa más transferencias de capital, excluyendo inversión financiera, / gastos totales. Los flujos trimestrales se reexpresan antes de agregarse.",
        "unit": "percent",
        "direction": "neutral",
        "source_scope": "APNOF",
    },
    {
        "id": "capex_pct_gasto_primario",
        "label": "CAPEX / gasto primario",
        "section": "Inversión pública",
        "description": "Inversión real directa más transferencias de capital, excluyendo inversión financiera, / gastos primarios. Los flujos trimestrales se reexpresan antes de agregarse.",
        "unit": "percent",
        "direction": "neutral",
        "source_scope": "APNOF",
    },
    {
        "id": "capex_trimestral_usd_m",
        "label": "CAPEX trimestral",
        "section": "Inversión pública",
        "description": "CAPEX del trimestre convertido al tipo de cambio promedio A3500 del trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "ingresos_operativos_netos_copart_ars_m",
        "label": "Ingresos operativos netos de coparticipación municipal",
        "section": "Ingresos",
        "description": "Ingresos corrientes LTM menos coparticipación y transferencias automáticas a municipios LTM.",
        "unit": "ars_millions",
        "direction": "neutral",
        "source_scope": "APNOF",
    },
    {
        "id": "transferencias_pct_ingresos",
        "label": "Transferencias / ingresos totales",
        "section": "Ingresos",
        "description": "(Ingresos tributarios de origen nacional + transferencias corrientes recibidas) LTM / ingresos totales LTM.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "APNOF",
    },
    {
        "id": "capex_ltm_usd_m",
        "label": "CAPEX últimos 12 meses",
        "section": "Inversión pública",
        "description": "Suma del CAPEX trimestral en USD de los últimos cuatro trimestres.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "servicio_deuda_pct_ingresos_operativos",
        "label": "Servicio de deuda / ingresos operativos netos",
        "section": "Deuda y servicio",
        "description": "Amortizaciones más intereses pagados en los últimos cuatro trimestres / ingresos corrientes netos de coparticipación automática a municipios.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + APNOF",
    },
    {
        "id": "deuda_usd_m",
        "label": "Deuda denominada en USD",
        "section": "Deuda y servicio",
        "description": "Stock en pesos de instrumentos denominados en dólares / tipo de cambio de valuación informado por la provincia; cuando no está disponible se utiliza A3500 de cierre.",
        "unit": "usd_millions",
        "direction": "lower",
        "source_scope": "Deuda + TC provincial/A3500",
    },
    {
        "id": "deuda_moneda_extranjera_pct",
        "label": "Deuda total en moneda extranjera",
        "section": "Deuda y servicio",
        "description": "Stock identificado en moneda extranjera / deuda pública total.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda",
    },
    {
        "id": "deuda_mas_flotante_pct_ingresos",
        "label": "Deuda más deuda flotante / ingresos",
        "section": "Deuda y servicio",
        "description": "(Deuda pública + deuda flotante) / ingresos totales APNOF LTM.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + APNOF",
    },
    {
        "id": "saldo_neto_endeudamiento_ooii_usd_m",
        "label": "Saldo neto con organismos internacionales",
        "section": "Financiamiento",
        "description": "Desembolsos de organismos internacionales LTM menos amortizaciones pagadas LTM, convertidos trimestre a trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "deuda_total_ars_m",
        "label": "Deuda pública total",
        "section": "Deuda y servicio",
        "description": "Stock total de deuda pública al cierre del trimestre.",
        "unit": "ars_millions",
        "direction": "lower",
        "source_scope": "Deuda",
    },
    {
        "id": "deuda_pct_ingresos",
        "label": "Deuda / ingresos totales",
        "section": "Deuda y servicio",
        "description": "Stock total de deuda pública / ingresos totales APNOF LTM.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + APNOF",
    },
    {
        "id": "endeudamiento_total_usd_m",
        "label": "Endeudamiento total",
        "section": "Financiamiento",
        "description": "Uso del crédito LTM convertido con el tipo de cambio promedio A3500 de cada trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "emision_bonos_internacionales_usd_m",
        "label": "Emisión de bonos internacionales",
        "section": "Financiamiento",
        "description": "Uso del crédito de títulos públicos internacionales LTM, convertido trimestre a trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "borrowings_ooii_usd_m",
        "label": "Desembolsos de organismos internacionales",
        "section": "Financiamiento",
        "description": "Uso del crédito de financiamiento de organismos internacionales vía Gobierno Nacional y préstamos directos LTM.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "amortizacion_ooii_usd_m",
        "label": "Amortizaciones a organismos internacionales",
        "section": "Financiamiento",
        "description": "Amortizaciones pagadas a organismos internacionales LTM, convertidas trimestre a trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "intereses_ooii_usd_m",
        "label": "Intereses y comisiones a organismos internacionales",
        "section": "Financiamiento",
        "description": "Intereses, comisiones y gastos pagados a organismos internacionales LTM, convertidos trimestre a trimestre.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "Deuda + A3500",
    },
    {
        "id": "ingresos_operativos_netos_copart_real_ars_m",
        "label": "Ingresos operativos netos reales",
        "section": "Ingresos",
        "description": "Ingresos corrientes menos coparticipación automática a municipios, reexpresados al IPC nacional más reciente y acumulados en cuatro trimestres.",
        "unit": "ars_millions",
        "direction": "neutral",
        "source_scope": "APNOF + IPC nacional",
    },
    {
        "id": "capex_trimestral_real_ars_m",
        "label": "CAPEX trimestral real",
        "section": "Inversión pública",
        "description": "Inversión real directa más transferencias de capital del trimestre, excluyendo inversión financiera, reexpresada al IPC nacional más reciente.",
        "unit": "ars_millions",
        "direction": "higher",
        "source_scope": "APNOF + IPC nacional",
    },
    {
        "id": "capex_ltm_real_ars_m",
        "label": "CAPEX real últimos 12 meses",
        "section": "Inversión pública",
        "description": "Suma de inversión real directa y transferencias de capital de los últimos cuatro trimestres, reexpresada al IPC nacional más reciente.",
        "unit": "ars_millions",
        "direction": "higher",
        "source_scope": "APNOF + IPC nacional",
    },
    {
        "id": "amortizaciones_pct_ingresos_operativos",
        "label": "Amortizaciones / ingresos operativos netos",
        "section": "Deuda y servicio",
        "description": "Amortizaciones pagadas en los últimos cuatro trimestres / ingresos corrientes netos de coparticipación automática a municipios.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + APNOF",
    },
    {
        "id": "intereses_pct_ingresos_operativos",
        "label": "Intereses / ingresos operativos netos",
        "section": "Deuda y servicio",
        "description": "Intereses pagados en los últimos cuatro trimestres / ingresos corrientes netos de coparticipación automática a municipios.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + APNOF",
    },
    {
        "id": "depositos_bcra_ars_m",
        "label": "Depósitos del sector público provincial",
        "section": "Deuda y servicio",
        "description": "Depósitos en moneda nacional y extranjera del sector público provincial informados por BCRA, ambos valuados en pesos.",
        "unit": "ars_millions",
        "direction": "higher",
        "source_scope": "BCRA",
    },
    {
        "id": "deuda_neta_ars_m",
        "label": "Deuda neta",
        "section": "Deuda y servicio",
        "description": "Deuda pública bruta menos depósitos en moneda nacional y extranjera del sector público provincial informados por BCRA.",
        "unit": "ars_millions",
        "direction": "lower",
        "source_scope": "Deuda + BCRA",
    },
    {
        "id": "deuda_neta_pct_ingresos",
        "label": "Deuda neta / ingresos totales",
        "section": "Deuda y servicio",
        "description": "Deuda pública bruta menos depósitos BCRA, dividido por ingresos totales APNOF de los últimos cuatro trimestres.",
        "unit": "percent",
        "direction": "lower",
        "source_scope": "Deuda + BCRA + APNOF",
    },
    {
        "id": "fuentes_resultado_financiero_usd_m",
        "label": "Resultado financiero últimos 12 meses",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Resultado financiero devengado convertido a USD trimestre a trimestre y acumulado en los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "higher",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_amort_total_usd_m",
        "label": "Total amortizaciones",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Amortización de deuda y disminución de otros pasivos de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_amort_comercial_usd_m",
        "label": "Amortización de deuda comercial",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Amortización de títulos, letras y préstamos bancarios de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_amort_ooii_usd_m",
        "label": "Amortización de organismos internacionales",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Devolución de préstamos de organismos internacionales de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_amort_otras_usd_m",
        "label": "Otras amortizaciones",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Residual entre amortizaciones totales y las amortizaciones comerciales y multilaterales.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_endeudamiento_total_usd_m",
        "label": "Total endeudamiento",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Endeudamiento público e incremento de otros pasivos de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_endeudamiento_comercial_usd_m",
        "label": "Endeudamiento comercial",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Colocación de títulos, letras y obtención de préstamos financieros de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_endeudamiento_ooii_usd_m",
        "label": "Endeudamiento con organismos internacionales",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Obtención de préstamos de organismos internacionales de los últimos 12 meses.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_endeudamiento_otros_usd_m",
        "label": "Otros endeudamientos",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Residual entre endeudamiento total y endeudamiento comercial y multilateral.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
    {
        "id": "fuentes_variacion_inversion_financiera_usd_m",
        "label": "Variación de inversiones financieras",
        "section": "Fuentes y aplicaciones financieras",
        "description": "Disminución menos aumento de inversiones financieras. Un valor positivo representa uso neto de caja.",
        "unit": "usd_millions",
        "direction": "neutral",
        "source_scope": "APNOF + A3500",
    },
]


def norm_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.upper()).strip()


def as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def period_parts(period: str) -> tuple[int, int]:
    match = PERIOD_RE.match(period)
    if not match:
        raise ValueError(f"Periodo trimestral inválido: {period}")
    return int(match.group(1)), int(match.group(2))


def period_index(period: str) -> int:
    year, quarter = period_parts(period)
    return year * 4 + quarter - 1


def period_from_index(index: int) -> str:
    year, offset = divmod(index, 4)
    return f"{year}Q{offset + 1}"


def trailing_periods(period: str, count: int = 4) -> list[str]:
    end = period_index(period)
    return [period_from_index(end - offset) for offset in range(count - 1, -1, -1)]


def period_end(period: str) -> str:
    year, quarter = period_parts(period)
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    return f"{year}-{month_day}"


def month_index(period: str) -> int:
    match = MONTH_RE.match(period)
    if not match:
        raise ValueError(f"Periodo mensual inválido: {period}")
    return int(match.group(1)) * 12 + int(match.group(2)) - 1


def month_from_index(index: int) -> str:
    year, offset = divmod(index, 12)
    return f"{year}-{offset + 1:02d}"


def trailing_months(period: str, count: int = 12) -> list[str]:
    end = month_index(period)
    return [month_from_index(end - offset) for offset in range(count - 1, -1, -1)]


def month_period_end(period: str) -> str:
    match = MONTH_RE.match(period)
    if not match:
        raise ValueError(f"Periodo mensual inválido: {period}")
    year, month = int(match.group(1)), int(match.group(2))
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def readonly_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def file_fingerprint(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": digest.hexdigest(),
    }


def load_macro(path: Path) -> dict[str, dict[str, float | None]]:
    values: dict[str, dict[str, float | None]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            period = row.get("period", "")
            if PERIOD_RE.match(period):
                values[period] = {
                    "average": as_float(row.get("tcn_promedio_a3500")),
                    "end": as_float(row.get("tcn_fin_a3500")),
                }
    return values


def load_monthly_macro(path: Path) -> dict[str, dict[str, float | None]]:
    values: dict[str, dict[str, float | None]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            period = str(row.get("mes") or "")[:7]
            if MONTH_RE.match(period):
                values[period] = {
                    "average": as_float(row.get("a3500_promedio_mensual")),
                    "end": as_float(row.get("a3500_fin_de_periodo")),
                }
    return values


def load_ipc(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    monthly = {
        str(row["date"])[:7]: as_float(row.get("index"))
        for row in payload.get("records", [])
        if as_float(row.get("index")) is not None
    }
    reference = as_float(payload.get("latest_index"))
    quarterly: dict[str, float] = {}
    for year in range(2000, 2101):
        for quarter in range(1, 5):
            months = [f"{year}-{month:02d}" for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1)]
            values = [monthly.get(month) for month in months]
            if all(value is not None for value in values):
                quarterly[f"{year}Q{quarter}"] = sum(float(value) for value in values) / 3
    return {
        "monthly": monthly,
        "quarterly": quarterly,
        "reference": reference,
        "reference_date": payload.get("latest_date"),
        "source_url": payload.get("source_url"),
    }


def load_deposits(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if norm_text(payload.get("unit")) != "MILES DE PESOS":
        raise ValueError("La serie de depósitos BCRA debe estar expresada en miles de pesos antes de convertirla a millones.")
    output: dict[tuple[str, str], dict[str, float]] = {}
    for row in payload.get("records", []):
        province_id = str(row.get("province_id") or "")
        date = str(row.get("date") or "")
        if not province_id or not re.match(r"^\d{4}-\d{2}-01$", date):
            continue
        domestic = as_float(row.get("domestic_ars_thousands"))
        foreign = as_float(row.get("foreign_ars_thousands"))
        total = as_float(row.get("total_ars_thousands"))
        output[(province_id, date)] = {
            "domestic": domestic / 1000 if domestic is not None else None,
            "foreign": foreign / 1000 if foreign is not None else None,
            "total": total / 1000 if total is not None else None,
        }
    return output


def period_month_key(period: str) -> str:
    year, quarter = period_parts(period)
    return f"{year}-{quarter * 3:02d}-01"


def load_fiscal(province_id: str, spec: dict[str, object], checks: list[dict[str, object]]) -> dict[str, object]:
    path = Path(str(spec["fiscal_db"]))
    expected = {"entity", "construction", "basis", "period", "period_end", "item_key", "value"}
    values: dict[tuple[str, str, str], float] = {}
    sources: dict[tuple[str, str, str], dict[str, str | None]] = {}
    conflicts = 0

    with readonly_connection(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(fiscal_aif_metrics_long)")}
        missing = sorted(expected - columns)
        if missing:
            raise RuntimeError(f"{province_id}: faltan columnas fiscales: {', '.join(missing)}")
        query = """
            SELECT entity, period, period_end, item_key, value, source_url, local_path
            FROM fiscal_aif_metrics_long
            WHERE basis = 'Dev'
              AND construction IN ('trimestral', 'mensual')
              AND (
                    period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]'
                 OR period GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
              )
              AND value IS NOT NULL
        """
        for row in connection.execute(query):
            key = (str(row["entity"]), str(row["period"]), str(row["item_key"]))
            value = as_float(row["value"])
            if value is None:
                continue
            if key in values and not math.isclose(values[key], value, rel_tol=1e-9, abs_tol=1e-6):
                conflicts += 1
                continue
            values[key] = value
            sources[key] = {
                "source_url": row["source_url"],
                "local_path": row["local_path"],
            }

    periods = sorted({key[1] for key in values if key[0] == "APNOF" and PERIOD_RE.match(key[1])}, key=period_index)
    monthly_periods = sorted({key[1] for key in values if key[0] == "APNOF" and MONTH_RE.match(key[1])}, key=month_index)
    checks.append({
        "province_id": province_id,
        "check_id": "fiscal_duplicate_conflicts",
        "status": "pass" if conflicts == 0 else "warn",
        "detail": f"{conflicts} conflictos de duplicación con valores diferentes.",
    })
    return {"values": values, "sources": sources, "periods": periods, "monthly_periods": monthly_periods}


def normalized_debt_period(period: str, frequency: str | None) -> tuple[str, int] | None:
    if PERIOD_RE.match(period):
        return period, 1
    match = MONTH_RE.match(period)
    if not match:
        return None
    month = int(match.group(2))
    if month not in {3, 6, 9, 12}:
        return None
    return f"{match.group(1)}Q{month // 3}", 2 if frequency == "monthly" else 1


def canonical_category(raw_label: str) -> str:
    text = norm_text(raw_label)
    if "PRESTAMOS DIRECTOS" in text and "INTERNACIONALES" in text:
        return "Organismos internacionales"
    if "GOBIERNO NACIONAL" in text:
        return "Gobierno nacional"
    if "ENTIDADES BANCARIAS" in text or "ENTIDADES FINANCIERAS" in text:
        return "Entidades financieras y otras"
    if "TITULOS PUBLICOS" in text:
        return "Títulos públicos"
    if "LETRAS" in text:
        return "Letras"
    if "DEUDA CONSOLIDADA" in text or "PAGARES PESIFICADOS" in text:
        return "Deuda consolidada"
    if "FINANCIAMIENTO DE CORTO PLAZO" in text:
        return "Financiamiento de corto plazo"
    if "GARANTIA" in text or "AVALES" in text:
        return "Garantías y avales"
    return "Otros"


def canonical_currency(raw_label: str | None) -> str:
    text = norm_text(raw_label)
    if not text:
        return "Sin identificar"
    if "DOLAR" in text or text == "USD":
        return "USD"
    if "EURO" in text:
        return "EUR"
    if "DINAR" in text:
        return "KWD"
    if "CER" in text:
        return "ARS + CER"
    if "ICC" in text:
        return "ARS + ICC"
    if "PESO" in text or text == "ARS":
        return "ARS"
    return raw_label.strip() if raw_label else "Sin identificar"


def sum_field(rows: list[dict[str, object]], field: str) -> float | None:
    numbers = [as_float(row.get(field)) for row in rows]
    valid = [number for number in numbers if number is not None]
    return sum(valid) if valid else None


def load_santa_fe_debt(connection: sqlite3.Connection) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, str | None]]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    priorities: dict[tuple[str, str], int] = {}
    source_lookup: dict[str, dict[str, str | None]] = {}
    for source in connection.execute("SELECT period, source_url, local_path FROM fuentes"):
        source_lookup[str(source["period"])] = {
            "source_url": source["source_url"],
            "local_path": source["local_path"],
        }
    query = """
        SELECT period, frequency, period_end, tipo_fila, is_total, is_detail,
               acreedor, subgrupo, nivel, instrumento, moneda_instrumento,
               stock_pesos, uso_credito_cum, amort_pag_cum, intereses_pag_cum,
               row_key, orden
        FROM deuda_publica_long
    """
    for source_row in connection.execute(query):
        converted = normalized_debt_period(str(source_row["period"]), source_row["frequency"])
        if not converted:
            continue
        normalized, priority = converted
        source_period = str(source_row["period"])
        key = (normalized, source_period)
        priorities[key] = priority
        row = dict(source_row)
        row.update({
            "category_raw": row.get("acreedor"),
            "group_raw": row.get("subgrupo"),
            "instrument_raw": row.get("instrumento"),
            "currency_raw": row.get("moneda_instrumento"),
            "level": row.get("nivel"),
            "source_period": source_period,
            **source_lookup.get(source_period, {}),
        })
        groups[key].append(row)

    selected: dict[str, list[dict[str, object]]] = {}
    selected_sources: dict[str, dict[str, str | None]] = {}
    candidates: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for normalized, source_period in groups:
        candidates[normalized].append((priorities[(normalized, source_period)], source_period))
    for normalized, options in candidates.items():
        _, source_period = sorted(options, key=lambda item: (item[0], item[1]))[-1]
        selected[normalized] = groups[(normalized, source_period)]
        selected_sources[normalized] = source_lookup.get(source_period, {})
    return selected, selected_sources


def load_santa_fe_monthly_stock(connection: sqlite3.Connection) -> dict[str, float | None]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    query = """
        SELECT period, tipo_fila, is_total, acreedor, stock_pesos
        FROM deuda_publica_long
        WHERE frequency = 'monthly'
          AND period GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
    """
    for source_row in connection.execute(query):
        period = str(source_row["period"])
        if MONTH_RE.match(period):
            row = dict(source_row)
            row["category_raw"] = row.get("acreedor")
            grouped[period].append(row)
    output: dict[str, float | None] = {}
    for period, rows in grouped.items():
        total_row = debt_total_row("santa_fe", rows)
        output[period] = as_float(total_row.get("stock_pesos")) if total_row else None
    return output


def load_reported_debt_fx(connection: sqlite3.Connection) -> dict[str, float]:
    output: dict[str, float] = {}
    priorities: dict[str, int] = {}
    query = """
        SELECT period, frequency, rate, reported_rate_available
        FROM tipo_cambio_deuda
        WHERE currency_from = 'USD'
          AND currency_to = 'ARS'
    """
    for row in connection.execute(query):
        rate = as_float(row["rate"])
        if not row["reported_rate_available"] or rate is None or rate <= 0:
            continue
        period = str(row["period"])
        if PERIOD_RE.match(period):
            normalized, priority = period, 1
        else:
            match = MONTH_RE.match(period)
            if not match or int(match.group(2)) not in {3, 6, 9, 12}:
                continue
            normalized, priority = f"{match.group(1)}Q{int(match.group(2)) // 3}", 2
        if priority >= priorities.get(normalized, -1):
            output[normalized] = rate
            priorities[normalized] = priority
    return output


def load_neuquen_debt(connection: sqlite3.Connection) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, str | None]]]:
    selected: dict[str, list[dict[str, object]]] = defaultdict(list)
    sources: dict[str, dict[str, str | None]] = {}
    query = """
        SELECT period, period_end, is_total, is_detail, acreedor, grupo, subgrupo,
               moneda, stock_pesos, uso_credito_cum, amort_pag_cum,
               intereses_pag_cum, row_key, source_url, local_path
        FROM deuda_publica_long
        WHERE period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]'
    """
    for source_row in connection.execute(query):
        period = str(source_row["period"])
        row = dict(source_row)
        row.update({
            "tipo_fila": None,
            "category_raw": row.get("acreedor"),
            "group_raw": row.get("grupo") or row.get("subgrupo"),
            "instrument_raw": row.get("acreedor"),
            "currency_raw": row.get("moneda"),
            "level": None,
            "source_period": period,
        })
        selected[period].append(row)
        if period not in sources and row.get("source_url"):
            sources[period] = {
                "source_url": row.get("source_url"),
                "local_path": row.get("local_path"),
            }
    return dict(selected), sources


def load_neuquen_stock_file(path: Path) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, str | None]]]:
    selected: dict[str, list[dict[str, object]]] = defaultdict(list)
    sources: dict[str, dict[str, str | None]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for source_row in csv.DictReader(source):
            period = source_row.get("period", "")
            if not PERIOD_RE.match(period):
                continue
            level = int(float(source_row.get("nivel") or -1))
            row = dict(source_row)
            row.update({
                "is_total": source_row.get("tipo_fila") == "Total",
                "is_detail": source_row.get("tipo_fila") == "Detalle",
                "category_raw": source_row.get("emisor"),
                "group_raw": source_row.get("subgrupo"),
                "instrument_raw": source_row.get("emision_en_particular"),
                "currency_raw": source_row.get("moneda"),
                "level": level,
                "source_period": period,
                "source_layout": "stock_v3",
                "uso_credito_cum": None,
                "amort_pag_cum": None,
                "intereses_pag_cum": None,
            })
            selected[period].append(row)
            if period not in sources and source_row.get("source_url"):
                sources[period] = {
                    "source_url": source_row.get("source_url"),
                    "local_path": source_row.get("local_path"),
                }
    return dict(selected), sources


def load_neuquen_metric_cumulative(path: Path) -> dict[str, dict[str, float | None]]:
    metric_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    international_subgroups = {"BID", "BIRF", "ENOHSA", "FIDA"}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            period = row.get("period", "")
            if not PERIOD_RE.match(period) or row.get("construction") != "reportado":
                continue
            metric = row.get("metric", "")
            if metric not in {"uso_credito", "amortizacion_base_caja", "intereses_base_caja", "comisiones_base_caja"}:
                continue
            value = as_float(row.get("value"))
            if value is None:
                continue
            emitter = norm_text(row.get("emisor"))
            subgroup = norm_text(row.get("subgrupo"))
            row_type = norm_text(row.get("tipo_fila"))
            if row_type == "TOTAL":
                metric_values[(period, metric, "total")].append(value)
            if metric == "uso_credito" and row_type == "DETALLE" and subgroup == "TITULOS PUBLICOS INTERNACIONALES":
                metric_values[(period, metric, "international_bonds")].append(value)
            direct_ooii = emitter == "PRESTAMOS DIRECTOS CON ORGANISMOS INTERNACIONALES" and row_type == "SUBTOTAL"
            via_nation = emitter == "GOBIERNO NACIONAL" and row_type == "SUBTOTAL SUBGRUPO" and subgroup in international_subgroups
            if direct_ooii or via_nation:
                metric_values[(period, metric, "ooii")].append(value)

    periods = sorted({key[0] for key in metric_values}, key=period_index)
    output: dict[str, dict[str, float | None]] = {}
    for period in periods:
        def total(metric: str, scope: str) -> float | None:
            rows = metric_values.get((period, metric, scope), [])
            return sum(rows) if rows else None

        total_interest = total("intereses_base_caja", "total")
        total_commissions = total("comisiones_base_caja", "total")
        ooii_interest = add_numbers(total("intereses_base_caja", "ooii"), total("comisiones_base_caja", "ooii"))
        output[period] = {
            "total_use": total("uso_credito", "total"),
            "total_amort": total("amortizacion_base_caja", "total"),
            "total_interest": total_interest,
            "total_commissions": total_commissions,
            "intl_bond_use": total("uso_credito", "international_bonds"),
            "ooii_use": total("uso_credito", "ooii"),
            "ooii_amort": total("amortizacion_base_caja", "ooii"),
            "ooii_interest": ooii_interest,
        }
    return output


def debt_total_row(province_id: str, rows: list[dict[str, object]]) -> dict[str, object] | None:
    totals = [row for row in rows if bool(row.get("is_total"))]
    if province_id == "santa_fe":
        preferred = [row for row in totals if norm_text(row.get("category_raw")) == "TOTAL GENERAL"]
        return preferred[0] if preferred else (totals[0] if totals else None)
    return totals[0] if totals else None


def debt_top_categories(province_id: str, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if province_id == "santa_fe":
        return [row for row in rows if row.get("tipo_fila") == "Categoria" and int(row.get("level") or -1) == 1]
    if any(row.get("source_layout") == "stock_v3" for row in rows):
        return [row for row in rows if row.get("tipo_fila") == "Subtotal" and int(row.get("level") or -1) == 1]
    output = []
    for row in rows:
        if row.get("is_total") or row.get("is_detail"):
            continue
        key = str(row.get("row_key") or "")
        if key.endswith("|||"):
            output.append(row)
    return output


def debt_special_rows(province_id: str, rows: list[dict[str, object]], kind: str) -> list[dict[str, object]]:
    if province_id == "santa_fe":
        if kind == "international_bonds":
            return [row for row in rows if int(row.get("level") or -1) == 2 and "TITULOS PUBLICOS INTERNACIONALES" in norm_text(row.get("group_raw")) and norm_text(row.get("instrument_raw")) == norm_text(row.get("group_raw"))]
        if kind == "ooii":
            via_nation = [row for row in rows if int(row.get("level") or -1) == 2 and "FINANCIAMIENTO DE ORGANISMOS INTERNACIONALES DE CREDITO" in norm_text(row.get("group_raw")) and norm_text(row.get("instrument_raw")) == norm_text(row.get("group_raw"))]
            direct = [row for row in rows if int(row.get("level") or -1) == 1 and "PRESTAMOS DIRECTOS CON ORGANISMOS INTERNACIONALES" in norm_text(row.get("category_raw"))]
            return via_nation + direct
    else:
        if kind == "international_bonds":
            return [row for row in rows if row.get("is_detail") and "TITULOS PUBLICOS INTERNACIONALES" in norm_text(row.get("group_raw"))]
        if kind == "ooii":
            via_nation = [row for row in rows if row.get("is_detail") and "FINANCIAMIENTO DE ORGANISMOS INTERNACIONALES DE CREDITO" in norm_text(row.get("group_raw"))]
            direct = [row for row in rows if not row.get("is_detail") and "PRESTAMOS DIRECTOS CON ORGANISMOS INTERNACIONALES" in norm_text(row.get("category_raw")) and str(row.get("row_key") or "").endswith("|||")]
            return via_nation + direct
    return []


def load_floating_debt(path_value: object) -> dict[str, dict[str, object]]:
    if not path_value:
        return {}
    path = Path(str(path_value))
    output: dict[str, dict[str, object]] = {}
    details: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            period = row.get("period", "")
            if not PERIOD_RE.match(period):
                continue
            value = as_float(row.get("value_millions_pesos"))
            if value is None:
                continue
            item = row.get("item") or "Sin identificar"
            if item not in details[period]:
                details[period][item] = {
                    "item": item,
                    "value": 0.0,
                    "source_url": row.get("source_url"),
                    "local_path": row.get("local_path"),
                }
            details[period][item]["value"] += value
    for period, items in details.items():
        source_total = next(
            (row["value"] for row in items.values() if norm_text(row["item"]) == "TOTAL DEUDA FLOTANTE"),
            None,
        )
        component_rows = [
            row for row in items.values()
            if norm_text(row["item"]) != "TOTAL DEUDA FLOTANTE"
            and "HABERES Y CARGAS SOCIALES" not in norm_text(row["item"])
        ]
        rows = sorted(component_rows, key=lambda item: item["value"], reverse=True)
        component_total = sum(row["value"] for row in rows)
        output[period] = {
            "total": source_total if source_total is not None else component_total,
            "details": rows,
            "component_total": component_total,
        }
    return output


def load_debt(province_id: str, spec: dict[str, object], checks: list[dict[str, object]]) -> dict[str, object]:
    path = Path(str(spec["debt_db"]))
    monthly_stock: dict[str, float | None] = {}
    reported_fx: dict[str, float] = {}
    if province_id == "neuquen" and spec.get("debt_stock_file"):
        grouped_rows, sources = load_neuquen_stock_file(Path(str(spec["debt_stock_file"])))
    else:
        with readonly_connection(path) as connection:
            grouped_rows, sources = load_santa_fe_debt(connection)
            monthly_stock = load_santa_fe_monthly_stock(connection)
            reported_fx = load_reported_debt_fx(connection)

    floating = load_floating_debt(spec.get("floating_debt_file"))
    snapshots: dict[str, dict[str, object]] = {}
    cumulative: dict[str, dict[str, float | None]] = {}

    for period in sorted(grouped_rows, key=period_index):
        rows = grouped_rows[period]
        total_row = debt_total_row(province_id, rows)
        if not total_row:
            checks.append({"province_id": province_id, "check_id": f"debt_total_{period}", "status": "fail", "detail": "No se encontró la fila de deuda total."})
            continue
        total_stock = as_float(total_row.get("stock_pesos"))

        category_values: dict[str, float] = defaultdict(float)
        category_raw: dict[str, list[str]] = defaultdict(list)
        for row in debt_top_categories(province_id, rows):
            value = as_float(row.get("stock_pesos"))
            if value is None:
                continue
            category = canonical_category(str(row.get("category_raw") or ""))
            category_values[category] += value
            category_raw[category].append(str(row.get("category_raw") or ""))
        categories = [
            {"category": category, "value": value, "raw_labels": sorted(set(category_raw[category]))}
            for category, value in sorted(category_values.items(), key=lambda item: item[1], reverse=True)
        ]

        currency_values: dict[str, float] = defaultdict(float)
        for row in rows:
            if not row.get("is_detail"):
                continue
            value = as_float(row.get("stock_pesos"))
            if value is None:
                continue
            currency_values[canonical_currency(row.get("currency_raw"))] += value
        identified_stock = sum(currency_values.values())
        if total_stock is not None and abs(total_stock - identified_stock) > max(1.0, abs(total_stock) * 0.0001):
            currency_values["Sin desagregar"] += total_stock - identified_stock
        currencies = [
            {"currency": currency, "value": value}
            for currency, value in sorted(currency_values.items(), key=lambda item: item[1], reverse=True)
            if abs(value) > 1e-9
        ]
        usd_stock_ars = currency_values.get("USD")
        foreign_stock_ars = sum(value for currency, value in currency_values.items() if currency in {"USD", "EUR", "KWD"} or (not currency.startswith("ARS") and currency not in {"Sin desagregar", "Sin identificar"}))

        ars_buckets = {"ARS", "ARS + CER", "ARS + ICC"}
        split_by_currency: dict[str, dict[str, float]] = defaultdict(lambda: {"usd": 0.0, "ars": 0.0, "otras": 0.0})
        for row in rows:
            if not row.get("is_detail"):
                continue
            value = as_float(row.get("stock_pesos"))
            if value is None:
                continue
            canonical = canonical_currency(row.get("currency_raw"))
            bucket = "usd" if canonical == "USD" else ("ars" if canonical in ars_buckets else "otras")
            split_by_currency[canonical_category(str(row.get("category_raw") or ""))][bucket] += value
        categories_by_currency = [
            {"category": category, **buckets}
            for category, buckets in sorted(split_by_currency.items(), key=lambda item: sum(item[1].values()), reverse=True)
            if abs(sum(buckets.values())) > 1e-9
        ]

        intl_bond_rows = debt_special_rows(province_id, rows, "international_bonds")
        ooii_rows = debt_special_rows(province_id, rows, "ooii")
        cumulative[period] = {
            "total_use": as_float(total_row.get("uso_credito_cum")),
            "total_amort": as_float(total_row.get("amort_pag_cum")),
            "total_interest": as_float(total_row.get("intereses_pag_cum")),
            "intl_bond_use": sum_field(intl_bond_rows, "uso_credito_cum"),
            "ooii_use": sum_field(ooii_rows, "uso_credito_cum"),
            "ooii_amort": sum_field(ooii_rows, "amort_pag_cum"),
            "ooii_interest": sum_field(ooii_rows, "intereses_pag_cum"),
        }
        snapshots[period] = {
            "period": period,
            "period_end": period_end(period),
            "source_period": str(total_row.get("source_period") or period),
            "total_stock": total_stock,
            "usd_stock_ars": usd_stock_ars,
            "foreign_stock_ars": foreign_stock_ars,
            "categories": categories,
            "categories_by_currency": categories_by_currency,
            "currencies": currencies,
            "floating_total": floating.get(period, {}).get("total"),
            "commercial_details": floating.get(period, {}).get("details", []),
            "source_url": total_row.get("source_url") or sources.get(period, {}).get("source_url"),
            "local_path": total_row.get("local_path") or sources.get(period, {}).get("local_path"),
        }

        if total_stock is not None:
            category_sum = sum(item["value"] for item in categories)
            difference = total_stock - category_sum
            checks.append({
                "province_id": province_id,
                "check_id": f"debt_categories_{period}",
                "status": "pass" if abs(difference) <= max(1.0, abs(total_stock) * 0.001) else "warn",
                "detail": f"Diferencia total menos categorías: {difference:.3f} millones de pesos.",
            })

    if province_id == "neuquen" and spec.get("debt_metrics_file"):
        clean_cumulative = load_neuquen_metric_cumulative(Path(str(spec["debt_metrics_file"])))
        for period, values in clean_cumulative.items():
            if period in cumulative:
                cumulative[period] = values

    flow_keys = ["total_use", "total_amort", "total_interest", "total_commissions", "intl_bond_use", "ooii_use", "ooii_amort", "ooii_interest"]
    flows: dict[str, dict[str, float | None]] = {}
    for period in sorted(cumulative, key=period_index):
        year, quarter = period_parts(period)
        previous = f"{year}Q{quarter - 1}" if quarter > 1 else None
        flows[period] = {}
        for key in flow_keys:
            current = cumulative[period].get(key)
            if current is None:
                flows[period][key] = None
            elif quarter == 1:
                flows[period][key] = current
            elif previous in cumulative and cumulative[previous].get(key) is not None:
                flows[period][key] = current - float(cumulative[previous][key])
            else:
                flows[period][key] = None

    for period, floating_record in floating.items():
        total = as_float(floating_record.get("total"))
        component_total = as_float(floating_record.get("component_total"))
        difference = subtract_numbers(total, component_total)
        tolerance = max(0.01, abs(total or 0.0) * 0.0001)
        checks.append({
            "province_id": province_id,
            "check_id": f"floating_debt_components_{period}",
            "status": "pass" if difference is not None and abs(difference) <= tolerance else "warn",
            "detail": f"Diferencia total publicado menos componentes: {difference:.3f} millones de pesos." if difference is not None else "No fue posible comparar total y componentes.",
        })

    return {
        "snapshots": snapshots,
        "cumulative": cumulative,
        "flows": flows,
        "periods": sorted(snapshots, key=period_index),
        "monthly_stock": monthly_stock,
        "reported_fx": reported_fx,
    }


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def add_numbers(*values: float | None) -> float | None:
    return sum(float(value) for value in values) if all(value is not None for value in values) else None


def subtract_numbers(first: float | None, second: float | None) -> float | None:
    return first - second if first is not None and second is not None else None


def build_indicators(
    province_id: str,
    spec: dict[str, object],
    fiscal: dict[str, object],
    debt: dict[str, object],
    macro: dict[str, dict[str, float | None]],
    ipc: dict[str, object],
    deposits: dict[tuple[str, str], dict[str, float]],
    checks: list[dict[str, object]],
) -> list[dict[str, object]]:
    values = fiscal["values"]
    keys = spec["fiscal_keys"]
    periods = fiscal["periods"]
    debt_snapshots = debt["snapshots"]
    debt_flows = debt["flows"]
    output: list[dict[str, object]] = []

    def fiscal_quarter(entity: str, period: str, concept: str) -> float | None:
        value = values.get((entity, period, keys[concept]))
        fallback_key = keys.get(f"{concept}_fallback")
        if value is None and fallback_key:
            value = values.get((entity, period, fallback_key))
        return value

    def inflation_factor(period: str) -> float | None:
        reference = as_float(ipc.get("reference"))
        quarter_index = as_float(ipc.get("quarterly", {}).get(period))
        return ratio(reference, quarter_index)

    def fiscal_quarter_real(entity: str, period: str, concept: str) -> float | None:
        value = fiscal_quarter(entity, period, concept)
        factor = inflation_factor(period)
        return value * factor if value is not None and factor is not None else None

    def fiscal_ltm(entity: str, period: str, concept: str, real: bool = False) -> float | None:
        getter = fiscal_quarter_real if real else fiscal_quarter
        numbers = [getter(entity, item_period, concept) for item_period in trailing_periods(period)]
        return add_numbers(*numbers)

    def fiscal_ltm_usd(period: str, concept: str) -> float | None:
        converted = [
            ratio(fiscal_quarter("APNOF", item_period, concept), macro.get(item_period, {}).get("average"))
            for item_period in trailing_periods(period)
        ]
        return add_numbers(*converted)

    def financial_component(period: str, component: str) -> float | None:
        component_keys = spec.get("financial_keys", {}).get(component, [])
        numbers = [values.get(("APNOF", period, item_key)) for item_key in component_keys]
        valid = [number for number in numbers if number is not None]
        return sum(float(number) for number in valid) if valid else 0.0

    def financial_component_ltm_usd(period: str, component: str) -> float | None:
        converted = [
            ratio(financial_component(item_period, component), macro.get(item_period, {}).get("average"))
            for item_period in trailing_periods(period)
        ]
        return add_numbers(*converted)

    def financial_residual_ltm_usd(period: str, total_concept: str, first_component: str, second_component: str) -> float | None:
        converted: list[float | None] = []
        for item_period in trailing_periods(period):
            total = fiscal_quarter("APNOF", item_period, total_concept)
            first = financial_component(item_period, first_component)
            second = financial_component(item_period, second_component)
            residual = total - first - second if total is not None and first is not None and second is not None else None
            converted.append(ratio(residual, macro.get(item_period, {}).get("average")))
        return add_numbers(*converted)

    def ltm_debt_ars(period: str, key: str) -> float | None:
        numbers = [debt_flows.get(item_period, {}).get(key) for item_period in trailing_periods(period)]
        return add_numbers(*numbers)

    def ltm_debt_usd(period: str, key: str) -> float | None:
        converted: list[float | None] = []
        for item_period in trailing_periods(period):
            value = debt_flows.get(item_period, {}).get(key)
            fx = macro.get(item_period, {}).get("average")
            converted.append(ratio(value, fx))
        return add_numbers(*converted)

    def add_metric(period: str, metric_id: str, value: float | None, numerator: float | None = None, denominator: float | None = None, note: str | None = None) -> None:
        output.append({
            "province_id": province_id,
            "period": period,
            "period_end": period_end(period),
            "metric_id": metric_id,
            "value": value,
            "numerator": numerator,
            "denominator": denominator,
            "status": "ok" if value is not None else "missing",
            "note": note,
        })

    for period in periods:
        current_ltm = trailing_periods(period)
        if not all(item_period in periods for item_period in current_ltm):
            continue

        inc_current = fiscal_ltm("APNOF", period, "ingresos_corrientes")
        inc_total = fiscal_ltm("APNOF", period, "ingresos_totales")
        copart = fiscal_ltm("APNOF", period, "coparticipacion_municipios")

        inc_current_real = fiscal_ltm("APNOF", period, "ingresos_corrientes", real=True)
        exp_current_real = fiscal_ltm("APNOF", period, "gastos_corrientes", real=True)
        result_econ_real = fiscal_ltm("APNOF", period, "resultado_economico", real=True)
        inc_total_real = fiscal_ltm("APNOF", period, "ingresos_totales", real=True)
        exp_total_real = fiscal_ltm("APNOF", period, "gastos_totales", real=True)
        exp_primary_real = fiscal_ltm("APNOF", period, "gastos_primarios", real=True)
        result_primary_real = fiscal_ltm("APNOF", period, "resultado_primario", real=True)
        result_financial_real = fiscal_ltm("APNOF", period, "resultado_financiero", real=True)
        amort_fiscal_real = fiscal_ltm("APNOF", period, "amortizacion_deuda_pasivos", real=True)
        borrowing_fiscal_real = fiscal_ltm("APNOF", period, "endeudamiento_publico_pasivos", real=True)
        contributions_apnof_real = fiscal_ltm("APNOF", period, "contribuciones_seguridad_social", real=True)
        copart_real = fiscal_ltm("APNOF", period, "coparticipacion_municipios", real=True)
        transfers_national_real = fiscal_ltm("APNOF", period, "ingresos_origen_nacional", real=True)
        transfers_current_real = fiscal_ltm("APNOF", period, "transferencias_corrientes_ingresos", real=True)
        capex_ird_real = fiscal_ltm("APNOF", period, "inversion_real_directa", real=True)
        capex_transfers_real = fiscal_ltm("APNOF", period, "transferencias_capital_gasto", real=True)
        capex_ltm_real = add_numbers(capex_ird_real, capex_transfers_real)
        real_note = f"Flujos trimestrales reexpresados al IPC nacional de {ipc.get('reference_date')}."

        add_metric(period, "balance_operativo_pct", ratio(result_econ_real, inc_current_real), result_econ_real, inc_current_real, real_note)
        add_metric(period, "balance_primario_pct", ratio(result_primary_real, inc_total_real), result_primary_real, inc_total_real, real_note)
        add_metric(period, "balance_financiero_pct", ratio(result_financial_real, inc_total_real), result_financial_real, inc_total_real, real_note)
        post_amort = subtract_numbers(result_financial_real, amort_fiscal_real)
        add_metric(period, "balance_post_amortizaciones_pct", ratio(post_amort, inc_total_real), post_amort, inc_total_real, real_note)
        post_debt = add_numbers(post_amort, borrowing_fiscal_real)
        add_metric(period, "balance_post_endeudamiento_pct", ratio(post_debt, inc_total_real), post_debt, inc_total_real, real_note)

        add_metric(period, "balance_seguridad_social_operativo_pct", ratio(result_econ_real, inc_current_real), result_econ_real, inc_current_real, f"Cálculo sobre APNOF. {real_note}")
        ss_excluding = subtract_numbers(contributions_apnof_real, exp_current_real)
        add_metric(period, "balance_seguridad_social_sin_aportes_pct", ratio(ss_excluding, inc_current_real), ss_excluding, inc_current_real, f"Cálculo sobre APNOF. {real_note}")
        ss_result_pre = fiscal_ltm("SS", period, "resultado_financiero_previo_figurativas", real=True)
        ss_income = fiscal_ltm("SS", period, "ingresos_totales", real=True)
        ss_contributions = fiscal_ltm("SS", period, "contribuciones_seguridad_social", real=True)
        ss_figurative = fiscal_ltm("SS", period, "contribuciones_figurativas", real=True)
        add_metric(period, "balance_seguridad_social_entidad_pct", ratio(ss_result_pre, ss_income), ss_result_pre, ss_income, real_note)
        ss_total_resources = add_numbers(ss_income, ss_figurative)
        add_metric(period, "contribuciones_seguridad_social_pct", ratio(ss_contributions, ss_total_resources), ss_contributions, ss_total_resources, real_note)

        add_metric(period, "capex_pct_gasto_total", ratio(capex_ltm_real, exp_total_real), capex_ltm_real, exp_total_real, real_note)
        add_metric(period, "capex_pct_gasto_primario", ratio(capex_ltm_real, exp_primary_real), capex_ltm_real, exp_primary_real, real_note)
        quarter_capex = add_numbers(
            fiscal_quarter("APNOF", period, "inversion_real_directa"),
            fiscal_quarter("APNOF", period, "transferencias_capital_gasto"),
        )
        quarter_capex_real = add_numbers(
            fiscal_quarter_real("APNOF", period, "inversion_real_directa"),
            fiscal_quarter_real("APNOF", period, "transferencias_capital_gasto"),
        )
        quarter_fx = macro.get(period, {}).get("average")
        quarter_capex_usd = ratio(quarter_capex, quarter_fx)
        add_metric(period, "capex_trimestral_usd_m", quarter_capex_usd, quarter_capex, quarter_fx)
        add_metric(period, "capex_trimestral_real_ars_m", quarter_capex_real, quarter_capex, inflation_factor(period), real_note)
        add_metric(period, "capex_ltm_real_ars_m", capex_ltm_real, capex_ltm_real, ipc.get("reference"), real_note)
        capex_usd_quarters = []
        for item_period in current_ltm:
            item_capex = add_numbers(
                fiscal_quarter("APNOF", item_period, "inversion_real_directa"),
                fiscal_quarter("APNOF", item_period, "transferencias_capital_gasto"),
            )
            capex_usd_quarters.append(ratio(item_capex, macro.get(item_period, {}).get("average")))
        add_metric(period, "capex_ltm_usd_m", add_numbers(*capex_usd_quarters))

        net_operating_income = subtract_numbers(inc_current, copart)
        net_operating_income_real = subtract_numbers(inc_current_real, copart_real)
        add_metric(period, "ingresos_operativos_netos_copart_ars_m", net_operating_income, inc_current, copart)
        add_metric(period, "ingresos_operativos_netos_copart_real_ars_m", net_operating_income_real, inc_current_real, copart_real, real_note)
        transfer_total_real = add_numbers(transfers_national_real, transfers_current_real)
        add_metric(period, "transferencias_pct_ingresos", ratio(transfer_total_real, inc_total_real), transfer_total_real, inc_total_real, real_note)

        snapshot = debt_snapshots.get(period)
        debt_total = snapshot.get("total_stock") if snapshot else None
        debt_usd_ars = snapshot.get("usd_stock_ars") if snapshot else None
        debt_foreign_ars = snapshot.get("foreign_stock_ars") if snapshot else None
        debt_floating = snapshot.get("floating_total") if snapshot else None
        reported_stock_fx = debt.get("reported_fx", {}).get(period)
        fx_end = reported_stock_fx or macro.get(period, {}).get("end")
        stock_fx_source = "Tipo de cambio de valuación informado por la provincia." if reported_stock_fx else "A3500 de cierre por falta de tipo de cambio provincial informado."
        debt_amortization = ltm_debt_ars(period, "total_amort")
        debt_interest = ltm_debt_ars(period, "total_interest")
        debt_service = add_numbers(debt_amortization, debt_interest)
        add_metric(period, "amortizaciones_pct_ingresos_operativos", ratio(debt_amortization, net_operating_income), debt_amortization, net_operating_income)
        add_metric(period, "intereses_pct_ingresos_operativos", ratio(debt_interest, net_operating_income), debt_interest, net_operating_income)
        add_metric(period, "servicio_deuda_pct_ingresos_operativos", ratio(debt_service, net_operating_income), debt_service, net_operating_income)
        add_metric(period, "deuda_usd_m", ratio(debt_usd_ars, fx_end), debt_usd_ars, fx_end, stock_fx_source)
        add_metric(period, "deuda_moneda_extranjera_pct", ratio(debt_foreign_ars, debt_total), debt_foreign_ars, debt_total)
        debt_plus_floating = add_numbers(debt_total, debt_floating)
        add_metric(period, "deuda_mas_flotante_pct_ingresos", ratio(debt_plus_floating, inc_total), debt_plus_floating, inc_total, "s/d cuando la provincia no publica una serie separada de deuda flotante.")
        add_metric(period, "deuda_total_ars_m", debt_total)
        add_metric(period, "deuda_pct_ingresos", ratio(debt_total, inc_total), debt_total, inc_total)
        deposit_record = deposits.get((province_id, period_month_key(period)), {})
        deposit_total = deposit_record.get("total")
        debt_net = subtract_numbers(debt_total, deposit_total)
        add_metric(period, "depositos_bcra_ars_m", deposit_total)
        add_metric(period, "deuda_neta_ars_m", debt_net, debt_total, deposit_total)
        add_metric(period, "deuda_neta_pct_ingresos", ratio(debt_net, inc_total), debt_net, inc_total)
        if snapshot is not None:
            snapshot["deposits_domestic"] = deposit_record.get("domestic")
            snapshot["deposits_foreign"] = deposit_record.get("foreign")
            snapshot["deposits_total"] = deposit_total
            snapshot["net_debt"] = debt_net
            snapshot["stock_fx"] = fx_end
            snapshot["stock_fx_source"] = "provincial" if reported_stock_fx else "a3500"

        total_borrowing_usd = ltm_debt_usd(period, "total_use")
        intl_bond_usd = ltm_debt_usd(period, "intl_bond_use")
        ooii_borrowing_usd = ltm_debt_usd(period, "ooii_use")
        ooii_amort_usd = ltm_debt_usd(period, "ooii_amort")
        ooii_interest_usd = ltm_debt_usd(period, "ooii_interest")
        add_metric(period, "endeudamiento_total_usd_m", total_borrowing_usd)
        add_metric(period, "emision_bonos_internacionales_usd_m", intl_bond_usd)
        add_metric(period, "borrowings_ooii_usd_m", ooii_borrowing_usd)
        add_metric(period, "amortizacion_ooii_usd_m", ooii_amort_usd)
        add_metric(period, "intereses_ooii_usd_m", ooii_interest_usd)
        add_metric(period, "saldo_neto_endeudamiento_ooii_usd_m", subtract_numbers(ooii_borrowing_usd, ooii_amort_usd), ooii_borrowing_usd, ooii_amort_usd)

        fiscal_result_usd = fiscal_ltm_usd(period, "resultado_financiero")
        fiscal_amort_total_usd = fiscal_ltm_usd(period, "amortizacion_deuda_pasivos")
        fiscal_amort_commercial_usd = financial_component_ltm_usd(period, "amortization_commercial")
        fiscal_amort_ooii_usd = financial_component_ltm_usd(period, "amortization_multilateral")
        fiscal_amort_other_usd = financial_residual_ltm_usd(
            period,
            "amortizacion_deuda_pasivos",
            "amortization_commercial",
            "amortization_multilateral",
        )
        fiscal_borrowing_total_usd = fiscal_ltm_usd(period, "endeudamiento_publico_pasivos")
        fiscal_borrowing_commercial_usd = financial_component_ltm_usd(period, "borrowing_commercial")
        fiscal_borrowing_ooii_usd = financial_component_ltm_usd(period, "borrowing_multilateral")
        fiscal_borrowing_other_usd = financial_residual_ltm_usd(
            period,
            "endeudamiento_publico_pasivos",
            "borrowing_commercial",
            "borrowing_multilateral",
        )
        investment_decrease_usd = financial_component_ltm_usd(period, "financial_investment_decrease")
        investment_application_usd = financial_component_ltm_usd(period, "financial_investment_application")
        investment_change_usd = subtract_numbers(investment_decrease_usd, investment_application_usd)
        add_metric(period, "fuentes_resultado_financiero_usd_m", fiscal_result_usd)
        add_metric(period, "fuentes_amort_total_usd_m", fiscal_amort_total_usd)
        add_metric(period, "fuentes_amort_comercial_usd_m", fiscal_amort_commercial_usd)
        add_metric(period, "fuentes_amort_ooii_usd_m", fiscal_amort_ooii_usd)
        add_metric(period, "fuentes_amort_otras_usd_m", fiscal_amort_other_usd)
        add_metric(period, "fuentes_endeudamiento_total_usd_m", fiscal_borrowing_total_usd)
        add_metric(period, "fuentes_endeudamiento_comercial_usd_m", fiscal_borrowing_commercial_usd)
        add_metric(period, "fuentes_endeudamiento_ooii_usd_m", fiscal_borrowing_ooii_usd)
        add_metric(period, "fuentes_endeudamiento_otros_usd_m", fiscal_borrowing_other_usd)
        add_metric(period, "fuentes_variacion_inversion_financiera_usd_m", investment_change_usd)

    latest = max((row["period"] for row in output), key=period_index, default=None)
    if latest:
        latest_missing = sum(1 for row in output if row["period"] == latest and row["status"] == "missing")
        checks.append({
            "province_id": province_id,
            "check_id": "latest_indicator_coverage",
            "status": "pass" if latest_missing == 0 else "warn",
            "detail": f"{len(INDICATOR_DEFINITIONS) - latest_missing}/{len(INDICATOR_DEFINITIONS)} indicadores disponibles en {latest}.",
        })
    return output


def build_monthly_trends(
    province_id: str,
    spec: dict[str, object],
    fiscal: dict[str, object],
    debt: dict[str, object],
    monthly_macro: dict[str, dict[str, float | None]],
    ipc: dict[str, object],
    deposits: dict[tuple[str, str], dict[str, float]],
) -> dict[str, object]:
    if province_id != "santa_fe" or not fiscal.get("monthly_periods"):
        return {"frequency": "quarterly", "periods": [], "metrics": {}}

    values = fiscal["values"]
    keys = spec["fiscal_keys"]
    available_periods = set(fiscal["monthly_periods"])
    reference = as_float(ipc.get("reference"))
    monthly_ipc = ipc.get("monthly", {})
    monthly_stock = debt.get("monthly_stock", {})
    metric_ids = [
        "balance_operativo_pct",
        "balance_primario_pct",
        "balance_financiero_pct",
        "capex_pct_gasto_primario",
        "capex_ltm_real_ars_m",
        "capex_ltm_usd_m",
        "deuda_pct_ingresos",
        "deuda_neta_pct_ingresos",
    ]
    series: dict[str, list[dict[str, object]]] = {metric_id: [] for metric_id in metric_ids}
    output_periods: list[str] = []

    def monthly_value(period: str, concept: str) -> float | None:
        return values.get(("APNOF", period, keys[concept]))

    def monthly_real(period: str, concept: str) -> float | None:
        value = monthly_value(period, concept)
        month_ipc = as_float(monthly_ipc.get(period))
        factor = ratio(reference, month_ipc)
        return value * factor if value is not None and factor is not None else None

    def ltm(period: str, concept: str, real: bool = False) -> float | None:
        getter = monthly_real if real else monthly_value
        return add_numbers(*(getter(item_period, concept) for item_period in trailing_months(period)))

    def append(metric_id: str, period: str, value: float | None) -> None:
        series[metric_id].append({
            "period": period,
            "value": value,
            "status": "ok" if value is not None else "missing",
        })

    for period in fiscal["monthly_periods"]:
        months = trailing_months(period)
        if not all(item_period in available_periods for item_period in months):
            continue
        output_periods.append(period)
        income_current_real = ltm(period, "ingresos_corrientes", real=True)
        income_total_real = ltm(period, "ingresos_totales", real=True)
        result_economic_real = ltm(period, "resultado_economico", real=True)
        result_primary_real = ltm(period, "resultado_primario", real=True)
        result_financial_real = ltm(period, "resultado_financiero", real=True)
        primary_spending_real = ltm(period, "gastos_primarios", real=True)
        capex_real = add_numbers(
            ltm(period, "inversion_real_directa", real=True),
            ltm(period, "transferencias_capital_gasto", real=True),
        )
        capex_usd_months: list[float | None] = []
        for item_period in months:
            capex_nominal = add_numbers(
                monthly_value(item_period, "inversion_real_directa"),
                monthly_value(item_period, "transferencias_capital_gasto"),
            )
            capex_usd_months.append(ratio(capex_nominal, monthly_macro.get(item_period, {}).get("average")))

        income_total_nominal = ltm(period, "ingresos_totales")
        gross_debt = as_float(monthly_stock.get(period))
        deposit_record = deposits.get((province_id, f"{period}-01"), {})
        net_debt = subtract_numbers(gross_debt, deposit_record.get("total"))

        append("balance_operativo_pct", period, ratio(result_economic_real, income_current_real))
        append("balance_primario_pct", period, ratio(result_primary_real, income_total_real))
        append("balance_financiero_pct", period, ratio(result_financial_real, income_total_real))
        append("capex_pct_gasto_primario", period, ratio(capex_real, primary_spending_real))
        append("capex_ltm_real_ars_m", period, capex_real)
        append("capex_ltm_usd_m", period, add_numbers(*capex_usd_months))
        append("deuda_pct_ingresos", period, ratio(gross_debt, income_total_nominal))
        append("deuda_neta_pct_ingresos", period, ratio(net_debt, income_total_nominal))

    return {
        "frequency": "monthly",
        "periods": output_periods,
        "latest_period": output_periods[-1] if output_periods else None,
        "metrics": series,
    }


def build_fiscal_flows(
    province_id: str,
    spec: dict[str, object],
    fiscal: dict[str, object],
    ipc: dict[str, object],
) -> list[dict[str, object]]:
    values = fiscal["values"]
    keys = spec["fiscal_keys"]
    reference = as_float(ipc.get("reference"))
    rows: list[dict[str, object]] = []

    def value_for(entity: str, period: str, concept: str) -> float | None:
        value = values.get((entity, period, keys[concept]))
        fallback_key = keys.get(f"{concept}_fallback")
        if value is None and fallback_key:
            value = values.get((entity, period, fallback_key))
        return value

    def append_row(entity: str, period: str, concept_id: str, nominal: float | None, note: str | None = None) -> None:
        quarter_ipc = as_float(ipc.get("quarterly", {}).get(period))
        factor = ratio(reference, quarter_ipc)
        rows.append({
            "province_id": province_id,
            "period": period,
            "period_end": period_end(period),
            "entity": entity,
            "concept_id": concept_id,
            "nominal_ars_m": nominal,
            "ipc_quarter_average": quarter_ipc,
            "ipc_reference": reference,
            "inflation_factor": factor,
            "real_ars_m": nominal * factor if nominal is not None and factor is not None else None,
            "note": note,
        })

    concepts = [concept for concept in keys if not concept.endswith("_fallback")]
    for period in fiscal["periods"]:
        for entity in ("APNOF", "SS"):
            for concept in concepts:
                nominal = value_for(entity, period, concept)
                if nominal is not None:
                    append_row(entity, period, concept, nominal)

        capex = add_numbers(
            value_for("APNOF", period, "inversion_real_directa"),
            value_for("APNOF", period, "transferencias_capital_gasto"),
        )
        append_row("APNOF", period, "capex", capex, "Excluye inversion financiera.")
        net_operating = subtract_numbers(
            value_for("APNOF", period, "ingresos_corrientes"),
            value_for("APNOF", period, "coparticipacion_municipios"),
        )
        append_row(
            "APNOF",
            period,
            "ingresos_operativos_netos_copart",
            net_operating,
            "Ingresos corrientes menos coparticipacion y transferencias automaticas a municipios.",
        )
    return rows


def create_database(
    path: Path,
    definitions: list[dict[str, object]],
    indicators: list[dict[str, object]],
    fiscal_flows: list[dict[str, object]],
    provinces: dict[str, object],
    checks: list[dict[str, object]],
    generated_at: str,
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode = DELETE;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE indicator_definitions (
            metric_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            section TEXT NOT NULL,
            description TEXT NOT NULL,
            unit TEXT NOT NULL,
            direction TEXT NOT NULL,
            source_scope TEXT NOT NULL
        );
        CREATE TABLE indicators (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            period_end TEXT NOT NULL,
            metric_id TEXT NOT NULL,
            value REAL,
            numerator REAL,
            denominator REAL,
            status TEXT NOT NULL,
            note TEXT,
            PRIMARY KEY (province_id, period, metric_id)
        );
        CREATE TABLE fiscal_flows (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            period_end TEXT NOT NULL,
            entity TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            nominal_ars_m REAL,
            ipc_quarter_average REAL,
            ipc_reference REAL,
            inflation_factor REAL,
            real_ars_m REAL,
            note TEXT,
            PRIMARY KEY (province_id, period, entity, concept_id)
        );
        CREATE TABLE debt_categories (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            category TEXT NOT NULL,
            value_ars_m REAL NOT NULL,
            raw_labels TEXT,
            PRIMARY KEY (province_id, period, category)
        );
        CREATE TABLE debt_currencies (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            currency TEXT NOT NULL,
            value_ars_m REAL NOT NULL,
            PRIMARY KEY (province_id, period, currency)
        );
        CREATE TABLE commercial_debt (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            item TEXT NOT NULL,
            value_ars_m REAL NOT NULL,
            source_url TEXT,
            local_path TEXT,
            PRIMARY KEY (province_id, period, item)
        );
        CREATE TABLE debt_liquidity (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            deposits_domestic_ars_m REAL,
            deposits_foreign_ars_m REAL,
            deposits_total_ars_m REAL,
            gross_debt_ars_m REAL,
            net_debt_ars_m REAL,
            PRIMARY KEY (province_id, period)
        );
        CREATE TABLE monthly_trends (
            province_id TEXT NOT NULL,
            period TEXT NOT NULL,
            period_end TEXT NOT NULL,
            metric_id TEXT NOT NULL,
            value REAL,
            status TEXT NOT NULL,
            PRIMARY KEY (province_id, period, metric_id)
        );
        CREATE TABLE quality_checks (
            province_id TEXT NOT NULL,
            check_id TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL
        );
        CREATE INDEX idx_indicators_period ON indicators(period, province_id);
        CREATE INDEX idx_fiscal_flows_period ON fiscal_flows(period, province_id);
        CREATE INDEX idx_monthly_trends_period ON monthly_trends(period, province_id);
    """)
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
        ("generated_at", generated_at),
        ("schema_version", "1.2.0"),
        ("basis", "Devengado trimestral; flujos LTM = últimos cuatro trimestres; flujos reales a IPC nacional más reciente"),
    ])
    connection.executemany(
        "INSERT INTO indicator_definitions VALUES (:id, :label, :section, :description, :unit, :direction, :source_scope)",
        definitions,
    )
    connection.executemany(
        "INSERT INTO indicators VALUES (:province_id, :period, :period_end, :metric_id, :value, :numerator, :denominator, :status, :note)",
        indicators,
    )
    connection.executemany(
        "INSERT INTO fiscal_flows VALUES (:province_id, :period, :period_end, :entity, :concept_id, :nominal_ars_m, :ipc_quarter_average, :ipc_reference, :inflation_factor, :real_ars_m, :note)",
        fiscal_flows,
    )
    for province_id, province in provinces.items():
        snapshots = province["debt"]["snapshots"]
        category_rows = []
        currency_rows = []
        commercial_rows = []
        liquidity_rows = []
        monthly_trend_rows = []
        for period, snapshot in snapshots.items():
            category_rows.extend((province_id, period, item["category"], item["value"], json.dumps(item["raw_labels"], ensure_ascii=False)) for item in snapshot["categories"])
            currency_rows.extend((province_id, period, item["currency"], item["value"]) for item in snapshot["currencies"])
            commercial_rows.extend((province_id, period, item["item"], item["value"], item.get("source_url"), item.get("local_path")) for item in snapshot["commercial_details"])
            liquidity_rows.append((
                province_id,
                period,
                snapshot.get("deposits_domestic"),
                snapshot.get("deposits_foreign"),
                snapshot.get("deposits_total"),
                snapshot.get("total_stock"),
                snapshot.get("net_debt"),
            ))
        connection.executemany("INSERT INTO debt_categories VALUES (?, ?, ?, ?, ?)", category_rows)
        connection.executemany("INSERT INTO debt_currencies VALUES (?, ?, ?, ?)", currency_rows)
        connection.executemany("INSERT INTO commercial_debt VALUES (?, ?, ?, ?, ?, ?)", commercial_rows)
        connection.executemany("INSERT INTO debt_liquidity VALUES (?, ?, ?, ?, ?, ?, ?)", liquidity_rows)
        for metric_id, metric_series in province.get("trends", {}).get("metrics", {}).items():
            monthly_trend_rows.extend((province_id, item["period"], month_period_end(item["period"]), metric_id, item["value"], item["status"]) for item in metric_series)
        connection.executemany("INSERT INTO monthly_trends VALUES (?, ?, ?, ?, ?, ?)", monthly_trend_rows)
    connection.executemany("INSERT INTO quality_checks VALUES (:province_id, :check_id, :status, :detail)", checks)
    connection.commit()
    connection.close()


def build_payload(
    config: dict[str, object],
    macro: dict[str, dict[str, float | None]],
    monthly_macro: dict[str, dict[str, float | None]],
    ipc: dict[str, object],
    deposits: dict[tuple[str, str], dict[str, float]],
    checks: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    province_output: dict[str, object] = {}
    all_indicators: list[dict[str, object]] = []
    all_fiscal_flows: list[dict[str, object]] = []
    for province_id, spec in config["provinces"].items():
        fiscal = load_fiscal(province_id, spec, checks)
        debt = load_debt(province_id, spec, checks)
        indicators = build_indicators(province_id, spec, fiscal, debt, macro, ipc, deposits, checks)
        trends = build_monthly_trends(province_id, spec, fiscal, debt, monthly_macro, ipc, deposits)
        all_indicators.extend(indicators)
        all_fiscal_flows.extend(build_fiscal_flows(province_id, spec, fiscal, ipc))
        series: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in indicators:
            series[row["metric_id"]].append({
                "period": row["period"],
                "value": row["value"],
                "status": row["status"],
            })
        periods = sorted({row["period"] for row in indicators}, key=period_index)
        province_output[province_id] = {
            "id": province_id,
            "name": spec["name"],
            "periods": periods,
            "latest_period": periods[-1] if periods else None,
            "metrics": dict(series),
            "trends": trends,
            "debt": debt,
        }
    return province_output, all_indicators, all_fiscal_flows


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def main() -> int:
    with CONFIG_PATH.open("r", encoding="utf-8") as source:
        config = json.load(source)
    source_paths = [Path(config["macro_file"]), Path(config["monthly_macro_file"]), Path(config["ipc_file"]), Path(config["deposits_file"])]
    for spec in config["provinces"].values():
        source_paths.extend([Path(spec["fiscal_db"]), Path(spec["debt_db"])])
        if spec.get("debt_stock_file"):
            source_paths.append(Path(spec["debt_stock_file"]))
        if spec.get("debt_metrics_file"):
            source_paths.append(Path(spec["debt_metrics_file"]))
        if spec.get("floating_debt_file"):
            source_paths.append(Path(spec["floating_debt_file"]))
    missing_sources = [str(path) for path in source_paths if not path.exists()]
    if missing_sources:
        raise FileNotFoundError("No se encontraron fuentes:\n" + "\n".join(missing_sources))

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    checks: list[dict[str, object]] = []
    macro = load_macro(Path(config["macro_file"]))
    monthly_macro = load_monthly_macro(Path(config["monthly_macro_file"]))
    ipc = load_ipc(Path(config["ipc_file"]))
    deposits = load_deposits(Path(config["deposits_file"]))
    provinces, indicators, fiscal_flows = build_payload(config, macro, monthly_macro, ipc, deposits, checks)
    manifest = {
        "generated_at": generated_at,
        "schema_version": config["schema_version"],
        "sources": [file_fingerprint(path) for path in dict.fromkeys(source_paths)],
        "province_summary": {
            province_id: {
                "name": province["name"],
                "latest_period": province["latest_period"],
                "period_count": len(province["periods"]),
            }
            for province_id, province in provinces.items()
        },
    }
    payload = {
        "metadata": {
            "generated_at": generated_at,
            "schema_version": config["schema_version"],
            "basis": "Devengado; flujos LTM sobre cuatro trimestres y tendencias mensuales de Santa Fe sobre doce meses.",
            "fx_method": "A3500 promedio para flujos; tipo de cambio de valuación provincial para stocks cuando está informado y A3500 de cierre como respaldo.",
            "ipc_reference_date": ipc.get("reference_date"),
            "ipc_reference_index": ipc.get("reference"),
            "frozen_source_version": config.get("frozen_source_version"),
        },
        "definitions": INDICATOR_DEFINITIONS,
        "provinces": provinces,
        "quality": checks,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_DIR.mkdir(parents=True, exist_ok=True)
    for stale_file in DATA_DIR.glob(".base_consolidada_*.sqlite"):
        if stale_file.parent == DATA_DIR:
            stale_file.unlink()
    for candidate in VERSION_DIR.iterdir():
        if candidate.is_dir() and not any(candidate.iterdir()):
            candidate.rmdir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_path = VERSION_DIR / timestamp
    temporary_db = DATA_DIR / f".base_consolidada_{timestamp}.sqlite"
    create_database(temporary_db, INDICATOR_DEFINITIONS, indicators, fiscal_flows, provinces, checks, generated_at)

    json_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    pretty_manifest = json.dumps(manifest, ensure_ascii=False, indent=2)
    pretty_checks = json.dumps(checks, ensure_ascii=False, indent=2)
    atomic_write(DATA_DIR / "dashboard_data.json", json_text)
    atomic_write(DATA_DIR / "dashboard_data.js", "window.PROVINCIAS_DATA = " + json_text + ";\n")
    atomic_write(DATA_DIR / "manifest.json", pretty_manifest + "\n")
    atomic_write(DATA_DIR / "control_calidad.json", pretty_checks + "\n")
    os.replace(temporary_db, DATA_DIR / "base_consolidada.sqlite")

    version_path.mkdir(parents=True, exist_ok=False)
    shutil.copy2(DATA_DIR / "base_consolidada.sqlite", version_path / "base_consolidada.sqlite")
    shutil.copy2(DATA_DIR / "dashboard_data.json", version_path / "dashboard_data.json")
    shutil.copy2(DATA_DIR / "manifest.json", version_path / "manifest.json")
    shutil.copy2(DATA_DIR / "control_calidad.json", version_path / "control_calidad.json")

    print(f"Actualización completada: {generated_at}")
    for province_id, province in provinces.items():
        warnings = sum(1 for item in checks if item["province_id"] == province_id and item["status"] != "pass")
        print(f"- {province['name']}: {province['latest_period']} | {len(province['periods'])} períodos | {warnings} advertencias")
    print(f"- Versión: {version_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
