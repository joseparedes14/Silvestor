import click
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box

from database import (
    init_db, agregar_transaccion, listar_transacciones, eliminar_transaccion,
    obtener_portfolio, obtener_snapshots,
)
from fondos import (
    obtener_info_fondo, obtener_precio_actual, obtener_portfolio_completo,
    obtener_datos_historicos, generar_histograma, generar_reporte_rendimiento, calcular_rendimientos,
    obtener_tipo_cambio, convertir_a_eur, limpiar_cache_tipo_cambio
)
from snapshot import tomar_snapshot

console = Console()


def _formatear_moneda(valor, moneda="EUR") -> str:
    if valor is None:
        return f"---"
    simbolos = {"EUR": "€", "USD": "$", "MXN": "MX$"}
    simbolo = simbolos.get(moneda, moneda + " ")
    return f"{simbolo}{valor:,.2f}"


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

    tc = obtener_tipo_cambio()
    table = Table(box=box.SIMPLE, title="Historial de Transacciones (EUR)")
    table.add_column("ID", style="cyan")
    table.add_column("Fecha", style="white")
    table.add_column("ISIN")
    table.add_column("Nombre")
    table.add_column("Tipo")
    table.add_column("Particip.", justify="right")
    table.add_column("Precio", justify="right")
    table.add_column("Total", justify="right")

    for t in transacciones:
        moneda = t.get("moneda", "USD")
        color_tipo = "green" if t["tipo"] == "compra" else "red"
        table.add_row(
            str(t["id"]),
            t["fecha"],
            t["isin"],
            t["nombre"][:30],
            f"[{color_tipo}]{t['tipo']}[/{color_tipo}]",
            str(t["participaciones"]),
            _formatear_moneda(convertir_a_eur(t["precio"], moneda, tc)),
            _formatear_moneda(convertir_a_eur(t["total"], moneda, tc)),
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

    tipo_cambio = None
    if actualizar:
        with console.status("[bold green]Obteniendo tipo de cambio EUR/USD..."):
            tipo_cambio = obtener_tipo_cambio()

    def _eur(valor, moneda):
        if moneda == "EUR":
            return valor
        if tipo_cambio is None:
            return valor
        return round(valor / tipo_cambio, 2) if valor is not None else None

    table = Table(box=box.SIMPLE, title="Portafolio de Fondos (EUR)")
    table.add_column("ISIN", style="cyan")
    table.add_column("Nombre")
    table.add_column("Particip.", justify="right")
    table.add_column("P. Prom.", justify="right")
    table.add_column("NAV Actual", justify="right")
    table.add_column("Invertido", justify="right")
    table.add_column("Valor Actual", justify="right")
    table.add_column("Ganancia", justify="right")
    table.add_column("Rent.", justify="right")

    total_invertido_eur = 0
    total_valor_eur = 0

    for pos in posiciones:
        moneda = pos.get("moneda", "USD")
        p_prom_eur = _eur(pos["precio_promedio"], moneda)
        p_act_eur = _eur(pos["precio_actual"], moneda)
        inv_eur = _eur(pos["total_invertido"], moneda)
        val_eur = _eur(pos["valor_actual"], moneda)
        gan_eur = _eur(pos["ganancia"], moneda)

        total_invertido_eur += inv_eur if inv_eur is not None else 0
        if val_eur is not None:
            total_valor_eur += val_eur

        gan_str = _formatear_moneda(gan_eur) if gan_eur is not None else "---"
        gan_pct = f"{pos['ganancia_pct']:+.2f}%" if pos['ganancia_pct'] is not None else "---"

        table.add_row(
            pos["isin"],
            pos.get("nombre", "")[:25],
            f"{pos['participaciones']:.4f}",
            _formatear_moneda(p_prom_eur),
            _formatear_moneda(p_act_eur),
            _formatear_moneda(inv_eur),
            _formatear_moneda(val_eur),
            f"[{_color_ganancia(gan_eur)}]{gan_str}[/{_color_ganancia(gan_eur)}]",
            f"[{_color_ganancia(pos['ganancia_pct'])}]{gan_pct}[/{_color_ganancia(pos['ganancia_pct'])}]",
        )

    console.print(table)

    if actualizar and total_valor_eur > 0:
        gan_total_eur = round(total_valor_eur - total_invertido_eur, 2)
        gan_pct_total = (gan_total_eur / total_invertido_eur) * 100 if total_invertido_eur else 0

        summary = Table(box=box.SIMPLE, show_header=False)
        summary.add_column("Métrica")
        summary.add_column("Valor", justify="right")
        summary.add_row("Total Invertido", _formatear_moneda(total_invertido_eur))
        summary.add_row("Valor Actual", _formatear_moneda(total_valor_eur))
        summary.add_row(
            "Ganancia/Pérdida Total",
            f"[{_color_ganancia(gan_total_eur)}]{_formatear_moneda(gan_total_eur)} ({gan_pct_total:+.2f}%)[/{_color_ganancia(gan_total_eur)}]",
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
        tc = obtener_tipo_cambio()
        nav_eur = convertir_a_eur(nav, tipo_cambio=tc)
        console.print(f"[green]{identificador.upper()}[/green]: {_formatear_moneda(nav_eur)}")


@cli.command()
def resumen():
    """Mostrar un resumen rápido del portafolio."""
    items = obtener_portfolio()
    if not items:
        console.print("[yellow]No hay posiciones activas.[/yellow]")
        return

    total_participaciones = sum(i["total_participaciones"] for i in items)
    total_invertido_usd = sum(i["total_invertido"] for i in items)
    tipo_cambio = obtener_tipo_cambio()
    total_invertido_eur = convertir_a_eur(total_invertido_usd) if tipo_cambio else total_invertido_usd

    console.print(f"[bold]Posiciones activas:[/bold] {len(items)}")
    console.print(f"[bold]Total participaciones:[/bold] {total_participaciones:.4f}")
    console.print(f"[bold]Total invertido:[/bold] {_formatear_moneda(total_invertido_eur)}")


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
@click.option("--fecha", "-f", default=None, help="Fecha (YYYY-MM-DD). Por defecto: hoy")
def snapshot(fecha):
    """Tomar un snapshot diario del valor del portafolio."""
    with console.status("[bold green]Calculando valor del portafolio..."):
        resultado = tomar_snapshot(fecha)
    dpnl_str = f"{resultado['daily_pnl']:+.2f}" if resultado['daily_pnl'] is not None else "N/A"
    console.print(f"[green]Snapshot {resultado['fecha']}[/green]")
    console.print(f"  Invertido:    [cyan]EUR {resultado['total_invertido']:,.2f}[/cyan]")
    console.print(f"  Valor actual: [cyan]EUR {resultado['total_valor']:,.2f}[/cyan]")
    pnl_color = _color_ganancia(resultado['cumulative_pnl'])
    console.print(f"  P&L Diario:   EUR {dpnl_str}")
    cum_str = f"EUR {resultado['cumulative_pnl']:+,.2f}"
    console.print(f"  P&L Acum.:    [{pnl_color}]{cum_str}[/{pnl_color}]")


@cli.command()
@click.option("--limite", "-l", type=int, default=None, help="Numero de snapshots a mostrar")
def snapshot_history(limite):
    """Ver historial de snapshots diarios."""
    snapshots = obtener_snapshots(limite)
    if not snapshots:
        console.print("[yellow]No hay snapshots registrados. Usa 'snapshot' para tomar uno.[/yellow]")
        return
    table = Table(box=box.SIMPLE, title="Historial de Snapshots Diarios (EUR)")
    table.add_column("Fecha", style="cyan")
    table.add_column("Invertido", justify="right")
    table.add_column("Valor", justify="right")
    table.add_column("P&L Diario", justify="right")
    table.add_column("P&L Acum.", justify="right")
    for s in snapshots:
        dpnl = f"{s['daily_pnl']:+.2f}" if s['daily_pnl'] is not None else "---"
        table.add_row(
            s["fecha"],
            _formatear_moneda(s["total_invertido"]),
            _formatear_moneda(s["total_valor"]),
            f"[{_color_ganancia(s['daily_pnl'])}]{dpnl}[/{_color_ganancia(s['daily_pnl'])}]",
            f"[{_color_ganancia(s['cumulative_pnl'])}]{_formatear_moneda(s['cumulative_pnl'])}[/{_color_ganancia(s['cumulative_pnl'])}]",
        )
    console.print(table)


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
        try:
            os.startfile(archivo)
            console.print("[blue]Abriendo imagen con el visor predeterminado...[/blue]")
        except Exception:
            pass
    else:
        console.print("[red]No se pudo generar el histograma.[/red]")


if __name__ == "__main__":
    cli()
