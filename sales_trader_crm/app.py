"""Controle de contato com clientes de mesa de operações (sales trader)."""
from flask import Flask, render_template, request, redirect, url_for, flash

from db import get_conn, init_db, today_str

app = Flask(__name__)
app.secret_key = "sales-trader-client-tracker"  # uso local, sem multiusuário


@app.route("/")
def index():
    with get_conn() as conn:
        clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return render_template("index.html", clients=clients)


@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        name = request.form["name"].strip()
        structures = request.form.get("structures", "").strip()
        notes = request.form.get("notes", "").strip()
        last_contact_date = request.form.get("last_contact_date") or today_str()
        if not name:
            flash("Nome é obrigatório.")
            return render_template("client_form.html", client=None, form=request.form, today=today_str())

        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO clients (name, structures, notes, created_at) VALUES (?, ?, ?, ?)",
                (name, structures, notes, today_str()),
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
    return render_template("client_detail.html", client=client)


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    with get_conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if client is None:
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form["name"].strip()
        structures = request.form.get("structures", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name:
            flash("Nome é obrigatório.")
            return render_template("client_form.html", client=client, form=request.form)

        with get_conn() as conn:
            conn.execute(
                "UPDATE clients SET name = ?, structures = ?, notes = ? WHERE id = ?",
                (name, structures, notes, client_id),
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
