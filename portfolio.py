import yfinance as yf
from datetime import datetime
from typing import Optional


def obtener_precio_actual(symbol: str) -> Optional[float]:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if data.empty:
            data = ticker.history(period="5d")
        if data.empty:
            return None
        return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        return None


def obtener_info_etf(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "nombre": info.get("longName", info.get("shortName", symbol)),
            "moneda": info.get("currency", "USD"),
            "precio_actual": info.get("currentPrice") or info.get("regularMarketPrice"),
            "cambio_pct": info.get("regularMarketChangePercent"),
        }
    except Exception:
        return {"nombre": symbol, "moneda": "USD", "precio_actual": None, "cambio_pct": None}


def calcular_posicion(symbol: str, acciones: float, total_invertido: float):
    precio_actual = obtener_precio_actual(symbol)
    if precio_actual is None:
        return {
            "symbol": symbol,
            "acciones": acciones,
            "precio_actual": None,
            "valor_actual": None,
            "total_invertido": total_invertido,
            "ganancia": None,
            "ganancia_pct": None,
            "precio_promedio": round(total_invertido / acciones, 2) if acciones else 0,
        }
    valor_actual = round(acciones * precio_actual, 2)
    ganancia = round(valor_actual - total_invertido, 2)
    ganancia_pct = round((ganancia / total_invertido) * 100, 2) if total_invertido else 0
    precio_promedio = round(total_invertido / acciones, 2) if acciones else 0
    return {
        "symbol": symbol,
        "acciones": acciones,
        "precio_actual": precio_actual,
        "valor_actual": valor_actual,
        "total_invertido": total_invertido,
        "ganancia": ganancia,
        "ganancia_pct": ganancia_pct,
        "precio_promedio": precio_promedio,
    }


def obtener_portfolio_completo(items: list[dict]) -> list[dict]:
    resultados = []
    for item in items:
        pos = calcular_posicion(
            item["symbol"],
            item["total_acciones"],
            item["total_invertido"],
        )
        pos["nombre"] = item["nombre"]
        resultados.append(pos)
    return resultados


def obtener_precios_multiples(symbols: list[str]) -> dict[str, Optional[float]]:
    if not symbols:
        return {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        precios = {}
        for sym in symbols:
            try:
                data = tickers.tickers[sym].history(period="1d")
                if not data.empty:
                    precios[sym] = round(float(data["Close"].iloc[-1]), 2)
                else:
                    precios[sym] = None
            except Exception:
                precios[sym] = None
        return precios
    except Exception:
        return {s: None for s in symbols}
