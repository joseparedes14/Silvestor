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
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

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

_tipo_cambio_cache = {"rate": None}


def obtener_tipo_cambio(origen: str = "USD", destino: str = "EUR") -> Optional[float]:
    if _tipo_cambio_cache["rate"] is not None:
        return _tipo_cambio_cache["rate"]
    try:
        pair = f"{destino}{origen}=X"
        ticker = yf.Ticker(pair)
        data = ticker.history(period="1d")
        if data.empty:
            data = ticker.history(period="5d")
        if not data.empty:
            _tipo_cambio_cache["rate"] = float(data["Close"].iloc[-1])
            return _tipo_cambio_cache["rate"]
    except Exception:
        pass
    return None


def limpiar_cache_tipo_cambio():
    _tipo_cambio_cache["rate"] = None


def convertir_a_eur(valor, moneda_origen="USD", tipo_cambio=None):
    if valor is None:
        return None
    if moneda_origen == "EUR":
        return round(valor, 2)
    if tipo_cambio is None:
        tipo_cambio = obtener_tipo_cambio()
    if tipo_cambio is None or tipo_cambio == 0:
        return None
    eur = valor / tipo_cambio
    return round(eur, 2)


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


_CURRENCY_FROM_NAME = [
    (r"\bEUR\b", "EUR"),
    (r"\bEuro\b", "EUR"),
    (r"\bUSD\b", "USD"),
    (r"\bUS Dollar\b", "USD"),
    (r"\bGBP\b", "GBP"),
    (r"\bSterling\b", "GBP"),
    (r"\bPound\b", "GBP"),
    (r"\bCHF\b", "CHF"),
    (r"\bJPY\b", "JPY"),
    (r"\bCAD\b", "CAD"),
    (r"\bAUD\b", "AUD"),
    (r"\bSEK\b", "SEK"),
    (r"\bNOK\b", "NOK"),
    (r"\bDKK\b", "DKK"),
    (r"\bPLN\b", "PLN"),
    (r"\bHKD\b", "HKD"),
    (r"\bSGD\b", "SGD"),
]


def _extraer_moneda_desde_nombre(nombre: str) -> Optional[str]:
    for patron, moneda in _CURRENCY_FROM_NAME:
        if re.search(patron, nombre):
            return moneda
    return None


def _extraer_moneda(soup: BeautifulSoup, nombre_fallback: str = "") -> str:
    table = soup.select_one(".mod-profile-and-investment-app__table--profile")
    moneda_scrapeada = None
    if table:
        rows = table.select("tr")
        for row in rows:
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td and "currency" in th.get_text(strip=True).lower():
                moneda_scrapeada = td.get_text(strip=True)
                break
    if nombre_fallback:
        moneda_nombre = _extraer_moneda_desde_nombre(nombre_fallback)
        if moneda_nombre:
            return moneda_nombre
    return moneda_scrapeada or "USD"


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


def _extraer_xid(soup: BeautifulSoup) -> Optional[str]:
    hist_div = soup.select_one('[data-f2-app-id="mod-tearsheet-historical-prices"]')
    if not hist_div:
        return None
    hp_app = hist_div.select_one('[data-module-name="HistoricalPricesApp"]')
    if not hp_app:
        return None
    config_str = hp_app.get("data-mod-config")
    if not config_str:
        return None
    config_str = config_str.replace("&quot;", '"').replace("&amp;", "&")
    try:
        return json.loads(config_str).get("symbol")
    except Exception:
        return None


def _extraer_datos_tabla_ajax(soup: BeautifulSoup) -> Optional[pd.DataFrame]:
    rows = soup.select("tr")
    data = []
    for row in rows:
        cols = row.select("td")
        if len(cols) >= 5:
            span = cols[0].select_one("span.mod-ui-hide-small-below")
            fecha_texto = span.get_text(strip=True) if span else cols[0].get_text(strip=True)
            from dateutil import parser as dtparser
            try:
                fecha = dtparser.parse(fecha_texto)
            except Exception:
                continue
            try:
                close = float(cols[4].get_text(strip=True))
                data.append({"fecha": fecha, "close": close})
            except ValueError:
                continue
    if not data:
        return None
    return pd.DataFrame(data).sort_values("fecha").reset_index(drop=True)


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


def _obtener_datos_historicos_ajax(xid: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    url = "https://markets.ft.com/data/equities/ajax/get-historical-prices"
    params = {"startDate": start_date, "endDate": end_date, "symbol": xid}
    try:
        resp = requests.get(url, params=params, headers=_AJAX_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        html = resp.json().get("html", "")
        if not html:
            return None
        soup = BeautifulSoup(f"<table>{html}</table>", "html.parser")
        return _extraer_datos_tabla_ajax(soup)
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
        moneda = _extraer_moneda(soup, nombre)
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
    xid = None
    df_diario = None
    url = f"{FT_BASE}/historical?s={t}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            xid = _extraer_xid(soup)
            df_diario = _extraer_datos_tabla(soup)
    except Exception:
        pass
    # 1. Try Ajax with custom date range around target date
    if xid:
        target = pd.Timestamp(fecha)
        start = (target - timedelta(days=60)).strftime("%Y/%m/%d")
        end = min(target + timedelta(days=7), pd.Timestamp.now()).strftime("%Y/%m/%d")
        df_ajax = _obtener_datos_historicos_ajax(xid, start, end)
        if df_ajax is not None and not df_ajax.empty:
            nav = _buscar_nav_en_df(df_ajax, fecha)
            if nav is not None:
                return nav
    # 2. Fallback to default daily table from HTML
    if df_diario is not None:
        nav = _buscar_nav_en_df(df_diario, fecha)
        if nav is not None:
            return nav
    # 3. Fallback to monthly growth data
    df_mensual = _obtener_datos_mensuales(t)
    if df_mensual is None or df_mensual.empty:
        return None
    nav_actual = obtener_precio_actual(identificador, ticker)
    if nav_actual is None or not df_mensual["growth"].notna().any():
        return _buscar_nav_en_df(df_mensual, fecha, "growth")
    ultimo_growth = float(df_mensual["growth"].iloc[-1])
    if ultimo_growth <= 0:
        return None
    df_mensual["nav"] = df_mensual["growth"] * (nav_actual / ultimo_growth)
    return _buscar_nav_en_df(df_mensual, fecha, "nav")


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

    tc = obtener_tipo_cambio()
    if tc:
        precios_eur = precios / tc
    else:
        precios_eur = precios.copy()

    valor_posicion = participaciones * precios_eur
    pnl_diario = np.diff(valor_posicion)

    if len(pnl_diario) < 4:
        return None

    total_invertido_eur = total_invertido / tc if tc else total_invertido
    valor_actual_eur = valor_posicion[-1]
    ganancia_eur = valor_actual_eur - total_invertido_eur
    ganancia_pct = (ganancia_eur / total_invertido_eur) * 100 if total_invertido_eur else 0
    pnl_acumulado = valor_posicion - total_invertido_eur

    wins = pnl_diario[pnl_diario > 0]
    losses = pnl_diario[pnl_diario <= 0]
    win_rate = (len(wins) / len(pnl_diario)) * 100
    media = float(np.mean(pnl_diario))
    mediana = float(np.median(pnl_diario))
    mejor_dia = float(np.max(pnl_diario))
    peor_dia = float(np.min(pnl_diario))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    ax1.hist(wins, bins=20, color="#2e7d32", alpha=0.8, label=f"Días ganadores: {len(wins)}")
    ax1.hist(losses, bins=20, color="#d32f2f", alpha=0.8, label=f"Días perdedores: {len(losses)}")
    ax1.axvline(media, color="#1565c0", linestyle="dashed", linewidth=1.5, label=f"Media: €{media:.2f}")
    ax1.axvline(mediana, color="#ff8f00", linestyle="dashed", linewidth=1.5, label=f"Mediana: €{mediana:.2f}")
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_xlabel("P&L Diario (EUR)", fontsize=11)
    ax1.set_ylabel("Frecuencia", fontsize=11)
    ax1.set_title(f"Distribución P&L Diario · Win Rate: {win_rate:.1f}%", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=8, loc="upper right")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    x_acum = range(len(pnl_acumulado))
    ax2.fill_between(x_acum, pnl_acumulado, 0,
                     where=(pnl_acumulado >= 0), color="#2e7d32", alpha=0.25, label="Ganancia")
    ax2.fill_between(x_acum, pnl_acumulado, 0,
                     where=(pnl_acumulado < 0), color="#d32f2f", alpha=0.25, label="Pérdida")
    ax2.plot(x_acum, pnl_acumulado, color="#1565c0", linewidth=1.5)
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_xlabel("Días desde la primera compra", fontsize=11)
    ax2.set_ylabel("P&L Acumulado (EUR)", fontsize=11)

    pnl_final = pnl_acumulado[-1]
    if pnl_final >= 0:
        label_final = f"GANANCIA TOTAL: €{pnl_final:+.2f}"
        color_final = "#2e7d32"
    else:
        label_final = f"PÉRDIDA TOTAL: €{pnl_final:+.2f}"
        color_final = "#d32f2f"
    ax2.set_title(label_final, fontsize=13, fontweight="bold", color=color_final)
    ax2.legend(fontsize=9, loc="upper left")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    fig.suptitle(
        f"{nombre or identificador}  ·  {participaciones:.4f} participaciones\n"
        f"Invertido: €{total_invertido_eur:,.2f}  ·  "
        f"Valor actual: €{valor_actual_eur:,.2f}  ·  "
        f"Resultado: €{ganancia_eur:+.2f} ({ganancia_pct:+.2f}%)  ·  "
        f"Mejor día: €{mejor_dia:+.2f}  ·  Peor día: €{peor_dia:+.2f}",
        fontsize=11, fontweight="bold", y=0.98
    )

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    filename = f"pnl_{identificador.replace(':', '_').replace('.', '_')}.png"
    filepath = os.path.join(HIST_DIR, filename)
    plt.savefig(filepath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return filepath


def generar_grafico_pnl_linea(
    df: pd.DataFrame, participaciones: float, total_invertido: float,
    identificador: str, nombre: str = ""
) -> Optional[str]:
    if df is None or df.empty or len(df) < 5:
        return None
    os.makedirs(HIST_DIR, exist_ok=True)
    precios = df["close"].values
    fechas = df["fecha"].values

    tc = obtener_tipo_cambio()
    if tc:
        precios_eur = precios / tc
        total_inv_eur = total_invertido / tc
    else:
        precios_eur = precios.copy()
        total_inv_eur = total_invertido

    valor_posicion = participaciones * precios_eur
    pnl_diario = np.diff(valor_posicion)
    if len(pnl_diario) < 4:
        return None

    valor_actual_eur = valor_posicion[-1]
    ganancia_eur = valor_actual_eur - total_inv_eur
    ganancia_pct = (ganancia_eur / total_inv_eur) * 100 if total_inv_eur else 0
    pnl_acumulado = valor_posicion - total_inv_eur

    wins = pnl_diario[pnl_diario > 0]
    losses = pnl_diario[pnl_diario <= 0]
    win_rate = (len(wins) / len(pnl_diario)) * 100
    media = float(np.mean(pnl_diario))
    mediana = float(np.median(pnl_diario))

    fig, ax = plt.subplots(figsize=(9, 5))

    x_acum = range(len(pnl_acumulado))
    ax.fill_between(x_acum, pnl_acumulado, 0,
                    where=(pnl_acumulado >= 0), color="#2e7d32", alpha=0.25, label="Ganancia")
    ax.fill_between(x_acum, pnl_acumulado, 0,
                    where=(pnl_acumulado < 0), color="#d32f2f", alpha=0.25, label="Pérdida")
    ax.plot(x_acum, pnl_acumulado, color="#1565c0", linewidth=1.5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Días desde la primera compra", fontsize=11)
    ax.set_ylabel("P&L Acumulado (EUR)", fontsize=11)

    pnl_final = pnl_acumulado[-1]
    if pnl_final >= 0:
        label_final = f"GANANCIA TOTAL: €{pnl_final:+.2f}"
        color_final = "#2e7d32"
    else:
        label_final = f"PÉRDIDA TOTAL: €{pnl_final:+.2f}"
        color_final = "#d32f2f"
    ax.set_title(label_final, fontsize=13, fontweight="bold", color=color_final)
    ax.legend(fontsize=9, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.suptitle(
        f"{nombre or identificador}  ·  {participaciones:.4f} participaciones\n"
        f"Invertido: €{total_inv_eur:,.2f}  ·  "
        f"Valor actual: €{valor_actual_eur:,.2f}  ·  "
        f"Resultado: €{ganancia_eur:+.2f} ({ganancia_pct:+.2f}%)",
        fontsize=11, fontweight="bold", y=0.98
    )

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    filename = f"pnl_line_{identificador.replace(':', '_').replace('.', '_')}.png"
    filepath = os.path.join(HIST_DIR, filename)
    plt.savefig(filepath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return filepath


def generar_grafico_evolucion(
    df: pd.DataFrame, participaciones: float, total_invertido: float,
    identificador: str, nombre: str = ""
) -> Optional[str]:
    if df is None or df.empty or len(df) < 2:
        return None
    os.makedirs(HIST_DIR, exist_ok=True)
    precios = df["close"].values
    fechas_dt = df["fecha"].values

    tc = obtener_tipo_cambio()
    if tc:
        precios_eur = precios / tc
        total_inv_eur = total_invertido / tc
    else:
        precios_eur = precios
        total_inv_eur = total_invertido

    valor_posicion = participaciones * precios_eur
    ganancia_eur = valor_posicion[-1] - total_inv_eur
    ganancia_pct = (ganancia_eur / total_inv_eur) * 100 if total_inv_eur else 0

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(valor_posicion))

    ax.fill_between(x, total_inv_eur, valor_posicion,
                    where=(valor_posicion >= total_inv_eur),
                    color="#2e7d32", alpha=0.15, label="Ganancia")
    ax.fill_between(x, total_inv_eur, valor_posicion,
                    where=(valor_posicion < total_inv_eur),
                    color="#d32f2f", alpha=0.15, label="Pérdida")
    ax.plot(x, valor_posicion, color="#1565c0", linewidth=2, label="Valor de la inversión")
    ax.axhline(total_inv_eur, color="#ff8f00", linestyle="--", linewidth=1.5,
               label=f"Invertido: €{total_inv_eur:,.2f}")

    n = len(x)
    if n > 0:
        step = max(1, n // 10)
        tick_pos = list(range(0, n, step))
        if tick_pos[-1] != n - 1:
            tick_pos.append(n - 1)
        tick_lbl = [str(fechas_dt[i])[:10] for i in tick_pos]
        ax.set_xticks(tick_pos)
        ax.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=8)

    ax.set_xlabel("Fecha", fontsize=11)
    ax.set_ylabel("Valor (EUR)", fontsize=11)

    color_name = "green" if ganancia_eur >= 0 else "red"
    ax.set_title(
        f"{nombre or identificador}  ·  {participaciones:.4f} participaciones\n"
        f"Invertido: €{total_inv_eur:,.2f}  ·  "
        f"Actual: €{valor_posicion[-1]:,.2f}  ·  "
        f"Resultado: €{ganancia_eur:+.2f} ({ganancia_pct:+.2f}%)",
        fontsize=12, fontweight="bold", color=color_name
    )

    ax.legend(fontsize=10, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axhline(0, color="black", linewidth=0.5)

    plt.tight_layout()
    filename = f"evol_{identificador.replace(':', '_').replace('.', '_')}.png"
    filepath = os.path.join(HIST_DIR, filename)
    plt.savefig(filepath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return filepath


def obtener_portfolio_completo(items: list[dict]) -> list[dict]:
    resultados = [None] * len(items)

    def procesar(i, item):
        pos = calcular_posicion(
            item["isin"],
            item["total_participaciones"],
            item["total_invertido"],
            item.get("ticker"),
        )
        pos["nombre"] = item.get("nombre") or pos.get("nombre", "")
        return i, pos

    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = {executor.submit(procesar, i, item): i for i, item in enumerate(items)}
        for futuro in as_completed(futuros):
            i, pos = futuro.result()
            resultados[i] = pos

    return resultados
