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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha           TEXT NOT NULL,
                total_invertido REAL NOT NULL,
                total_valor     REAL NOT NULL,
                daily_pnl       REAL,
                cumulative_pnl  REAL NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_fecha
            ON daily_snapshots(fecha)
        """)
        # Migration: remove UNIQUE constraint from legacy schema
        _migrar_snapshots(conn)


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


def actualizar_transaccion(
    transaccion_id: int,
    fecha: str,
    tipo: str,
    participaciones: float,
    precio: float,
    total: float,
    moneda: str = "USD",
) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            """UPDATE transacciones
               SET fecha=?, tipo=?, participaciones=?, precio=?, total=?, moneda=?
               WHERE id=?""",
            (fecha, tipo, participaciones, precio, total, moneda, transaccion_id),
        )
        return cursor.rowcount > 0


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


def guardar_snapshot(fecha: str, total_invertido: float, total_valor: float,
                     daily_pnl: float = None, cumulative_pnl: float = None) -> int:
    if cumulative_pnl is None:
        cumulative_pnl = round(total_valor - total_invertido, 2)
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO daily_snapshots (fecha, total_invertido, total_valor, daily_pnl, cumulative_pnl)
            VALUES (?, ?, ?, ?, ?)
        """, (fecha, total_invertido, total_valor, daily_pnl, cumulative_pnl))
        return cursor.lastrowid


def obtener_ultimo_snapshot() -> dict:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM daily_snapshots ORDER BY fecha DESC LIMIT 1
        """).fetchone()
    return dict(row) if row else None


def obtener_snapshots(limite: int = None) -> list[dict]:
    with get_connection() as conn:
        query = "SELECT * FROM daily_snapshots ORDER BY fecha DESC"
        if limite:
            query += f" LIMIT {limite}"
        rows = conn.execute(query).fetchall()
    return [dict(r) for r in rows]


def eliminar_snapshot(snapshot_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM daily_snapshots WHERE id = ?", (snapshot_id,)
        )
        return cursor.rowcount > 0


def obtener_snapshots_asc() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY fecha ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def _migrar_snapshots(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_snapshots'"
    ).fetchone()
    if row and "UNIQUE" in row["sql"].upper():
        conn.execute("ALTER TABLE daily_snapshots RENAME TO daily_snapshots_old")
        conn.execute("""
            CREATE TABLE daily_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha           TEXT NOT NULL,
                total_invertido REAL NOT NULL,
                total_valor     REAL NOT NULL,
                daily_pnl       REAL,
                cumulative_pnl  REAL NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO daily_snapshots
                (id, fecha, total_invertido, total_valor, daily_pnl, cumulative_pnl, created_at)
            SELECT id,
                   CASE WHEN length(fecha) <= 10 THEN fecha || ' 00:00:00' ELSE fecha END,
                   total_invertido, total_valor, daily_pnl, cumulative_pnl, created_at
            FROM daily_snapshots_old
        """)
        conn.execute("DROP TABLE daily_snapshots_old")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_fecha
            ON daily_snapshots(fecha)
        """)
