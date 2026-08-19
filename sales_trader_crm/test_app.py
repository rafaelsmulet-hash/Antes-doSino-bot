"""Testes de ponta a ponta via Flask test client: isolamento entre operadores,
import do CSV do Orbit (roteamento por operador + salvaguarda), clientes/operações/
carteira escopados, alertas e rascunho."""
import io
import os
import tempfile

os.environ["MESA_SECRET_KEY"] = "test-secret"

import db  # noqa: E402

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db.DB_PATH = db.Path(_tmp_db.name)

import app as appmod  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

pass_count = 0
fail_count = 0


def check(cond, msg):
    global pass_count, fail_count
    if cond:
        pass_count += 1
    else:
        fail_count += 1
        print("FAIL:", msg)


def make_user(conn, username, password, is_admin=0, display_name=None):
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, generate_password_hash(password), display_name or username, is_admin, db.now_str()),
    )


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=True)


def csv_bytes(rows_text):
    return io.BytesIO(rows_text.encode("utf-8"))


def main():
    db.init_db()
    with db.get_conn() as conn:
        make_user(conn, "admin", "adminpass", is_admin=1, display_name="Admin")
        make_user(conn, "alice", "alicepass", display_name="Alice")
        make_user(conn, "bob", "bobpass", display_name="Bob")

    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    # --- login/logout ---
    resp = login(client, "alice", "wrongpass")
    check(b"invalidos" in resp.data or b"inv\xc3\xa1lidos" in resp.data, "login errado mostra mensagem de erro")

    resp = login(client, "alice", "alicepass")
    check(resp.status_code == 200, "login correto retorna 200 (com follow_redirects)")
    check(b"Monitoramento" in resp.data, "apos login, cai no dashboard de monitoramento")

    resp = client.get("/clientes")
    check(resp.status_code == 200, "alice consegue acessar /clientes logada")

    client.post("/logout")
    resp = client.get("/clientes", follow_redirects=False)
    check(resp.status_code == 302, "sem sessao, /clientes redireciona (login_required)")

    # --- admin only ---
    login(client, "alice", "alicepass")
    resp = client.get("/monitoramento/importar")
    check(resp.status_code == 403, "operador comum nao pode acessar import do Orbit (403)")
    resp = client.get("/admin/operadores")
    check(resp.status_code == 403, "operador comum nao pode acessar admin/operadores (403)")
    client.post("/logout")

    login(client, "admin", "adminpass")
    resp = client.get("/monitoramento/importar")
    check(resp.status_code == 200, "admin acessa tela de import do Orbit")
    client.post("/logout")

    # --- import do CSV Orbit: roteamento por operador + upsert + fechamento ---
    login(client, "admin", "adminpass")

    headers = "Operador,Nome Cliente,Estrutura,Ativo,Data operação,Fixing,Notional,Barreira Down,Barreira up,Dis. Barreira(%),Barreira acionada em,Resultado (%),Resultado (R$)"
    rows1 = "\n".join([
        headers,
        "alice,Cliente A1,Trava,PETR4,01/01/2026,25/12/2026,1000000,28,40,3,,5,50000",
        "alice,Cliente A2,Collar,VALE3,05/01/2026,20/12/2026,500000,60,80,20,,-15,-30000",
        "bob,Cliente B1,PutSpread,ITUB4,10/01/2026,22/12/2026,300000,20,30,2,15/08/2026,1,1000",
    ])
    resp = client.post(
        "/monitoramento/importar",
        data={"arquivo": (csv_bytes(rows1), "orbit1.csv")},
        content_type="multipart/form-data",
    )
    check(resp.status_code == 200, "import 1 aplicado com sucesso")
    check(b"3</strong>" in resp.data, "3 estruturas novas no primeiro import")

    with db.get_conn() as conn:
        alice_id = conn.execute("SELECT id FROM users WHERE username='alice'").fetchone()["id"]
        bob_id = conn.execute("SELECT id FROM users WHERE username='bob'").fetchone()["id"]
        alice_rows = conn.execute("SELECT * FROM estruturas WHERE user_id=?", (alice_id,)).fetchall()
        bob_rows = conn.execute("SELECT * FROM estruturas WHERE user_id=?", (bob_id,)).fetchall()

    check(len(alice_rows) == 2, f"alice tem 2 estruturas, tem {len(alice_rows)}")
    check(len(bob_rows) == 1, f"bob tem 1 estrutura, tem {len(bob_rows)}")
    check(all(r["status"] == "ativa" for r in alice_rows + bob_rows), "todas ativas apos import 1")

    bob_row = bob_rows[0]
    check(bob_row["barreira_acionada_em"] == "15/08/2026", "bob: barreira acionada em preservada")

    # isolamento: alice nao ve estrutura de bob
    login(client, "alice", "alicepass")
    resp = client.get("/monitoramento")
    check(b"Cliente A1" in resp.data, "alice ve a propria estrutura Cliente A1")
    check(b"Cliente B1" not in resp.data, "alice NAO ve a estrutura do bob (Cliente B1)")
    check(b"Barreira atingida" not in resp.data or b"Cliente B1" not in resp.data, "alerta de bob nao aparece pra alice")
    client.post("/logout")

    login(client, "bob", "bobpass")
    resp = client.get("/monitoramento")
    check(b"Cliente B1" in resp.data, "bob ve a propria estrutura")
    check(b"Cliente A1" not in resp.data, "bob NAO ve estrutura da alice")
    client.post("/logout")

    # --- segundo import: so alice aparece; bob sumiu do arquivo -> bob NAO deve ser fechado (salvaguarda) ---
    login(client, "admin", "adminpass")
    rows2 = "\n".join([
        headers,
        "alice,Cliente A1,Trava,PETR4,01/01/2026,25/12/2026,1000000,28,40,3,,5,50000",
        # Cliente A2 da alice sumiu -> deve fechar
        # bob nao aparece de jeito nenhum -> NAO deve fechar nada do bob
    ])
    resp = client.post(
        "/monitoramento/importar",
        data={"arquivo": (csv_bytes(rows2), "orbit2.csv")},
        content_type="multipart/form-data",
    )
    check(resp.status_code == 200, "import 2 aplicado com sucesso")
    check(b"bob" in resp.data, "resultado avisa que bob ficou de fora (operador ausente)")

    with db.get_conn() as conn:
        alice_rows2 = conn.execute("SELECT * FROM estruturas WHERE user_id=?", (alice_id,)).fetchall()
        bob_rows2 = conn.execute("SELECT * FROM estruturas WHERE user_id=?", (bob_id,)).fetchall()

    a1 = next(r for r in alice_rows2 if r["nome_cliente"] == "Cliente A1")
    a2 = next(r for r in alice_rows2 if r["nome_cliente"] == "Cliente A2")
    check(a1["status"] == "ativa", "Cliente A1 (reapareceu) continua ativa")
    check(a2["status"] == "encerrada", "Cliente A2 (sumiu do arquivo) foi encerrada")
    check(bob_rows2[0]["status"] == "ativa", "estrutura do bob NAO foi encerrada (bob nao apareceu no arquivo -> salvaguarda)")

    # --- operador nao cadastrado no CSV ---
    rows3 = "\n".join([
        headers,
        "carla,Cliente C1,Trava,MGLU3,01/02/2026,25/12/2026,100000,10,20,4,,2,2000",
    ])
    resp = client.post(
        "/monitoramento/importar",
        data={"arquivo": (csv_bytes(rows3), "orbit3.csv")},
        content_type="multipart/form-data",
    )
    check(b"carla" in resp.data, "operador nao cadastrado (carla) aparece como nao reconhecido")
    with db.get_conn() as conn:
        carla_count = conn.execute("SELECT COUNT(*) c FROM estruturas WHERE nome_cliente='Cliente C1'").fetchone()["c"]
    check(carla_count == 0, "linha de operador nao cadastrado nao vira estrutura nenhuma")
    client.post("/logout")

    # --- KPIs e alertas ---
    login(client, "alice", "alicepass")
    resp = client.get("/monitoramento")
    check(b"Perda relevante" in resp.data, "alice tem alerta de perda relevante (Cliente A2, -15%)")

    # config de alertas: mudar limiar de perda pra -1% deve fazer o A1 (+5%) continuar de fora e nao alterar isso,
    # mas confirma que a tela de configuracoes funciona
    resp = client.post("/configuracoes", data={"barrier_pct": "5", "loss_pct": "-1", "fixing_days": "5,2,1,0"}, follow_redirects=True)
    check(resp.status_code == 200, "salvar configuracoes funciona")
    with db.get_conn() as conn:
        s = conn.execute("SELECT * FROM settings WHERE user_id=?", (alice_id,)).fetchone()
    check(s["loss_threshold_pct"] == -1.0, "limiar de perda salvo corretamente")

    # --- rascunho ---
    with db.get_conn() as conn:
        estrutura_a2 = conn.execute("SELECT id FROM estruturas WHERE nome_cliente='Cliente A2'").fetchone()
    resp = client.get(f"/monitoramento/{estrutura_a2['id']}/rascunho")
    check(resp.status_code == 200, "pagina de rascunho abre")
    check("Cliente A2".encode() in resp.data, "rascunho menciona o cliente certo")
    check("revisar antes de enviar".encode() in resp.data, "rascunho carrega aviso de revisao manual")

    # bob nao consegue ver rascunho de estrutura da alice (tentativa direta por id)
    client.post("/logout")
    login(client, "bob", "bobpass")
    resp = client.get(f"/monitoramento/{estrutura_a2['id']}/rascunho")
    check(resp.status_code == 404, "bob NAO consegue abrir rascunho de estrutura da alice (id direto) -> 404")
    client.post("/logout")

    # --- clientes / operacoes / carteira escopados ---
    login(client, "alice", "alicepass")
    resp = client.post("/clientes/novo", data={"codigo": "CLI1", "name": "Fulano", "produtos": "Opcoes"}, follow_redirects=True)
    check(resp.status_code == 200, "alice cria cliente proprio")

    ops_csv = "Codigo,Estrutura,Fixing,Ativo,Quantidade,Resultado\nCLI1,Trava,20/12/2026,PETR4,100,4.5\n"
    resp = client.post(
        "/operacoes/importar",
        data={"arquivo": (csv_bytes(ops_csv), "ops.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    check(resp.status_code == 200, "import de operacoes funciona")

    cart_csv = "Codigo,Ativo,Quantidade\nCLI1,PETR4,100\nCLI1,PETR4,50\n"
    resp = client.post(
        "/carteira/importar",
        data={"arquivo": (csv_bytes(cart_csv), "cart.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    check(resp.status_code == 200, "import de carteira funciona")

    with db.get_conn() as conn:
        cli1 = conn.execute("SELECT * FROM clients WHERE user_id=? AND codigo='CLI1'", (alice_id,)).fetchone()
        ops = conn.execute("SELECT * FROM operations WHERE client_id=?", (cli1["id"],)).fetchall()
        cart = conn.execute("SELECT * FROM carteira_items WHERE client_id=?", (cli1["id"],)).fetchall()

    check(len(ops) == 1 and ops[0]["estrutura"] == "Trava", "operacao importada corretamente")
    check(len(cart) == 1 and cart[0]["quantidade"] == 150.0, "carteira soma quantidades duplicadas (100+50=150)")

    client.post("/logout")

    # bob nao ve o cliente CLI1 da alice
    login(client, "bob", "bobpass")
    resp = client.get("/clientes")
    check(b"CLI1" not in resp.data, "bob nao ve cliente CLI1 da alice na lista")
    resp = client.get(f"/clientes/{cli1['id']}")
    check(resp.status_code == 404, "bob nao consegue abrir direto o cliente da alice por id -> 404")
    client.post("/logout")

    print(f"\n{pass_count} passed, {fail_count} failed")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
