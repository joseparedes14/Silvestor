import sqlite3
import os
from datetime import datetime
from typing import Optional


DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "inversiones.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transacciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                isin            TEXT NOT NULL,
                ticker          TEXT DEFAULT '',
                nombre          TEXT NOT NULL,
                tipo            TEXT NOT NULL CHECK(tipo IN ('compra', 'venta')),
                participaciones REAL NOT NULL,
                precio          REAL NOT NULL,
                total           REAL NOT NULL,
                fecha           TEXT NOT NULL,
                moneda          TEXT NOT NULL DEFAULT 'USD',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transacciones_isin
            ON transacciones(isin)
        """)


def agregar_transaccion(
    isin: str,
    nombre: str,
    tipo: str,
    participaciones: float,
    precio: float,
    total: float,
    fecha: Optional[str] = None,
    moneda: str = "USD",
    ticker: str = "",
) -> int:
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO transacciones
               (isin, ticker, nombre, tipo, participaciones, precio, total, fecha, moneda)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (isin.upper(), ticker.upper(), nombre, tipo, participaciones, precio, total, fecha, moneda),
        )
        return cursor.lastrowid


def listar_transacciones(isin: Optional[str] = None):
    with get_connection() as conn:
        if isin:
            rows = conn.execute(
                "SELECT * FROM transacciones WHERE isin = ? ORDER BY fecha DESC",
                (isin.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transacciones ORDER BY fecha DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def eliminar_transaccion(transaccion_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM transacciones WHERE id = ?", (transaccion_id,)
        )
        return cursor.rowcount > 0


def obtener_portfolio():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                isin,
                ticker,
                nombre,
                moneda,
                SUM(CASE WHEN tipo = 'compra' THEN participaciones ELSE -participaciones END) AS total_participaciones,
                SUM(CASE WHEN tipo = 'compra' THEN total ELSE -total END) AS total_invertido,
                COUNT(*) AS num_transacciones
            FROM transacciones
            GROUP BY isin
            HAVING total_participaciones > 0
            ORDER BY total_invertido DESC
        """).fetchall()
    return [dict(r) for r in rows]


def obtener_isins():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT isin FROM transacciones ORDER BY isin"
        ).fetchall()
    return [r["isin"] for r in rows]


def obtener_resumen_isin(isin: str):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                isin,
                ticker,
                nombre,
                moneda,
                SUM(CASE WHEN tipo = 'compra' THEN participaciones ELSE -participaciones END) AS total_participaciones,
                SUM(CASE WHEN tipo = 'compra' THEN total ELSE -total END) AS total_invertido
            FROM transacciones
            WHERE isin = ?
            GROUP BY isin
        """, (isin.upper(),)).fetchall()
    return [dict(r) for r in rows]
