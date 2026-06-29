# Changelog - Inversiones ETF

## [1.4.0] - 2026-06-29

### Añadido
- **Agrupación por ISIN en tabla de inversiones**: Las transacciones con el mismo ISIN se agrupan bajo una fila principal que muestra la posición consolidada (participaciones netas, total invertido, valor actual y rentabilidad). Cada grupo es expandible/colapsable mediante una flecha en el margen izquierdo.
- **Filas principales en negrita**: La fila resumen de cada ISIN se muestra en negrita para distinguirla visualmente de las transacciones individuales.

### Cambiado
- **Navegación jerárquica**: La tabla "Inversiones" usa ahora el modo árbol (`Treeview` con `show="tree headings"`), permitiendo expandir/colapsar grupos de transacciones por ISIN.
- **NAV histórico en fila principal**: La columna "NAV en fecha" de la fila de grupo muestra `---` para evitar problemas de márgenes con la ponderación de múltiples compras.
- **Selector individual requerido**: Las operaciones de eliminar y editar solo funcionan sobre transacciones individuales (hijos del grupo), no sobre la fila resumen del ISIN.

## [1.3.0] - 2026-06-28

### Eliminado
- **Detalle de inversión**: Eliminado el panel de detalle con gráfico de evolución que se mostraba al seleccionar una transacción en la pestaña "Inversiones". Ahora la selección de una fila solo la resalta visualmente, sin abrir información adicional.

### Cambiado
- **Snapshots con timestamp**: La tabla `daily_snapshots` ya no tiene restricción UNIQUE en `fecha`, permitiendo múltiples snapshots en un mismo día. El campo `fecha` ahora almacena la fecha y hora (`YYYY-MM-DD HH:MM:SS`) para distinguir snapshots dentro del mismo día.
- **Migración automática**: Los snapshots existentes con solo fecha se convierten automáticamente al nuevo formato añadiendo `00:00:00`.
- **CLI y GUI**: Ajustados los formatos de visualización para mostrar correctamente los timestamps en las tablas y gráficos.

### Añadido
- **Eliminar snapshots**: Nuevo botón "Eliminar Snapshot" en la pestaña "Historial" que permite borrar un snapshot seleccionado de la tabla. También se añadió la función `eliminar_snapshot()` en `database.py`.
- **Editar transacciones**: Doble clic sobre cualquier transacción en la pestaña "Inversiones" abre un diálogo de edición donde se pueden modificar fecha, tipo, participaciones, precio (NAV) y moneda. El total se recalcula automáticamente.

### Cambiado
- **Detección de moneda mejorada**: Ahora `_extraer_moneda()` analiza tanto la tabla de perfil de FT como el nombre del fondo. Si el nombre contiene un código de moneda conocido (EUR, USD, GBP, etc.), este tiene prioridad sobre el valor extraído de la tabla de FT, ya que el nombre es más fiable. Corregido el caso del ISIN IE00B03HCZ61 cuyo precio está en EUR pero FT reportaba "Price currency: GBP".
- **Propagación de moneda en GUI**: Las llamadas a `convertir_a_eur` en los métodos `_agregar_transaccion`, `_task_preview` y `_mostrar_preview` ahora pasan la moneda real del fondo en lugar de asumir USD por defecto. La moneda también se guarda correctamente en la transacción al agregarla desde la GUI.

### Corregido
- **Gráfico interactivo de snapshots**: Se reescribió la generación del gráfico de la pestaña "Historial" para que funcione correctamente. Se corrigieron los siguientes problemas:
  - El `no_data_label` ahora se oculta adecuadamente al mostrar el gráfico (usando `grid_remove` en lugar de dejarlo superpuesto).
  - Se añadió `try/except` con mensaje de error visible si la generación del gráfico falla.
  - Se corrigió la comparación de `fill_between` que usaba comparación lexicográfica de listas en lugar de comparación elemento a elemento.
  - Se añadieron marcadores (`marker="o"`) en las líneas para visualizar puntos individuales de cada snapshot.
  - Se movió `set_xticks`/`set_xticklabels` a cada eje individualmente.

---

## [1.2.1] - 2026-06-26

### Añadido
- **AGENTS.md**: Archivo de instrucciones para el agente que exige registrar todos los cambios en `docs/changelog.md`.

---

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
