import click
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box

from database import init_db, agregar_transaccion, listar_transacciones, eliminar_transaccion, obtener_portfolio
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_portfolio_completo,
    obtener_datos_historicos, generar_histograma, generar_reporte_rendimiento, calcular_rendimientos
)

console = Console()


def _formatear_moneda(valor, moneda="USD") -> str:
    if valor is None:
        return f"{moneda} ---"
    return f"{moneda}{valor:,.2f}"


def _color_ganancia(valor):
    if valor is None:
        return "white"
    if valor > 0:
        return "green"
    if valor < 0:
        return "red"
    return "white"


@click.group()
def cli():
    """Sistema de seguimiento de inversiones en fondos."""
    init_db()


@cli.command()
@click.option("--isin", "-i", prompt="ISIN del fondo", help="ISIN del fondo de inversión")
@click.option("--ticker", "-t", default=None, help="Ticker en FT (opcional, se autocompleta)")
@click.option("--nombre", "-n", default=None, help="Nombre del fondo (opcional, se autocompleta)")
@click.option("--tipo", "-tp", type=click.Choice(["compra", "venta"]), prompt="Tipo", help="Tipo de transacción")
@click.option("--participaciones", "-p", type=float, prompt="Número de participaciones", help="Cantidad de participaciones")
@click.option("--precio", "-pr", type=float, prompt="Precio por participación", help="Precio por participación (NAV)")
@click.option("--fecha", "-f", default=None, help="Fecha (YYYY-MM-DD). Por defecto: hoy")
@click.option("--moneda", "-m", default="USD", help="Moneda (USD, EUR, MXN...)")
def agregar(isin, ticker, nombre, tipo, participaciones, precio, fecha, moneda):
    """Registrar una compra o venta de participaciones."""
    total = round(participaciones * precio, 2)
    isin = isin.upper().strip()
    if nombre is None or ticker is None:
        info = obtener_info_fondo(isin)
        if nombre is None:
            nombre = info.get("nombre") or isin
        if ticker is None and info.get("ticker"):
            ticker = info.get("ticker")
        moneda = info.get("moneda") or moneda

    trans_id = agregar_transaccion(isin, nombre, tipo, participaciones, precio, total, fecha, moneda, ticker or "")
    console.print(f"[green]OK[/green] Transaccion #{trans_id} registrada: {tipo} de {participaciones} {isin} a {_formatear_moneda(precio, moneda)}")


@cli.command()
@click.option("--isin", "-i", default=None, help="Filtrar por ISIN")
def historial(isin):
    """Ver el historial de transacciones."""
    transacciones = listar_transacciones(isin)
    if not transacciones:
        console.print("[yellow]No hay transacciones registradas.[/yellow]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan")
    table.add_column("Fecha", style="white")
    table.add_column("ISIN")
    table.add_column("Nombre")
    table.add_column("Tipo")
    table.add_column("Particip.", justify="right")
    table.add_column("Precio", justify="right")
    table.add_column("Total", justify="right")

    for t in transacciones:
        color_tipo = "green" if t["tipo"] == "compra" else "red"
        table.add_row(
            str(t["id"]),
            t["fecha"],
            t["isin"],
            t["nombre"][:30],
            f"[{color_tipo}]{t['tipo']}[/{color_tipo}]",
            str(t["participaciones"]),
            _formatear_moneda(t["precio"], t["moneda"]),
            _formatear_moneda(t["total"], t["moneda"]),
        )

    console.print(table)


@cli.command()
@click.argument("transaccion_id", type=int)
def eliminar(transaccion_id):
    """Eliminar una transacción por su ID."""
    if eliminar_transaccion(transaccion_id):
        console.print(f"[green]OK[/green] Transaccion #{transaccion_id} eliminada.")
    else:
        console.print(f"[red]X[/red] No se encontro la transaccion #{transaccion_id}.")


@cli.command()
@click.option("--actualizar/--no-actualizar", default=True, help="Obtener precios en tiempo real")
def portfolio(actualizar):
    """Mostrar el portafolio actual con valor en tiempo real."""
    items = obtener_portfolio()
    if not items:
        console.print("[yellow]No hay posiciones abiertas. Agrega transacciones con 'agregar'.[/yellow]")
        return

    if actualizar:
        with console.status("[bold green]Obteniendo precios desde Financial Times..."):
            posiciones = obtener_portfolio_completo(items)
    else:
        posiciones = [
            {
                "isin": p["isin"],
                "nombre": p["nombre"],
                "participaciones": p["total_participaciones"],
                "precio_actual": None,
                "valor_actual": None,
                "total_invertido": p["total_invertido"],
                "ganancia": None,
                "ganancia_pct": None,
                "precio_promedio": round(p["total_invertido"] / p["total_participaciones"], 4),
                "moneda": p["moneda"],
            }
            for p in items
        ]

    table = Table(box=box.SIMPLE, title="Portafolio de Fondos")
    table.add_column("ISIN", style="cyan")
    table.add_column("Nombre")
    table.add_column("Particip.", justify="right")
    table.add_column("P. Prom.", justify="right")
    table.add_column("NAV Actual", justify="right")
    table.add_column("Invertido", justify="right")
    table.add_column("Valor Actual", justify="right")
    table.add_column("Ganancia", justify="right")
    table.add_column("Rent.", justify="right")

    total_invertido = 0
    total_valor = 0

    for pos in posiciones:
        p_prom = _formatear_moneda(pos["precio_promedio"])
        p_act = _formatear_moneda(pos["precio_actual"])
        inv = _formatear_moneda(pos["total_invertido"])
        val = _formatear_moneda(pos["valor_actual"])
        gan = pos["ganancia"]
        gan_str = _formatear_moneda(gan) if gan is not None else "---"
        gan_pct = f"{pos['ganancia_pct']:+.2f}%" if pos['ganancia_pct'] is not None else "---"

        total_invertido += pos["total_invertido"]
        if pos["valor_actual"] is not None:
            total_valor += pos["valor_actual"]

        table.add_row(
            pos["isin"],
            pos.get("nombre", "")[:25],
            f"{pos['participaciones']:.4f}",
            p_prom,
            p_act,
            inv,
            val,
            f"[{_color_ganancia(gan)}]{gan_str}[/{_color_ganancia(gan)}]",
            f"[{_color_ganancia(pos['ganancia_pct'])}]{gan_pct}[/{_color_ganancia(pos['ganancia_pct'])}]",
        )

    console.print(table)

    if actualizar and total_valor > 0:
        gan_total = total_valor - total_invertido
        gan_pct_total = (gan_total / total_invertido) * 100 if total_invertido else 0

        summary = Table(box=box.SIMPLE, show_header=False)
        summary.add_column("Métrica")
        summary.add_column("Valor", justify="right")
        summary.add_row("Total Invertido", _formatear_moneda(total_invertido))
        summary.add_row("Valor Actual", _formatear_moneda(total_valor))
        summary.add_row(
            "Ganancia/Pérdida",
            f"[{_color_ganancia(gan_total)}]{_formatear_moneda(gan_total)} ({gan_pct_total:+.2f}%)[/{_color_ganancia(gan_total)}]",
        )
        console.print(summary)


@cli.command()
@click.argument("identificador")
def precio(identificador):
    """Consultar el NAV actual de un fondo por ISIN o ticker."""
    nav = obtener_precio_actual(identificador.upper())
    if nav is None:
        console.print(f"[red]No se pudo obtener el NAV de {identificador.upper()}[/red]")
    else:
        console.print(f"[green]{identificador.upper()}[/green]: {_formatear_moneda(nav)}")


@cli.command()
def resumen():
    """Mostrar un resumen rápido del portafolio."""
    items = obtener_portfolio()
    if not items:
        console.print("[yellow]No hay posiciones activas.[/yellow]")
        return

    total_participaciones = sum(i["total_participaciones"] for i in items)
    total_invertido = sum(i["total_invertido"] for i in items)

    console.print(f"[bold]Posiciones activas:[/bold] {len(items)}")
    console.print(f"[bold]Total participaciones:[/bold] {total_participaciones:.4f}")
    console.print(f"[bold]Total invertido:[/bold] {_formatear_moneda(total_invertido)}")


@cli.command()
@click.argument("identificador")
@click.option("--ticker", "-t", default=None, help="Ticker en FT (opcional)")
def rendimiento(identificador, ticker):
    """Ver rendimiento histórico de un fondo por ISIN."""
    with console.status("[bold green]Obteniendo datos históricos desde FT..."):
        df = obtener_datos_historicos(identificador, ticker)
    if df is None or df.empty:
        console.print("[red]No se pudieron obtener datos históricos.[/red]")
        return
    reporte = generar_reporte_rendimiento(df)
    console.print(reporte)


@cli.command()
@click.argument("identificador")
@click.option("--ticker", "-t", default=None, help="Ticker en FT (opcional)")
def histograma(identificador, ticker):
    """Generar histograma de retornos diarios de un fondo."""
    with console.status("[bold green]Obteniendo datos históricos desde FT..."):
        df = obtener_datos_historicos(identificador, ticker)
    if df is None or df.empty:
        console.print("[red]No se pudieron obtener datos históricos.[/red]")
        return
    info = obtener_info_fondo(identificador)
    nombre = info.get("nombre", identificador)
    archivo = generar_histograma(df, identificador, nombre)
    if archivo:
        console.print(f"[green]Histograma generado:[/green] {archivo}")
    else:
        console.print("[red]No se pudo generar el histograma.[/red]")


if __name__ == "__main__":
    cli()
