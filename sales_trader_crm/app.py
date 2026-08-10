"""Controle de contato com clientes de mesa de operações (sales trader)."""
from flask import Flask, render_template, request, redirect, url_for, flash

from db import get_conn, init_db, today_str
from status import client_status

app = Flask(__name__)
app.secret_key = "sales-trader-client-tracker"  # uso local, sem multiusuário


def _last_contact_dates(conn):
    """Mapa client_id -> data do contato mais recente."""
    rows = conn.execute(
        "SELECT client_id, MAX(contact_date) AS last_date FROM contacts GROUP BY client_id"
    ).fetchall()
    return {row["client_id"]: row["last_date"] for row in rows}


def _clients_with_status(conn):
    rows = conn.execute("SELECT * FROM clients").fetchall()
    last_contacts = _last_contact_dates(conn)

    clients = []
    for row in rows:
        client = dict(row)
        client.update(client_status(last_contacts.get(row["id"])))
        clients.append(client)

    # mais urgente primeiro: menor dias_remaining primeiro (vermelho > amarelo > verde)
    clients.sort(key=lambda c: (c["days_remaining"] is None, c["days_remaining"]))
    return clients


@app.route("/")
def index():
    search = request.args.get("q", "").strip().lower()
    with get_conn() as conn:
        all_clients = _clients_with_status(conn)

    counts = {"red": 0, "yellow": 0, "green": 0}
    for c in all_clients:
        counts[c["status"]] += 1

    clients = all_clients
    if search:
        clients = [
            c for c in all_clients
            if search in c["name"].lower() or search in (c["codigo"] or "").lower()
        ]

    return render_template("index.html", clients=clients, counts=counts, search=search)


@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip()
        name = request.form["name"].strip()
        structures = request.form.get("structures", "").strip()
        notes = request.form.get("notes", "").strip()
        last_contact_date = request.form.get("last_contact_date") or today_str()
        if not name:
            flash("Nome é obrigatório.")
            return render_template("client_form.html", client=None, form=request.form, today=today_str())

        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO clients (codigo, name, structures, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                (codigo, name, structures, notes, today_str()),
            )
            client_id = cur.lastrowid
            conn.execute(
                "INSERT INTO contacts (client_id, contact_date, note, created_at) VALUES (?, ?, ?, ?)",
                (client_id, last_contact_date, "Cadastro inicial", today_str()),
            )
        return redirect(url_for("index"))

    return render_template("client_form.html", client=None, form={}, today=today_str())


@app.route("/clients/<int:client_id>")
def client_detail(client_id):
    with get_conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if client is None:
            return redirect(url_for("index"))
        history = conn.execute(
            "SELECT * FROM contacts WHERE client_id = ? ORDER BY contact_date DESC, id DESC",
            (client_id,),
        ).fetchall()
        last_date = history[0]["contact_date"] if history else None

    status = client_status(last_date)
    return render_template(
        "client_detail.html", client=client, history=history, status=status, today=today_str()
    )


@app.route("/clients/<int:client_id>/contact", methods=["POST"])
def quick_contact(client_id):
    """Ação rápida: registra contato de hoje sem nota."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO contacts (client_id, contact_date, note, created_at) VALUES (?, ?, ?, ?)",
            (client_id, today_str(), "", today_str()),
        )
    return redirect(request.referrer or url_for("index"))


@app.route("/clients/<int:client_id>/contacts", methods=["POST"])
def add_contact(client_id):
    """Registro de contato com data e nota escolhidas na tela de detalhe."""
    contact_date = request.form.get("contact_date") or today_str()
    note = request.form.get("note", "").strip()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO contacts (client_id, contact_date, note, created_at) VALUES (?, ?, ?, ?)",
            (client_id, contact_date, note, today_str()),
        )
    return redirect(url_for("client_detail", client_id=client_id))


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    with get_conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if client is None:
        return redirect(url_for("index"))

    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip()
        name = request.form["name"].strip()
        structures = request.form.get("structures", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name:
            flash("Nome é obrigatório.")
            return render_template("client_form.html", client=client, form=request.form)

        with get_conn() as conn:
            conn.execute(
                "UPDATE clients SET codigo = ?, name = ?, structures = ?, notes = ? WHERE id = ?",
                (codigo, name, structures, notes, client_id),
            )
        return redirect(url_for("client_detail", client_id=client_id))

    return render_template("client_form.html", client=client, form=client)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
