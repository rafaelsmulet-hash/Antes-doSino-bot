"""Import do CSV diário do Orbit: parsing + upsert por operador.

A chave de cada estrutura é Cliente + Ativo + Estrutura + Data operação, escopada
por operador (cada operador só upserta/fecha dentro do próprio conjunto). Uma
estrutura ativa que não aparece mais no arquivo é encerrada automaticamente —
mas só para operadores que de fato tiveram alguma linha no arquivo daquele dia,
pra um arquivo incompleto (faltando o bloco de um operador) não apagar a
carteira inteira dele por engano.
"""
import csv
import io
from collections import defaultdict

from db import get_conn, now_str, today_str
from monitor import parse_flexible_date

REQUIRED_FIELDS = ["operador", "cliente", "estrutura", "ativo", "dataoperacao"]

FIELD_PATTERNS = {
    "operador": ["operador", "trader", "mesa"],
    "cliente": ["nome cliente", "cliente"],
    "estrutura": ["estrutura"],
    "ativo": ["ativo"],
    "dataoperacao": ["data opera", "data_oper", "dataoperacao"],
    "fixing": ["fixing"],
    "notional": ["notional"],
    "barreiradown": ["barreira down"],
    "barreiraup": ["barreira up"],
    "disbarreira": ["dis. barreira", "dis barreira", "distância", "distancia"],
    "barreiraacionada": ["acionada"],
    "resultadopct": ["resultado (%)", "resultado(%)", "resultado %"],
    "resultadors": ["resultado (r$)", "resultado(r$)", "resultado r$"],
}


def read_csv_text(raw_text):
    """Faz o parsing do texto CSV (já decodificado em UTF-8) e retorna (headers, rows)."""
    reader = csv.DictReader(io.StringIO(raw_text))
    headers = reader.fieldnames or []
    rows = list(reader)
    return headers, rows


def guess_column(headers, field):
    for h in headers:
        hl = h.strip().lower()
        for pattern in FIELD_PATTERNS[field]:
            if pattern in hl:
                return h
    return ""


def guess_mapping(headers):
    return {field: guess_column(headers, field) for field in FIELD_PATTERNS}


def _text_of(row, col):
    if not col:
        return ""
    val = row.get(col)
    return "" if val is None else str(val).strip()


def _num_of(row, col):
    if not col:
        return None
    val = row.get(col)
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip().replace(",", ".").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _date_info(row, col):
    if not col:
        return "", None
    raw = _text_of(row, col)
    if not raw:
        return "", None
    return raw, parse_flexible_date(raw)


def import_orbit_rows(conn, rows, mapping, imported_by_user_id):
    """Aplica o upsert dentro de uma conexão já aberta (get_conn). Retorna o resumo."""
    users = {
        u["username"].strip().lower(): u["id"]
        for u in conn.execute("SELECT id, username FROM users").fetchall()
    }

    users_with_active_before = {
        r["user_id"] for r in conn.execute(
            "SELECT DISTINCT user_id FROM estruturas WHERE status = 'ativa'"
        ).fetchall()
    }

    seen_keys_by_user = defaultdict(set)
    operadores_no_arquivo = set()
    unmatched_operadores = defaultdict(int)
    created = 0
    updated = 0
    now = now_str()
    today = today_str()

    for row in rows:
        operador_raw = _text_of(row, mapping.get("operador"))
        nome_cliente = _text_of(row, mapping.get("cliente"))
        estrutura = _text_of(row, mapping.get("estrutura"))
        ativo = _text_of(row, mapping.get("ativo"))
        data_operacao, _ = _date_info(row, mapping.get("dataoperacao"))

        if not operador_raw or not nome_cliente or not estrutura or not ativo or not data_operacao:
            continue

        user_id = users.get(operador_raw.strip().lower())
        if user_id is None:
            unmatched_operadores[operador_raw] += 1
            continue

        operadores_no_arquivo.add(user_id)

        key = "|".join([nome_cliente, ativo, estrutura, data_operacao]).lower()
        seen_keys_by_user[user_id].add(key)

        fixing_display, fixing_iso = _date_info(row, mapping.get("fixing"))
        acionada_display, acionada_iso = _date_info(row, mapping.get("barreiraacionada"))
        notional = _num_of(row, mapping.get("notional"))
        barreira_down = _num_of(row, mapping.get("barreiradown"))
        barreira_up = _num_of(row, mapping.get("barreiraup"))
        dis_barreira = _num_of(row, mapping.get("disbarreira"))
        resultado_pct = _num_of(row, mapping.get("resultadopct"))
        resultado_rs = _num_of(row, mapping.get("resultadors"))

        existing = conn.execute(
            "SELECT id FROM estruturas WHERE user_id = ? AND dedup_key = ?", (user_id, key)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE estruturas SET nome_cliente=?, estrutura=?, ativo=?, data_operacao=?,
                   fixing=?, fixing_iso=?, notional=?, barreira_down=?, barreira_up=?, dis_barreira_pct=?,
                   barreira_acionada_em=?, barreira_acionada_iso=?, resultado_pct=?, resultado_rs=?,
                   status='ativa', closed_at=NULL, last_seen_at=?, updated_at=?
                   WHERE id=?""",
                (nome_cliente, estrutura, ativo, data_operacao, fixing_display, fixing_iso,
                 notional, barreira_down, barreira_up, dis_barreira, acionada_display, acionada_iso,
                 resultado_pct, resultado_rs, today, now, existing["id"]),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO estruturas (user_id, dedup_key, nome_cliente, estrutura, ativo, data_operacao,
                   fixing, fixing_iso, notional, barreira_down, barreira_up, dis_barreira_pct,
                   barreira_acionada_em, barreira_acionada_iso, resultado_pct, resultado_rs,
                   status, closed_at, first_seen_at, last_seen_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ativa', NULL, ?, ?, ?, ?)""",
                (user_id, key, nome_cliente, estrutura, ativo, data_operacao, fixing_display, fixing_iso,
                 notional, barreira_down, barreira_up, dis_barreira, acionada_display, acionada_iso,
                 resultado_pct, resultado_rs, today, today, now, now),
            )
            created += 1

    closed = 0
    for user_id in operadores_no_arquivo:
        seen = seen_keys_by_user[user_id]
        active_rows = conn.execute(
            "SELECT id, dedup_key FROM estruturas WHERE user_id = ? AND status = 'ativa'", (user_id,)
        ).fetchall()
        for r in active_rows:
            if r["dedup_key"] not in seen:
                conn.execute(
                    "UPDATE estruturas SET status='encerrada', closed_at=?, updated_at=? WHERE id=?",
                    (today, now, r["id"]),
                )
                closed += 1

    # quem tinha estruturas ativas ANTES desse import mas não apareceu de jeito nenhum no arquivo
    operadores_nao_fechados_ids = sorted(users_with_active_before - operadores_no_arquivo)

    id_to_username = {u["id"]: u["username"] for u in conn.execute("SELECT id, username FROM users").fetchall()}

    summary = {
        "total_rows": len(rows),
        "created": created,
        "updated": updated,
        "closed": closed,
        "unmatched_operadores": dict(unmatched_operadores),
        "operadores_no_arquivo": sorted(id_to_username.get(uid, "?") for uid in operadores_no_arquivo),
        "operadores_nao_fechados": [id_to_username.get(uid, "?") for uid in operadores_nao_fechados_ids],
    }

    conn.execute(
        """INSERT INTO import_log (imported_by, imported_at, total_rows, created_count, updated_count,
           closed_count, unmatched_operador_count, unmatched_operadores, operadores_no_arquivo,
           operadores_nao_fechados)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            imported_by_user_id, now, summary["total_rows"], created, updated, closed,
            sum(unmatched_operadores.values()),
            ", ".join(f"{k} ({v})" for k, v in unmatched_operadores.items()),
            ", ".join(summary["operadores_no_arquivo"]),
            ", ".join(summary["operadores_nao_fechados"]),
        ),
    )

    return summary
