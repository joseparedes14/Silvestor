# Silvestor - Seguimiento de Inversiones en Fondos/ETF

Aplicación para el registro y seguimiento de inversiones en fondos de inversión y ETFs mediante ISIN. Obtiene precios en tiempo real desde Financial Times y Yahoo Finance, con conversión automática a EUR.

## Características

- **Registro de transacciones**: Compra/venta de participaciones por ISIN
- **Obtención automática de datos**: Nombre, ticker, moneda y NAV desde Financial Times
- **Portafolio en tiempo real**: Valor actual, ganancia/pérdida y rentabilidad global
- **Snapshots diarios**: Captura automatizada del valor del portafolio con P&L diario y acumulado
- **Rendimiento histórico**: Cálculo de rendimientos a 30d, 90d, 180d y 1 año
- **Histogramas**: Distribución de retornos diarios por fondo
- **Conversión a EUR**: Tipo de cambio USD/EUR en tiempo real
- **CLI y GUI**: Interfaz de línea de comandos (Click + Rich) e interfaz gráfica (CustomTkinter)

## Requisitos

- Python 3.10+
- Dependencias listadas en `requirements.txt`

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

### Interfaz gráfica

```bash
python gui.py
```

O ejecutando `iniciar.bat` en Windows.

### Línea de comandos

```bash
# Registrar una compra
python main.py agregar -i IE00B4L5Y983 -t compra -p 100 -pr 150.50

# Ver portafolio
python main.py portfolio

# Ver historial de transacciones
python main.py historial

# Tomar snapshot del portafolio
python main.py snapshot

# Ver rendimiento histórico de un fondo
python main.py rendimiento <ISIN>

# Generar histograma de retornos
python main.py histograma <ISIN>
```

### Snapshots automáticos

Ejecutar `programar_snapshot.bat` como Administrador para programar una tarea diaria en el Programador de Tareas de Windows.

## Estructura del proyecto

```
inversiones-etf/
├── main.py              # CLI con Click
├── gui.py               # Interfaz gráfica con CustomTkinter
├── database.py          # Capa de base de datos SQLite
├── fondos.py            # Obtención de datos de fondos (FT)
├── portfolio.py         # Consulta de precios (Yahoo Finance)
├── snapshot.py          # Captura de snapshots diarios
├── iniciar.bat          # Lanzador de la GUI
├── programar_snapshot.bat # Programador de snapshots
├── requirements.txt     # Dependencias
├── docs/
│   └── changelog.md     # Registro de cambios
└── inversiones.db       # Base de datos SQLite
```

## Licencia

Uso personal.
