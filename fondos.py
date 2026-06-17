import re
import json
import requests
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io
import os

FT_BASE = "https://markets.ft.com/data/funds/tearsheet"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}
_AJAX_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/html, */*",
    "Referer": "https://markets.ft.com/data/funds/tearsheet/charts",
}
HIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "histograms")


def _extraer_precio(soup: BeautifulSoup) -> Optional[float]:
    quote = soup.select_one(".mod-tearsheet-overview__quote")
    if not quote:
        return None
    values = quote.select(".mod-ui-data-list__value")
    if values:
        texto = values[0].get_text(strip=True)
        try:
            return float(texto)
        except ValueError:
            pass
    return None


def _extraer_cambio(soup: BeautifulSoup) -> Optional[dict]:
    quote = soup.select_one(".mod-tearsheet-overview__quote")
    if not quote:
        return None
    values = quote.select(".mod-ui-data-list__value")
    if len(values) >= 2:
        texto = values[1].get_text(strip=True)
        m = re.search(r"([+-]?\d+\.?\d*)\s*/\s*([+-]?\d+\.?\d*)%", texto)
        if m:
            return {"cambio": float(m.group(1)), "cambio_pct": float(m.group(2))}
    return None


def _extraer_cambio_1y(soup: BeautifulSoup) -> Optional[float]:
    quote = soup.select_one(".mod-tearsheet-overview__quote")
    if not quote:
        return None
    values = quote.select(".mod-ui-data-list__value")
    if len(values) >= 3:
        texto = values[2].get_text(strip=True)
        m = re.search(r"([+-]?\d+\.?\d*)%", texto)
        if m:
            return float(m.group(1))
    return None


def _extraer_nombre(soup: BeautifulSoup) -> str:
    h1 = soup.select_one("h1.mod-tearsheet-overview__header__name--large")
    if h1:
        return h1.get_text(strip=True)
    h1_small = soup.select_one("h1.mod-tearsheet-overview__header__name--small")
    if h1_small:
        return h1_small.get_text(strip=True)
    title = soup.select_one("title")
    if title:
        txt = title.get_text(strip=True)
        return txt.split(",")[0].strip()
    return "Desconocido"


def _extraer_ticker(soup: BeautifulSoup) -> Optional[str]:
    sym = soup.select_one(".mod-tearsheet-overview__header__symbol span")
    if sym:
        return sym.get_text(strip=True)
    return None


def _extraer_moneda(soup: BeautifulSoup) -> str:
    table = soup.select_one(".mod-profile-and-investment-app__table--profile")
    if table:
        rows = table.select("tr")
        for row in rows:
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td and "currency" in th.get_text(strip=True).lower():
                return td.get_text(strip=True)
    return "USD"


def _extraer_datos_tabla(soup: BeautifulSoup) -> Optional[pd.DataFrame]:
    table = soup.select_one("table.mod-tearsheet-historical-prices__results")
    if not table:
        return None
    rows = table.select("tbody tr")
    data = []
    for row in rows:
        cols = row.select("td")
        if len(cols) >= 5:
            span = cols[0].select_one("span.mod-ui-hide-small-below")
            if span:
                fecha_texto = span.get_text(strip=True)
            else:
                fecha_texto = cols[0].get_text(strip=True).split("  ")[0]
            try:
                from dateutil import parser as dtparser
                fecha = dtparser.parse(fecha_texto, fuzzy=False)
            except Exception:
                continue
            try:
                close = float(cols[4].get_text(strip=True))
                data.append({"fecha": fecha, "close": close})
            except ValueError:
                continue
    if not data:
        return None
    df = pd.DataFrame(data)
    df = df.sort_values("fecha").reset_index(drop=True)
    return df


def _obtener_datos_mensuales(ticker: str) -> Optional[pd.DataFrame]:
    try:
        resp = requests.get(
            "https://markets.ft.com/data/funds/ajax/growth-10k-app",
            params={"symbol": ticker},
            headers=_AJAX_HEADERS, timeout=15
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        configs = re.findall(r'data-mod-config="([^"]+)"', body.get("html", ""))
        for c in configs:
            decoded = c.replace("&quot;", '"').replace("&amp;", "&")
            config = json.loads(decoded)
            fund_data = config.get("chartData", {}).get("fund", [])
            if fund_data:
                records = []
                for item in fund_data:
                    records.append({
                        "fecha": pd.Timestamp(item["date"][:10]),
                        "growth": item["value"],
                    })
                df = pd.DataFrame(records)
                return df.sort_values("fecha").reset_index(drop=True)
        return None
    except Exception:
        return None


def buscar_en_ft(query: str) -> Optional[str]:
    url = f"{FT_BASE.rsplit('/', 2)[0]}/search?query={query}&assetClass=Fund"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href*='/data/funds/tearsheet/']")
        for link in links:
            href = link.get("href", "")
            m = re.search(r"[?&]s=([A-Za-z0-9]+)", href)
            if m:
                return m.group(1)
        return None
    except Exception:
        return None


def _es_isin(texto: str) -> bool:
    return bool(re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", texto))


def _es_ticker(texto: str) -> bool:
    return bool(re.match(r"^[A-Z]{1,5}$", texto))


def obtener_info_fondo(identificador: str) -> dict:
    raw = identificador.upper().strip()
    ticker = raw
    if _es_isin(raw):
        buscado = buscar_en_ft(raw)
        if buscado:
            ticker = buscado
    elif not _es_ticker(raw):
        buscado = buscar_en_ft(raw)
        if buscado:
            ticker = buscado
    url = f"{FT_BASE}/summary?s={ticker}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"isin": identificador, "ticker": ticker, "nombre": identificador, "moneda": "USD", "precio_actual": None}
        soup = BeautifulSoup(resp.text, "html.parser")
        nombre = _extraer_nombre(soup)
        moneda = _extraer_moneda(soup)
        precio = _extraer_precio(soup)
        cambio = _extraer_cambio(soup)
        cambio_1y = _extraer_cambio_1y(soup)
        return {
            "isin": identificador,
            "ticker": ticker,
            "nombre": nombre,
            "moneda": moneda,
            "precio_actual": precio,
            "cambio_diario": cambio["cambio"] if cambio else None,
            "cambio_diario_pct": cambio["cambio_pct"] if cambio else None,
            "cambio_1y": cambio_1y,
        }
    except Exception:
        return {"isin": identificador, "ticker": ticker, "nombre": identificador, "moneda": "USD", "precio_actual": None}


def _resolver_ticker(identificador: str, ticker: Optional[str] = None) -> str:
    if ticker:
        return ticker.upper().strip()
    raw = identificador.upper().strip()
    if _es_ticker(raw):
        return raw
    info = obtener_info_fondo(identificador)
    return info.get("ticker", raw)


def obtener_precio_actual(identificador: str, ticker: Optional[str] = None) -> Optional[float]:
    t = _resolver_ticker(identificador, ticker)
    url = f"{FT_BASE}/summary?s={t}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        return _extraer_precio(soup)
    except Exception:
        return None


def obtener_datos_historicos(identificador: str, ticker: Optional[str] = None) -> Optional[pd.DataFrame]:
    t = _resolver_ticker(identificador, ticker)
    url = f"{FT_BASE}/historical?s={t}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        return _extraer_datos_tabla(soup)
    except Exception:
        return None


def _buscar_nav_en_df(df: pd.DataFrame, fecha: str, col_precio: str = "close") -> Optional[float]:
    target = pd.Timestamp(fecha)
    mascara = df[col_precio].notna() & (df["fecha"] <= target)
    if not mascara.any():
        return None
    idx = df.loc[mascara, "fecha"].idxmax()
    return float(df.loc[idx, col_precio])


def obtener_precio_historico_en_fecha(
    identificador: str, fecha: str, ticker: Optional[str] = None
) -> Optional[float]:
    t = _resolver_ticker(identificador, ticker)
    # Try daily data first (last ~1 month)
    df_diario = obtener_datos_historicos(identificador, ticker)
    nav = _buscar_nav_en_df(df_diario, fecha) if df_diario is not None else None
    if nav is not None:
        return nav
    # Fall back to monthly growth data (5 years)
    df_mensual = _obtener_datos_mensuales(t)
    if df_mensual is None or df_mensual.empty:
        return nav
    # Convert growth values to NAV using current NAV as reference
    nav_actual = obtener_precio_actual(identificador, ticker)
    if nav_actual is None or not df_mensual["growth"].notna().any():
        return _buscar_nav_en_df(df_mensual, fecha, "growth")
    ultimo_growth = float(df_mensual["growth"].iloc[-1])
    if ultimo_growth <= 0:
        return None
    df_mensual["nav"] = df_mensual["growth"] * (nav_actual / ultimo_growth)
    nav = _buscar_nav_en_df(df_mensual, fecha, "nav")
    return nav


def calcular_rendimientos(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    rendimientos = {}
    precios = df["close"].values
    fechas = df["fecha"].values
    if len(precios) >= 2:
        rend_pct = (precios[-1] / precios[0] - 1) * 100
        rendimientos["total_periodo"] = round(rend_pct, 2)
    if len(precios) >= 2:
        retornos_diarios = np.diff(precios) / precios[:-1] * 100
        rendimientos["retorno_diario_promedio"] = round(float(np.mean(retornos_diarios)), 4)
        rendimientos["volatilidad_diaria"] = round(float(np.std(retornos_diarios)), 4)
    ultimos_30 = min(30, len(precios))
    if ultimos_30 >= 2:
        r30 = (precios[-1] / precios[-ultimos_30] - 1) * 100
        rendimientos["retorno_30d"] = round(r30, 2)
    ultimos_90 = min(90, len(precios))
    if ultimos_90 >= 2:
        r90 = (precios[-1] / precios[-ultimos_90] - 1) * 100
        rendimientos["retorno_90d"] = round(r90, 2)
    ultimos_180 = min(180, len(precios))
    if ultimos_180 >= 2:
        r180 = (precios[-1] / precios[-ultimos_180] - 1) * 100
        rendimientos["retorno_180d"] = round(r180, 2)
    ultimos_365 = min(365, len(precios))
    if ultimos_365 >= 2:
        r365 = (precios[-1] / precios[-ultimos_365] - 1) * 100
        rendimientos["retorno_1y"] = round(r365, 2)
    maximo = float(np.max(precios))
    minimo = float(np.min(precios))
    rendimientos["maximo"] = round(maximo, 2)
    rendimientos["minimo"] = round(minimo, 2)
    rendimientos["actual"] = round(float(precios[-1]), 2)
    rendimientos["desde_maximo"] = round((precios[-1] / maximo - 1) * 100, 2)
    rendimientos["fecha_inicio"] = str(fechas[0])[:10]
    rendimientos["fecha_fin"] = str(fechas[-1])[:10]
    return rendimientos


def generar_histograma(df: pd.DataFrame, identificador: str, nombre: str = "") -> Optional[str]:
    if df is None or df.empty or len(df) < 5:
        return None
    os.makedirs(HIST_DIR, exist_ok=True)
    retornos = df["close"].pct_change().dropna() * 100
    if retornos.empty:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(retornos, bins=40, edgecolor="white", color="#2e7d32", alpha=0.8)
    media = retornos.mean()
    mediana = retornos.median()
    desv = retornos.std()
    ax.axvline(media, color="red", linestyle="dashed", linewidth=1.5, label=f"Media: {media:.3f}%")
    ax.axvline(mediana, color="orange", linestyle="dashed", linewidth=1.5, label=f"Mediana: {mediana:.3f}%")
    ax.axvline(media + desv, color="gray", linestyle="dotted", linewidth=1, alpha=0.7)
    ax.axvline(media - desv, color="gray", linestyle="dotted", linewidth=1, alpha=0.7)
    ax.set_xlabel("Retorno Diario (%)", fontsize=11)
    ax.set_ylabel("Frecuencia", fontsize=11)
    titulo = f"Distribución de Retornos Diarios - {nombre or identificador}"
    ax.set_title(titulo, fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    filename = f"hist_{identificador.replace(':', '_').replace('.', '_')}.png"
    filepath = os.path.join(HIST_DIR, filename)
    plt.savefig(filepath, dpi=120)
    plt.close(fig)
    return filepath


def generar_reporte_rendimiento(df: pd.DataFrame) -> str:
    rends = calcular_rendimientos(df)
    if not rends:
        return "No hay datos suficientes para calcular rendimientos."
    lines = []
    lines.append(f"Periodo: {rends.get('fecha_inicio', '?')} -> {rends.get('fecha_fin', '?')}")
    lines.append(f"Precio actual: {rends.get('actual', '?')}")
    lines.append(f"Máximo: {rends.get('maximo', '?')}  |  Mínimo: {rends.get('minimo', '?')}")
    lines.append(f"Retorno total del período: {rends.get('total_periodo', '?')}%")
    lines.append(f"Retorno 30 días: {rends.get('retorno_30d', 'N/A')}%")
    lines.append(f"Retorno 90 días: {rends.get('retorno_90d', 'N/A')}%")
    lines.append(f"Retorno 180 días: {rends.get('retorno_180d', 'N/A')}%")
    lines.append(f"Retorno 1 año: {rends.get('retorno_1y', 'N/A')}%")
    lines.append(f"Retorno diario promedio: {rends.get('retorno_diario_promedio', '?')}%")
    lines.append(f"Volatilidad diaria: {rends.get('volatilidad_diaria', '?')}%")
    lines.append(f"Distancia desde maximo: {rends.get('desde_maximo', '?')}%")
    return "\n".join(lines)


def calcular_posicion(identificador: str, participaciones: float, total_invertido: float, ticker: Optional[str] = None):
    info = obtener_info_fondo(identificador) if not ticker else obtener_info_fondo(ticker)
    precio_actual = info.get("precio_actual") or obtener_precio_actual(identificador, ticker)
    if precio_actual is None:
        return {
            "isin": identificador,
            "ticker": info.get("ticker", ""),
            "nombre": info.get("nombre", identificador),
            "participaciones": participaciones,
            "precio_actual": None,
            "valor_actual": None,
            "total_invertido": total_invertido,
            "ganancia": None,
            "ganancia_pct": None,
            "precio_promedio": round(total_invertido / participaciones, 4) if participaciones else 0,
            "moneda": info.get("moneda", "USD"),
        }
    valor_actual = round(participaciones * precio_actual, 2)
    ganancia = round(valor_actual - total_invertido, 2)
    ganancia_pct = round((ganancia / total_invertido) * 100, 2) if total_invertido else 0
    precio_promedio = round(total_invertido / participaciones, 4) if participaciones else 0
    return {
        "isin": identificador,
        "ticker": info.get("ticker", ""),
        "nombre": info.get("nombre", identificador),
        "participaciones": participaciones,
        "precio_actual": precio_actual,
        "valor_actual": valor_actual,
        "total_invertido": total_invertido,
        "ganancia": ganancia,
        "ganancia_pct": ganancia_pct,
        "precio_promedio": precio_promedio,
        "moneda": info.get("moneda", "USD"),
    }


def generar_histograma_personal(
    df: pd.DataFrame, participaciones: float, total_invertido: float,
    identificador: str, nombre: str = ""
) -> Optional[str]:
    if df is None or df.empty or len(df) < 5:
        return None
    os.makedirs(HIST_DIR, exist_ok=True)
    precios = df["close"].values
    fechas = df["fecha"].values
    valor_posicion = participaciones * precios
    pnl_diario = np.diff(valor_posicion)
    if len(pnl_diario) < 4:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(pnl_diario, bins=40, edgecolor="white", color="#1f77b4", alpha=0.8)
    media = np.mean(pnl_diario)
    mediana = np.median(pnl_diario)
    desv = np.std(pnl_diario)
    ax.axvline(media, color="red", linestyle="dashed", linewidth=1.5,
               label=f"Media: ${media:.2f}")
    ax.axvline(mediana, color="orange", linestyle="dashed", linewidth=1.5,
               label=f"Mediana: ${mediana:.2f}")
    ax.axvline(media + desv, color="gray", linestyle="dotted", linewidth=1, alpha=0.7)
    ax.axvline(media - desv, color="gray", linestyle="dotted", linewidth=1, alpha=0.7)
    ax.set_xlabel("P&L Diario ($)", fontsize=11)
    ax.set_ylabel("Frecuencia", fontsize=11)
    valor_actual = valor_posicion[-1]
    ganancia = valor_actual - total_invertido
    ganancia_pct = (ganancia / total_invertido) * 100 if total_invertido else 0
    titulo = (f"P&L Diario de tu Posicion - {nombre or identificador}\n"
              f"{participaciones:.4f} part. | Invertido: ${total_invertido:,.2f} | "
              f"Actual: ${valor_actual:,.2f} ({ganancia_pct:+.2f}%)")
    ax.set_title(titulo, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    filename = f"pnl_{identificador.replace(':', '_').replace('.', '_')}.png"
    filepath = os.path.join(HIST_DIR, filename)
    plt.savefig(filepath, dpi=120)
    plt.close(fig)
    return filepath


def obtener_portfolio_completo(items: list[dict]) -> list[dict]:
    resultados = []
    for item in items:
        pos = calcular_posicion(
            item["isin"],
            item["total_participaciones"],
            item["total_invertido"],
            item.get("ticker"),
        )
        pos["nombre"] = item.get("nombre") or pos.get("nombre", "")
        resultados.append(pos)
    return resultados
