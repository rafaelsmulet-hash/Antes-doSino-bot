"""Mesa de Sales Trading — monitoramento de estruturas + clientes/operações/carteira.

Multiusuário: cada operador só vê os próprios dados. O CSV diário do Orbit é
importado por um admin e roteado por operador via uma coluna do próprio arquivo.
"""
import os

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from auth import admin_required, current_user, load_logged_in_user, login_required, verify_password
from csv_import import guess_mapping, import_orbit_rows, read_csv_text, REQUIRED_FIELDS
from db import get_conn, init_db, now_str, today_str
from io_import import guess_column, num_of, read_tabular_upload, text_of
from monitor import (
    DEFAULT_SETTINGS,
    build_draft_text,
    compute_alerts,
    barrier_status_for,
    days_between,
    fixing_days_list,
    fmt_money,
    fmt_num,
    fmt_pct,
    parse_flexible_date,
    today_iso,
)

app = Flask(__name__)
app.secret_key = os.environ.get("MESA_SECRET_KEY", "dev-secret-troque-antes-de-usar-em-producao")

app.jinja_env.filters["pct"] = fmt_pct
app.jinja_env.filters["numfmt"] = fmt_num
app.jinja_env.filters["money"] = fmt_money

CLIENT_FIELD_PATTERNS = {
    "codigo": ["codigo", "código"],
    "nome": ["nome", "cliente"],
    "produtos": ["produto", "estrutura"],
}
OPS_FIELD_PATTERNS = {
    "codigo": ["codigo", "código"],
    "estrutura": ["estrutura"],
    "fixing": ["fixing"],
    "ativo": ["ativo"],
    "quantidade": ["quantidade", "qtd"],
    "resultado": ["resultado"],
}
CARTEIRA_FIELD_PATTERNS = {
    "codigo": ["codigo", "código"],
    "ativo": ["ativo"],
    "quantidade": ["quantidade", "qtd"],
}


@app.before_request
def _load_user():
    load_logged_in_user()


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def get_settings(conn, user_id):
    row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO settings (user_id, barrier_proximity_pct, loss_threshold_pct, fixing_alert_days) VALUES (?, ?, ?, ?)",
            (user_id, DEFAULT_SETTINGS["barrier_proximity_pct"], DEFAULT_SETTINGS["loss_threshold_pct"],
             ",".join(str(d) for d in DEFAULT_SETTINGS["fixing_alert_days"])),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    return {
        "barrier_proximity_pct": row["barrier_proximity_pct"],
        "loss_threshold_pct": row["loss_threshold_pct"],
        "fixing_alert_days": fixing_days_list(row["fixing_alert_days"]),
    }


# ---------- autenticação ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            flash("Usuário ou senha inválidos.")
            return render_template("login.html")
        session.clear()
        session["user_id"] = row["id"]
        next_url = request.args.get("next") or url_for("monitoramento")
        return redirect(next_url)
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    if current_user() is None:
        return redirect(url_for("login"))
    return redirect(url_for("monitoramento"))


# ---------- monitoramento ----------

@app.route("/monitoramento")
@login_required
def monitoramento():
    user = current_user()
    q = request.args.get("q", "").strip().lower()
    quick_filter = request.args.get("filter", "ativas")

    with get_conn() as conn:
        settings = get_settings(conn, user["id"])
        rows = conn.execute(
            "SELECT * FROM estruturas WHERE user_id = ? ORDER BY nome_cliente COLLATE NOCASE",
            (user["id"],),
        ).fetchall()

    estruturas = [dict(r) for r in rows]

    ativas = [e for e in estruturas if e["status"] == "ativa"]
    for e in ativas:
        e["barrier_status"] = barrier_status_for(e, settings["barrier_proximity_pct"])

    total_ativas = len(ativas)
    total_proxima = sum(1 for e in ativas if e["barrier_status"] == "proxima")
    total_atingida = sum(1 for e in ativas if e["barrier_status"] == "atingida")
    total_perda = sum(1 for e in ativas if e["resultado_pct"] is not None and e["resultado_pct"] <= settings["loss_threshold_pct"])

    alerts = compute_alerts(ativas, settings)

    def matches_filter(e):
        if q:
            hay = f"{e['nome_cliente']} {e['estrutura']} {e['ativo']}".lower()
            if q not in hay:
                return False
        if quick_filter == "ativas":
            return e["status"] == "ativa"
        if quick_filter == "encerradas":
            return e["status"] == "encerrada"
        if quick_filter == "proxima":
            return e["status"] == "ativa" and barrier_status_for(e, settings["barrier_proximity_pct"]) == "proxima"
        if quick_filter == "atingida":
            return e["status"] == "ativa" and barrier_status_for(e, settings["barrier_proximity_pct"]) == "atingida"
        if quick_filter == "perda":
            return e["status"] == "ativa" and e["resultado_pct"] is not None and e["resultado_pct"] <= settings["loss_threshold_pct"]
        return True

    for e in estruturas:
        if "barrier_status" not in e:
            e["barrier_status"] = barrier_status_for(e, settings["barrier_proximity_pct"])
        today = today_iso()
        e["fixing_days_left"] = days_between(today, e["fixing_iso"]) if e["fixing_iso"] else None

    filtered = [e for e in estruturas if matches_filter(e)]
    filtered.sort(key=lambda e: (
        0 if e["status"] == "ativa" else 1,
        {"atingida": 0, "proxima": 1, "normal": 2}[e["barrier_status"]],
        (e["nome_cliente"] or "").lower(),
    ))

    return render_template(
        "monitoramento.html",
        kpis={"total": total_ativas, "proxima": total_proxima, "atingida": total_atingida, "perda": total_perda},
        alerts=alerts,
        estruturas=filtered,
        q=request.args.get("q", ""),
        quick_filter=quick_filter,
    )


@app.route("/monitoramento/<int:estrutura_id>/rascunho")
@login_required
def rascunho(estrutura_id):
    user = current_user()
    with get_conn() as conn:
        e = conn.execute(
            "SELECT * FROM estruturas WHERE id = ? AND user_id = ?", (estrutura_id, user["id"])
        ).fetchone()
        settings = get_settings(conn, user["id"])
    if e is None:
        return "Estrutura não encontrada.", 404
    text = build_draft_text(dict(e), settings["barrier_proximity_pct"])
    return render_template("rascunho.html", estrutura=e, texto=text)


# ---------- import Orbit (admin) ----------

@app.route("/monitoramento/importar", methods=["GET", "POST"])
@admin_required
def importar_orbit():
    if request.method == "POST":
        file = request.files.get("arquivo")
        if not file or not file.filename:
            flash("Selecione um arquivo CSV.")
            return redirect(url_for("importar_orbit"))

        raw_text = file.read().decode("utf-8-sig")
        headers, rows = read_csv_text(raw_text)
        if not rows:
            flash("O arquivo está vazio ou não pôde ser lido.")
            return redirect(url_for("importar_orbit"))

        mapping = guess_mapping(headers)
        missing = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
        if missing:
            flash(
                "Não consegui identificar as colunas: " + ", ".join(missing) +
                ". Colunas encontradas no arquivo: " + ", ".join(headers)
            )
            return redirect(url_for("importar_orbit"))

        with get_conn() as conn:
            summary = import_orbit_rows(conn, rows, mapping, current_user()["id"])

        return render_template("importar_orbit_resultado.html", summary=summary, headers=headers, mapping=mapping)

    return render_template("importar_orbit.html")


# ---------- configurações de alerta ----------

@app.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    user = current_user()
    with get_conn() as conn:
        if request.method == "POST":
            try:
                barrier_pct = float(request.form.get("barrier_pct", "").replace(",", "."))
            except ValueError:
                barrier_pct = DEFAULT_SETTINGS["barrier_proximity_pct"]
            try:
                loss_pct = float(request.form.get("loss_pct", "").replace(",", "."))
            except ValueError:
                loss_pct = DEFAULT_SETTINGS["loss_threshold_pct"]
            fixing_days_raw = request.form.get("fixing_days", "")
            days = fixing_days_list(fixing_days_raw)

            conn.execute(
                """INSERT INTO settings (user_id, barrier_proximity_pct, loss_threshold_pct, fixing_alert_days)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET barrier_proximity_pct=excluded.barrier_proximity_pct,
                     loss_threshold_pct=excluded.loss_threshold_pct, fixing_alert_days=excluded.fixing_alert_days""",
                (user["id"], barrier_pct, loss_pct, ",".join(str(d) for d in days)),
            )
            flash("Configurações salvas.")
            return redirect(url_for("configuracoes"))

        settings = get_settings(conn, user["id"])
    return render_template("configuracoes.html", settings=settings)


# ---------- clientes ----------

@app.route("/clientes")
@login_required
def clientes_list():
    user = current_user()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clients WHERE user_id = ? ORDER BY name COLLATE NOCASE", (user["id"],)
        ).fetchall()
    return render_template("clientes_list.html", clientes=rows)


@app.route("/clientes/novo", methods=["GET", "POST"])
@login_required
def cliente_novo():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip()
        name = request.form.get("name", "").strip()
        produtos = request.form.get("produtos", "").strip()
        if not name:
            flash("Nome é obrigatório.")
            return render_template("cliente_form.html", cliente=None, form=request.form)
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO clients (user_id, codigo, name, produtos, created_at) VALUES (?, ?, ?, ?, ?)",
                (current_user()["id"], codigo, name, produtos, now_str()),
            )
        return redirect(url_for("clientes_list"))
    return render_template("cliente_form.html", cliente=None, form={})


@app.route("/clientes/<int:client_id>")
@login_required
def cliente_detail(client_id):
    user = current_user()
    with get_conn() as conn:
        cliente = conn.execute(
            "SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, user["id"])
        ).fetchone()
        if cliente is None:
            return "Cliente não encontrado.", 404
        operations = conn.execute(
            "SELECT * FROM operations WHERE client_id = ? ORDER BY id DESC", (client_id,)
        ).fetchall()
        carteira = conn.execute(
            "SELECT * FROM carteira_items WHERE client_id = ? ORDER BY ativo", (client_id,)
        ).fetchall()
    return render_template("cliente_detail.html", cliente=cliente, operations=operations, carteira=carteira)


@app.route("/clientes/<int:client_id>/editar", methods=["GET", "POST"])
@login_required
def cliente_editar(client_id):
    user = current_user()
    with get_conn() as conn:
        cliente = conn.execute(
            "SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, user["id"])
        ).fetchone()
        if cliente is None:
            return "Cliente não encontrado.", 404
        if request.method == "POST":
            codigo = request.form.get("codigo", "").strip()
            name = request.form.get("name", "").strip()
            produtos = request.form.get("produtos", "").strip()
            if not name:
                flash("Nome é obrigatório.")
                return render_template("cliente_form.html", cliente=cliente, form=request.form)
            conn.execute(
                "UPDATE clients SET codigo=?, name=?, produtos=? WHERE id=? AND user_id=?",
                (codigo, name, produtos, client_id, user["id"]),
            )
            return redirect(url_for("cliente_detail", client_id=client_id))
    return render_template("cliente_form.html", cliente=cliente, form=dict(cliente))


@app.route("/clientes/<int:client_id>/excluir", methods=["POST"])
@login_required
def cliente_excluir(client_id):
    user = current_user()
    with get_conn() as conn:
        conn.execute("DELETE FROM clients WHERE id = ? AND user_id = ?", (client_id, user["id"]))
    return redirect(url_for("clientes_list"))


@app.route("/clientes/importar", methods=["GET", "POST"])
@login_required
def clientes_importar():
    user = current_user()
    if request.method == "POST":
        file = request.files.get("arquivo")
        if not file or not file.filename:
            flash("Selecione uma planilha.")
            return redirect(url_for("clientes_importar"))

        headers, rows = read_tabular_upload(file)
        if not rows:
            flash("A planilha está vazia ou não pôde ser lida.")
            return redirect(url_for("clientes_importar"))

        mapping = {f: guess_column(headers, patterns) for f, patterns in CLIENT_FIELD_PATTERNS.items()}
        if not mapping["codigo"] or not mapping["nome"]:
            flash(
                "Não consegui identificar as colunas de Código e Nome. Colunas encontradas: " + ", ".join(headers)
            )
            return redirect(url_for("clientes_importar"))

        by_codigo = {}
        for row in rows:
            codigo = text_of(row, mapping["codigo"])
            nome = text_of(row, mapping["nome"])
            if not codigo or not nome:
                continue
            key = codigo.lower()
            produto = text_of(row, mapping["produtos"])
            if key not in by_codigo:
                by_codigo[key] = {"codigo": codigo, "nome": nome, "produtos": []}
            if produto and produto not in by_codigo[key]["produtos"]:
                by_codigo[key]["produtos"].append(produto)

        created, skipped = 0, 0
        with get_conn() as conn:
            existing_codes = {
                r["codigo"].strip().lower()
                for r in conn.execute("SELECT codigo FROM clients WHERE user_id = ?", (user["id"],)).fetchall()
                if r["codigo"]
            }
            for key, entry in by_codigo.items():
                if key in existing_codes:
                    skipped += 1
                    continue
                conn.execute(
                    "INSERT INTO clients (user_id, codigo, name, produtos, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user["id"], entry["codigo"], entry["nome"], "\n".join(entry["produtos"]), now_str()),
                )
                created += 1

        flash(f"{created} cliente(s) criado(s), {skipped} já existiam (ignorados).")
        return redirect(url_for("clientes_list"))

    return render_template("importar_generico.html", titulo="Importar clientes", acao=url_for("clientes_importar"),
                            descricao="Planilha com colunas de Código, Nome e (opcional) Produtos.")


# ---------- operações (por cliente, escopado ao operador) ----------

@app.route("/operacoes/importar", methods=["GET", "POST"])
@login_required
def operacoes_importar():
    user = current_user()
    if request.method == "POST":
        file = request.files.get("arquivo")
        if not file or not file.filename:
            flash("Selecione uma planilha.")
            return redirect(url_for("operacoes_importar"))

        headers, rows = read_tabular_upload(file)
        if not rows:
            flash("A planilha está vazia ou não pôde ser lida.")
            return redirect(url_for("operacoes_importar"))

        mapping = {f: guess_column(headers, patterns) for f, patterns in OPS_FIELD_PATTERNS.items()}
        if not mapping["codigo"]:
            flash("Não consegui identificar a coluna de Código do cliente. Colunas encontradas: " + ", ".join(headers))
            return redirect(url_for("operacoes_importar"))

        by_codigo = {}
        for row in rows:
            codigo = text_of(row, mapping["codigo"])
            if not codigo:
                continue
            key = codigo.lower()
            record = {
                "estrutura": text_of(row, mapping["estrutura"]),
                "fixing": text_of(row, mapping["fixing"]),
                "ativo": text_of(row, mapping["ativo"]),
                "quantidade": text_of(row, mapping["quantidade"]),
                "resultado_pct": num_of(row, mapping["resultado"]),
            }
            if not any([record["estrutura"], record["fixing"], record["ativo"], record["quantidade"], record["resultado_pct"] is not None]):
                continue
            by_codigo.setdefault(key, []).append(record)

        updated, not_found = 0, []
        now = now_str()
        with get_conn() as conn:
            for key, records in by_codigo.items():
                client = conn.execute(
                    "SELECT id FROM clients WHERE user_id = ? AND LOWER(codigo) = ?", (user["id"], key)
                ).fetchone()
                if client is None:
                    not_found.append(key)
                    continue
                conn.execute("DELETE FROM operations WHERE client_id = ?", (client["id"],))
                for record in records:
                    fixing_iso = parse_flexible_date(record["fixing"]) if record["fixing"] else None
                    conn.execute(
                        """INSERT INTO operations (client_id, estrutura, fixing, fixing_iso, ativo, quantidade,
                           resultado_pct, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (client["id"], record["estrutura"], record["fixing"], fixing_iso, record["ativo"],
                         record["quantidade"], record["resultado_pct"], now),
                    )
                updated += 1

        msg = f"{updated} cliente(s) atualizado(s)."
        if not_found:
            msg += f" Códigos não encontrados: {', '.join(not_found)}."
        flash(msg)
        return redirect(url_for("clientes_list"))

    return render_template("importar_generico.html", titulo="Importar operações", acao=url_for("operacoes_importar"),
                            descricao="Planilha com Código do cliente, Estrutura, Fixing, Ativo, Quantidade e Resultado (%). Substitui as operações do cliente.")


# ---------- carteira (por cliente, escopado ao operador) ----------

@app.route("/carteira/importar", methods=["GET", "POST"])
@login_required
def carteira_importar():
    user = current_user()
    if request.method == "POST":
        file = request.files.get("arquivo")
        if not file or not file.filename:
            flash("Selecione uma planilha.")
            return redirect(url_for("carteira_importar"))

        headers, rows = read_tabular_upload(file)
        if not rows:
            flash("A planilha está vazia ou não pôde ser lida.")
            return redirect(url_for("carteira_importar"))

        mapping = {f: guess_column(headers, patterns) for f, patterns in CARTEIRA_FIELD_PATTERNS.items()}
        if not mapping["codigo"] or not mapping["ativo"]:
            flash("Não consegui identificar as colunas de Código e Ativo. Colunas encontradas: " + ", ".join(headers))
            return redirect(url_for("carteira_importar"))

        by_codigo = {}
        for row in rows:
            codigo = text_of(row, mapping["codigo"])
            ativo = text_of(row, mapping["ativo"])
            qty = num_of(row, mapping["quantidade"])
            if not codigo or not ativo or qty is None:
                continue
            key = codigo.lower()
            by_codigo.setdefault(key, {})
            ativo_key = ativo.lower()
            if ativo_key not in by_codigo[key]:
                by_codigo[key][ativo_key] = {"ativo": ativo, "quantidade": 0.0}
            by_codigo[key][ativo_key]["quantidade"] += qty

        updated, not_found = 0, []
        now = now_str()
        with get_conn() as conn:
            for key, items in by_codigo.items():
                client = conn.execute(
                    "SELECT id FROM clients WHERE user_id = ? AND LOWER(codigo) = ?", (user["id"], key)
                ).fetchone()
                if client is None:
                    not_found.append(key)
                    continue
                conn.execute("DELETE FROM carteira_items WHERE client_id = ?", (client["id"],))
                for item in items.values():
                    conn.execute(
                        "INSERT INTO carteira_items (client_id, ativo, quantidade, updated_at) VALUES (?, ?, ?, ?)",
                        (client["id"], item["ativo"], item["quantidade"], now),
                    )
                updated += 1

        msg = f"{updated} cliente(s) atualizado(s)."
        if not_found:
            msg += f" Códigos não encontrados: {', '.join(not_found)}."
        flash(msg)
        return redirect(url_for("clientes_list"))

    return render_template("importar_generico.html", titulo="Importar carteira", acao=url_for("carteira_importar"),
                            descricao="Planilha com Código do cliente, Ativo e Quantidade. Linhas repetidas do mesmo ativo são somadas. Substitui a carteira do cliente.")


# ---------- administração de operadores ----------

@app.route("/admin/operadores")
@admin_required
def admin_operadores():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    return render_template("admin_operadores.html", operadores=rows)


@app.route("/admin/operadores/novo", methods=["POST"])
@admin_required
def admin_operador_novo():
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    password = request.form.get("password", "")
    is_admin = 1 if request.form.get("is_admin") else 0

    if not username or not password:
        flash("Usuário e senha são obrigatórios.")
        return redirect(url_for("admin_operadores"))

    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            flash("Já existe um operador com esse usuário.")
            return redirect(url_for("admin_operadores"))
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), display_name or username, is_admin, now_str()),
        )
    flash(f"Operador {username} criado.")
    return redirect(url_for("admin_operadores"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
