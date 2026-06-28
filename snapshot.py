import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import (
    init_db, obtener_portfolio, guardar_snapshot,
    obtener_ultimo_snapshot, obtener_snapshots, obtener_snapshots_asc,
)
from fondos import (
    obtener_precio_actual, obtener_tipo_cambio, convertir_a_eur,
    obtener_info_fondo,
)


def calcular_portfolio_valor() -> dict:
    init_db()
    items = obtener_portfolio()
    if not items:
        return {"total_invertido_eur": 0.0, "total_valor_eur": 0.0}

    tc = obtener_tipo_cambio()

    total_invertido_eur = 0.0
    total_valor_eur = 0.0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = {}
        for item in items:
            isin = item["isin"]
            futuros[executor.submit(obtener_precio_actual, isin)] = item

        for futuro in as_completed(futuros):
            item = futuros[futuro]
            try:
                nav = futuro.result()
            except Exception:
                nav = None

            moneda = item.get("moneda", "USD")
            inv = item["total_invertido"]
            part = item["total_participaciones"]

            inv_eur = convertir_a_eur(inv, moneda, tc) or 0
            total_invertido_eur += inv_eur

            if nav and part:
                val_eur = convertir_a_eur(nav * part, moneda, tc) or 0
                total_valor_eur += val_eur

    return {
        "total_invertido_eur": round(total_invertido_eur, 2),
        "total_valor_eur": round(total_valor_eur, 2),
    }


def tomar_snapshot(fecha: str = None) -> dict:
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif len(fecha) <= 10:
        fecha = fecha + " 00:00:00"

    valores = calcular_portfolio_valor()
    total_invertido = valores["total_invertido_eur"]
    total_valor = valores["total_valor_eur"]

    cumulative_pnl = round(total_valor - total_invertido, 2)

    ultimo = obtener_ultimo_snapshot()
    if ultimo:
        daily_pnl = round(cumulative_pnl - ultimo["cumulative_pnl"], 2)
    else:
        daily_pnl = None

    guardar_snapshot(fecha, total_invertido, total_valor, daily_pnl, cumulative_pnl)

    return {
        "fecha": fecha,
        "total_invertido": total_invertido,
        "total_valor": total_valor,
        "daily_pnl": daily_pnl,
        "cumulative_pnl": cumulative_pnl,
    }


def mostrar_snapshots(limite: int = None):
    snapshots = obtener_snapshots(limite)
    if not snapshots:
        print("No hay snapshots registrados.")
        return

    print(f"{'Fecha':<22} {'Invertido':<14} {'Valor':<14} {'P&L Diario':<14} {'P&L Acum.':<14}")
    print("-" * 78)
    for s in snapshots:
        dpnl = f"{s['daily_pnl']:+.2f}" if s['daily_pnl'] is not None else "N/A"
        print(f"{s['fecha']:<22} {s['total_invertido']:<14,.2f} {s['total_valor']:<14,.2f} "
              f"{dpnl:<14} {s['cumulative_pnl']:<+.2f}")


def main():
    parser = argparse.ArgumentParser(description="Daily portfolio snapshot")
    parser.add_argument("action", nargs="?", default="take",
                        choices=["take", "history"],
                        help="'take' (default) or 'history'")
    parser.add_argument("--fecha", "-f", default=None, help="Fecha YYYY-MM-DD")
    parser.add_argument("--limite", "-l", type=int, default=None, help="Numero de snapshots a mostrar")

    args = parser.parse_args()
    init_db()

    if args.action == "history":
        mostrar_snapshots(args.limite)
    else:
        resultado = tomar_snapshot(args.fecha)
        dpnl_str = f"{resultado['daily_pnl']:+.2f}" if resultado['daily_pnl'] is not None else "N/A"
        print(f"Snapshot {resultado['fecha']}:")
        print(f"  Invertido:    EUR {resultado['total_invertido']:,.2f}")
        print(f"  Valor actual: EUR {resultado['total_valor']:,.2f}")
        print(f"  P&L Diario:   EUR {dpnl_str}")
        print(f"  P&L Acum.:    EUR {resultado['cumulative_pnl']:+,.2f}")


if __name__ == "__main__":
    main()
