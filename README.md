# Finanzas Provinciales

Monitor fiscal estático de Santa Fe y Neuquén. La versión activa utiliza copias congeladas de las bases provinciales y no vuelve a leer las carpetas de trabajo de cada jurisdicción.

## Abrir el dashboard

Abrir `index.html` con Chrome, Edge o Firefox. La página funciona offline porque Chart.js y `data/dashboard_data.js` están incluidos localmente.

## Reconstruir esta versión

Ejecutar `actualizar_datos.bat`. El proceso lee la versión congelada indicada en `config/provincias.json` y regenera:

- `data/base_consolidada.sqlite`: base común con indicadores, flujos nominales y reales, tendencias mensuales y deuda/liquidez.
- `data/dashboard_data.json`: salida estructurada para futuras integraciones.
- `data/dashboard_data.js`: datos consumidos por el HTML offline.
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

Para GitHub Pages alcanza con publicar los archivos del dashboard, `vendor/` y `data/dashboard_data.js`. Las fuentes congeladas, las SQLite y el historial de versiones no son necesarios para que funcione la página y están excluidos mediante `.gitignore`.
