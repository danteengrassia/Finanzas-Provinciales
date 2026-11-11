# Finanzas Provinciales

Monitor fiscal estático de Santa Fe y Neuquén. La versión activa utiliza copias congeladas de las bases provinciales y no vuelve a leer las carpetas de trabajo de cada jurisdicción.

## Abrir el dashboard

Abrir `index.html` con Chrome, Edge o Firefox. La página funciona offline porque Chart.js y `data/dashboard_data.js` están incluidos localmente.

## Reconstruir esta versión

Los puentes de Mendoza, Córdoba y Entre Ríos se regeneran con
`python scripts/generar_mendoza_puente.py`,
`python scripts/generar_cordoba_puente.py` y
`python scripts/generar_entre_rios_puente.py`. Leen las SQLite provinciales
en modo de solo lectura. Córdoba también usa el CSV auxiliar de deuda flotante
de su carpeta `database`. Cada comando admite `--source` y `--output` para
trabajar con otra extracción. La configuración indica qué puente consume el
consolidador.

Ejecutar `actualizar_datos.bat`. El proceso lee la versión congelada indicada en `config/provincias.json` y regenera:

- `data/base_consolidada.sqlite`: base común con indicadores, flujos nominales y reales, tendencias mensuales y deuda/liquidez.
- `data/economia.js`: series anuales de la pestaña Economía. El actualizador la reconstruye con `scripts/generar_economia.py` desde el archivo `Series_macro/Economia/base_pib_provincias_subtotales_monedas.json` (carpeta hermana de `WEB`) y los cierres de la base consolidada. Para regenerar solo esta pestaña, ejecutar `python scripts/generar_economia.py`; `--pbg` permite indicar otra ubicación del JSON.
- `data/dashboard_data.json`: salida estructurada para futuras integraciones.
- `data/dashboard_data.js`: datos consumidos por el HTML offline.
- `data/detalle/`: jerarquías provinciales para ejecución, stock y servicios. El generador usa las bases provinciales en modo de solo lectura.
- `data/control_calidad.json`: controles y advertencias.
- `data/manifest.json`: rutas, fechas y huellas SHA-256 de las fuentes.
- `data/versiones/<fecha_hora>/`: copia histórica de cada reconstrucción.

La versión activa combina Santa Fe `santa_fe_20260814_213940` con Neuquén `20260814_130319`. Para incorporar nuevas bases provinciales debe crearse otra carpeta de fuentes congeladas y actualizar las rutas de configuración. Esto evita mezclar una extracción en revisión con el dashboard vigente.

## Estructura

- `config/provincias.json`: fuentes activas y equivalencias de cuentas fiscales.
- `scripts/actualizar_datos.py`: normalización, cálculos y generación de salidas.
- `data/macro/`: IPC nacional y depósitos provinciales BCRA normalizados.
- `docs/METODOLOGIA.md`: criterios de cálculo y diferencias entre provincias.
- `index.html`, `styles.css`, `app.js`: dashboard estático.
- `vendor/chart.umd.min.js`: Chart.js 4.5.1 para uso offline.

## Publicación futura

Para GitHub Pages alcanza con publicar los archivos del dashboard, `vendor/`, `data/dashboard_data.js` y `data/detalle/`. Las fuentes congeladas, las SQLite y el historial de versiones no son necesarios para que funcione la página y están excluidos mediante `.gitignore`.
