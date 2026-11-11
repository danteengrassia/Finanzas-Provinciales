# Metodología

## Integración de Mendoza, Córdoba y Entre Ríos

- Mendoza suma meses completos de AIF y usa el orden 57 para el resultado
  financiero. El orden 62 incorpora operaciones de financiamiento. Las cuentas
  previsionales y los desgloses de fuentes sin equivalencia quedan como `s/d`.
- Córdoba publica amortizaciones e intereses devengados en la extracción
  integrada. Se usan para el servicio del resumen y para organismos
  internacionales. La deuda flotante
  histórica se suma por separado al stock de deuda pública.
- Entre Ríos usa los IDs fiscales compartidos entre APNOF y Seguridad Social.
  El resumen usa los flujos devengados. La serie de intereses
  de deuda incluye accesorios. El stock de flotante excluye la utilización
  del FUCO, que figura como informativa en la fuente.

## Resumen y detalle

El resumen usa base devengado. Para Mendoza, el servicio se obtiene del AIF
devengado con las cuentas de amortización consolidada e intereses y gastos de
la deuda. Para las fuentes y aplicaciones se toma la cuenta comercial combinada
cuando está identificada, o sus componentes explícitos. Los préstamos
genéricos quedan en el residual. Otras amortizaciones y otros endeudamientos
son el total menos el tramo comercial y el multilateral.

Las pestañas de detalle permiten comparar varios períodos en columnas. Para
flujos se puede elegir mensual, trimestral o acumulado desde enero hasta cada
cierre, según la frecuencia disponible en la fuente. Los flujos mensuales se
habilitan únicamente si corresponden a un mes completo. Los flujos usan el
A3500 promedio o el IPC promedio del período. Para acumulados, el promedio de
A3500 se pondera por la cantidad de observaciones diarias de cada mes y el IPC
es el promedio de los meses comprendidos. Los stocks muestran cierres mensuales
o trimestrales disponibles y
usan el tipo provincial informado o el A3500 de cierre y el IPC del mes final.
La reexpresión usa el último IPC nacional disponible. La vista Caja conserva
el alcance de la fuente. En Santa Fe, el AIF pagado cubre el ejercicio corriente.

## Alcance y fuentes

La versión consolida información fiscal base devengado, seguridad social, stock y servicio de deuda de Santa Fe y Neuquén. Los indicadores de flujo utilizan los últimos cuatro trimestres; los stocks corresponden al cierre de cada trimestre.

Las bases provinciales se leen desde copias congeladas. Santa Fe utiliza la construcción mensual devengada para los gráficos fiscales LTM y para deuda bruta y neta; el servicio de deuda se mantiene trimestral. Neuquén permanece trimestral. Todos los gráficos de series muestran como máximo los últimos ocho años.

## Flujos reales

Cada flujo trimestral se reexpresa al último IPC Nacional disponible:

`flujo real = flujo nominal × IPC de referencia / IPC promedio del trimestre`

Los saldos de los últimos 12 meses se obtienen sumando cuatro trimestres o doce meses ya reexpresados. La tabla `fiscal_flows` conserva la transformación trimestral y `monthly_trends` conserva las series mensuales de Santa Fe. La serie mensual LTM comparable comienza en diciembre de 2017 por disponibilidad del IPC Nacional base diciembre de 2016.

## Performance fiscal

Los balances operativo, primario y financiero se calculan con numeradores y denominadores reexpresados a precios de la misma fecha. Los ratios de stock de deuda se mantienen sobre ingresos totales nominales de los últimos cuatro trimestres, porque stock y denominador están expresados en pesos corrientes al cierre del período.

## Ingresos operativos y servicio

Los ingresos operativos netos son ingresos corrientes menos coparticipación y otras transferencias automáticas a municipios. En Neuquén la cuenta específica comienza en 2022; para la historia anterior se utiliza la cuenta más amplia `GASTOS CORRIENTES|MUNICIPIOS`. Este empalme recupera la serie histórica, pero antes de 2022 su alcance puede ser algo más amplio.

El servicio del resumen apila amortizaciones e intereses devengados de los últimos cuatro trimestres, divididos por ingresos operativos netos de coparticipación municipal. Entre Ríos informa intereses y accesorios de forma conjunta. La línea del 15% identifica la referencia del análisis.

## Inversión en infraestructura

CAPEX incluye inversión real directa más transferencias de capital. Excluye inversión financiera. Se presentan el monto real de los últimos cuatro trimestres, su participación en el gasto primario y su conversión a USD.

## Seguridad social

- Balance de seguridad social sobre ingresos operativos: base APNOF.
- Balance de seguridad social sin aportes tributarios directos: base APNOF.
- Balance financiero de la entidad previsional: base SS.
- Contribuciones de seguridad social sobre ingresos totales más figurativas: base SS.

## Deuda y depósitos

La deuda neta es deuda pública bruta menos depósitos en moneda nacional y extranjera del sector público provincial informados por BCRA. La fuente publica ambas series en miles de pesos; el actualizador valida esa unidad y divide por 1.000 para trabajar en millones de pesos. La tabla `debt_liquidity` conserva los dos componentes, el total de depósitos, la deuda bruta y la deuda neta.

El perímetro institucional de los depósitos BCRA puede ser más amplio que el de la deuda provincial publicada. Por eso una deuda neta negativa se interpreta como posición financiera neta bajo esta cobertura, no como una conciliación contable exacta.

Los flujos en USD se convierten con A3500 promedio. Para los stocks de Santa Fe se utiliza el tipo de cambio de valuación informado por la provincia; si no está disponible para ese cierre se usa A3500. Los intereses de organismos internacionales sí incluyen comisiones cuando la fuente los informa conjuntamente.

## Fuentes y aplicaciones financieras

El resultado financiero, las amortizaciones, el endeudamiento y la variación de inversiones financieras se presentan en USD millones y acumulados en los últimos 12 meses. Cada flujo trimestral se convierte antes de sumarse.

- Comercial: títulos, letras y préstamos bancarios o financieros.
- Organismos internacionales: préstamos multilaterales identificados en el AIF.
- Otros: residual conciliado contra el total publicado.
- Variación de inversiones financieras: disminuciones menos aumentos. Un valor positivo representa uso neto de caja y uno negativo, acumulación neta.

## Deuda flotante de Neuquén

El archivo fuente contiene componentes, una fila `Total Deuda Flotante` y una obligación separada por haberes y cargas sociales. La consolidación usa el total publicado como control, muestra únicamente los componentes que lo integran y excluye haberes y cargas sociales. Así evita sumar nuevamente el total y duplicar el stock.

Santa Fe no cuenta por ahora con una serie separada de deuda flotante. El indicador deuda más deuda flotante permanece como `s/d`.

## Controles

El actualizador verifica conflictos de duplicación fiscal, conciliación del stock por categorías, conciliación de deuda flotante, cobertura del último trimestre y huellas SHA-256 de todas las fuentes. Los valores faltantes permanecen nulos y el dashboard los muestra como `s/d`.
