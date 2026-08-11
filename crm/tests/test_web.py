import datetime as dt
import uuid

from sqlalchemy import select

from app import models
from tests.conftest import login


def codigo_unico(prefixo="CLI"):
    return f"{prefixo}-{uuid.uuid4().hex[:8]}"


def criar_cliente(client, codigo=None, trader_titular_id=None, nome="Cliente Teste"):
    codigo = codigo or codigo_unico()
    resp = client.post(
        "/clientes/novo",
        data={
            "codigo": codigo,
            "nome": nome,
            "tipo": "PF",
            "book": "varejo",
            "perfil_risco": "moderado",
            "trader_titular_id": trader_titular_id,
            "tags": "bancos",
            "produtos": "acoes,opcoes",
        },
        follow_redirects=False,
    )
    return resp, codigo


class TestAutenticacao:
    def test_login_com_credenciais_invalidas(self, client):
        resp = client.post(
            "/login", data={"username": "trader1", "password": "senha_errada", "next": "/"}
        )
        assert resp.status_code == 401
        assert "invalidos" in resp.text.lower()

    def test_login_com_credenciais_validas_redireciona(self, client):
        resp = login(client)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_acesso_sem_sessao_redireciona_para_login(self, client):
        resp = client.get("/clientes", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")

    def test_logout_encerra_sessao(self, client):
        login(client)
        assert client.get("/clientes").status_code == 200
        client.post("/logout", follow_redirects=False)
        resp = client.get("/clientes", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")


class TestVisibilidadeDeCarteira:
    def test_trader_ve_seu_proprio_cliente(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()

        resp, codigo = criar_cliente(client, trader_titular_id=trader1.id)
        assert resp.status_code == 303

        lista = client.get("/clientes")
        assert codigo in lista.text

    def test_outro_trader_nao_ve_cliente_alheio_sem_compartilhamento(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        _, codigo = criar_cliente(client, trader_titular_id=trader1.id)

        client.post("/logout")
        login(client, "trader2")
        lista = client.get("/clientes")
        assert codigo not in lista.text

    def test_compartilhamento_explicito_libera_visibilidade(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        trader2 = db_session.execute(
            select(models.User).where(models.User.username == "trader2")
        ).scalar_one()

        resp, codigo = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        db_session.add(models.ClienteCompartilhamento(cliente_id=cliente_id, user_id=trader2.id))
        db_session.commit()

        client.post("/logout")
        login(client, "trader2")
        lista = client.get("/clientes")
        assert codigo in lista.text

    def test_head_mesa_ve_todos_os_clientes_e_gera_trilha_de_auditoria(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, codigo = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        client.post("/logout")
        login(client, "head_mesa")

        logs_antes = db_session.execute(
            select(models.AccessLog).where(models.AccessLog.cliente_id == cliente_id)
        ).scalars().all()

        detalhe = client.get(f"/clientes/{cliente_id}")
        assert detalhe.status_code == 200
        assert codigo in detalhe.text

        db_session.expire_all()
        logs_depois = db_session.execute(
            select(models.AccessLog).where(models.AccessLog.cliente_id == cliente_id)
        ).scalars().all()
        assert len(logs_depois) == len(logs_antes) + 1
        assert logs_depois[-1].acao == "visualizou_ficha_cliente"

    def test_trader_nao_pode_abrir_ficha_de_cliente_alheio(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, _ = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        client.post("/logout")
        login(client, "trader2")
        detalhe = client.get(f"/clientes/{cliente_id}", follow_redirects=False)
        assert detalhe.status_code == 303  # Forbidden -> redireciona


class TestInteracaoAppendOnly:
    def test_registrar_interacao_e_ela_aparece_na_ficha_do_cliente(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, _ = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        resp_interacao = client.post(
            "/interacoes/nova",
            data={
                "cliente_id": cliente_id,
                "canal": "telefone",
                "resumo": "Cliente perguntou sobre PETR4, tom comprador.",
                "tickers_mencionados": "PETR4",
                "sentimento": "comprador",
                "follow_up_data": "",
            },
            follow_redirects=False,
        )
        assert resp_interacao.status_code == 303

        detalhe = client.get(f"/clientes/{cliente_id}")
        assert "PETR4" in detalhe.text
        assert "comprador" in detalhe.text

    def test_nao_existe_rota_de_edicao_ou_delecao_de_interacao(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, _ = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])
        client.post(
            "/interacoes/nova",
            data={"cliente_id": cliente_id, "canal": "telefone", "resumo": "Registro original."},
        )
        interacao = db_session.execute(
            select(models.Interacao).where(models.Interacao.cliente_id == cliente_id)
        ).scalars().first()

        # Nao existe rota de edicao/delecao por id -- append-only por design.
        assert client.put(f"/interacoes/{interacao.id}").status_code == 404
        assert client.delete(f"/interacoes/{interacao.id}").status_code == 404

    def test_correcao_cria_nova_linha_e_preserva_original(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, _ = criar_cliente(client, trader_titular_id=trader1.id)
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        client.post(
            "/interacoes/nova",
            data={"cliente_id": cliente_id, "canal": "telefone", "resumo": "Resumo com erro de digitacao."},
        )
        original = db_session.execute(
            select(models.Interacao).where(models.Interacao.cliente_id == cliente_id)
        ).scalars().first()
        resumo_original = original.resumo

        client.post(
            "/interacoes/nova",
            data={
                "cliente_id": cliente_id,
                "canal": "telefone",
                "resumo": "Correcao: resumo revisado sem erro.",
                "corrige_interacao_id": original.id,
            },
        )

        db_session.expire_all()
        todas = db_session.execute(
            select(models.Interacao).where(models.Interacao.cliente_id == cliente_id)
        ).scalars().all()
        assert len(todas) == 2
        original_recarregado = next(i for i in todas if i.id == original.id)
        assert original_recarregado.resumo == resumo_original  # nunca editado
        correcao = next(i for i in todas if i.id != original.id)
        assert correcao.corrige_interacao_id == original.id


class TestDashboard:
    def test_followup_pendente_aparece_no_dashboard(self, client, db_session):
        login(client, "trader1")
        trader1 = db_session.execute(
            select(models.User).where(models.User.username == "trader1")
        ).scalar_one()
        resp, codigo = criar_cliente(client, trader_titular_id=trader1.id, nome="Cliente Followup")
        cliente_id = int(resp.headers["location"].rsplit("/", 1)[-1])

        client.post(
            "/interacoes/nova",
            data={
                "cliente_id": cliente_id,
                "canal": "presencial",
                "resumo": "Combinar retorno.",
                "follow_up_data": dt.date.today().isoformat(),
            },
        )

        dash = client.get("/")
        assert "Cliente Followup" in dash.text

    def test_dashboard_requer_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")
