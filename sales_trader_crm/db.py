"""Persistência SQLite: mesa de sales trading, multiusuário.

Cada operador só enxerga os próprios clientes/operações/carteira/estruturas —
tudo é escopado por user_id nas queries em app.py, nunca confiar no cliente.
"""
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "mesa.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    codigo TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    produtos TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clients_user ON clients(user_id);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    estrutura TEXT NOT NULL DEFAULT '',
    fixing TEXT NOT NULL DEFAULT '',
    fixing_iso TEXT,
    ativo TEXT NOT NULL DEFAULT '',
    quantidade TEXT NOT NULL DEFAULT '',
    resultado_pct REAL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operations_client ON operations(client_id);

CREATE TABLE IF NOT EXISTS carteira_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    ativo TEXT NOT NULL,
    quantidade REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_carteira_client ON carteira_items(client_id);

CREATE TABLE IF NOT EXISTS estruturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dedup_key TEXT NOT NULL,
    nome_cliente TEXT NOT NULL DEFAULT '',
    estrutura TEXT NOT NULL DEFAULT '',
    ativo TEXT NOT NULL DEFAULT '',
    data_operacao TEXT NOT NULL DEFAULT '',
    fixing TEXT NOT NULL DEFAULT '',
    fixing_iso TEXT,
    notional REAL,
    barreira_down REAL,
    barreira_up REAL,
    dis_barreira_pct REAL,
    barreira_acionada_em TEXT NOT NULL DEFAULT '',
    barreira_acionada_iso TEXT,
    resultado_pct REAL,
    resultado_rs REAL,
    status TEXT NOT NULL DEFAULT 'ativa',
    closed_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_estruturas_user_key ON estruturas(user_id, dedup_key);
CREATE INDEX IF NOT EXISTS idx_estruturas_user_status ON estruturas(user_id, status);

CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    barrier_proximity_pct REAL NOT NULL DEFAULT 5,
    loss_threshold_pct REAL NOT NULL DEFAULT -10,
    fixing_alert_days TEXT NOT NULL DEFAULT '5,2,1,0'
);

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_by INTEGER NOT NULL REFERENCES users(id),
    imported_at TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0,
    created_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    closed_count INTEGER NOT NULL DEFAULT 0,
    unmatched_operador_count INTEGER NOT NULL DEFAULT 0,
    unmatched_operadores TEXT NOT NULL DEFAULT '',
    operadores_no_arquivo TEXT NOT NULL DEFAULT '',
    operadores_nao_fechados TEXT NOT NULL DEFAULT ''
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now_str():
    return datetime.now().isoformat(timespec="seconds")


def today_str():
    return date.today().isoformat()
