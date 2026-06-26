# Changelog - Inversiones ETF

## [1.2.0] - 2026-06-26

### Cambiado
- **Refactor del sistema de gráficos**: La pestaña "Rendimiento" ha sido eliminada. Ahora las únicas gráficas disponibles son las de evolución del portafolio y P&L acumulado en la pestaña "Historial".
- **Gráfico interactivo**: El gráfico del Historial ahora usa `FigureCanvasTkAgg` (matplotlib embebido) con toolbar interactivo (zoom, pan, autoscale) en lugar de imágenes PNG estáticas.
- **Cálculo de P&L Diario corregido**: `daily_pnl` ahora se calcula como la diferencia del `cumulative_pnl` entre snapshots consecutivos. Esto asegura que el P&L diario sea coherente incluso cuando hay aportaciones o retiradas de capital entre snapshots.
- **Bugfix CLI**: Corregido el formateo de color en el comando `snapshot` de la CLI.

---

## [1.1.0] - 2026-06-26

### Añadido
- **Daily Snapshots**: Nuevo sistema de captura diaria automática del valor del portafolio.
  - Nueva tabla `daily_snapshots` en la base de datos.
  - `snapshot.py`: script para ejecutar una vez al día (vía Task Scheduler) que calcula y almacena el valor total del portafolio, el profit diario y el profit acumulado.
  - Comando CLI `snapshot` para captura manual.
  - Comando CLI `snapshot history` para ver el historial de snapshots.
  - Nueva pestaña "Historial" en la GUI con gráfico de evolución del portafolio y tabla de snapshots.
  - Script `programar_snapshot.bat` para programar la tarea diaria en Windows Task Scheduler.
- **docs/**: carpeta con documentación de cambios.

---

## [1.0.0] - Versión inicial

### Funcionalidades originales
- Registro de transacciones (compra/venta) de fondos de inversión por ISIN.
- Obtención automática de nombre, ticker, moneda y NAV desde Financial Times.
- Conversión a EUR con tipo de cambio en tiempo real.
- Visualización del portafolio con valor actual, ganancia/pérdida y rentabilidad.
- Cálculo de rendimientos históricos (30d, 90d, 180d, 1y).
- Generación de histogramas de retornos diarios y gráficos P&L.
- Interfaz gráfica con customtkinter.
- Interfaz CLI con Click.
