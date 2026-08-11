import csv
import datetime as dt
import io
import uuid

from sqlalchemy import select

from app import models
from tests.conftest import SENHA_PADRAO_TESTE, criar_trader, login


def criar_cliente_via_db(db_session, trader_id, codigo=None):
    codigo = codigo or f"AUD-{uuid.uuid4().hex[:8]}"
    cliente = models.Cliente(
        codigo=codigo, nome=f"Cliente {codigo}", tipo="PF", trader_titular_id=trader_id, data_cadastro=dt.date.today()
    )
    db_session.add(cliente)
    db_session.commit()
    db_session.refresh(cliente)
    return cliente


class TestAcessoAoRelatorio:
    def test_trader_nao_acessa_relatorio_de_auditoria(self, client, db_session):
        login(client, "trader1")
        resp = client.get("/auditoria", follow_redirects=False)
        assert resp.status_code == 303

    def test_compliance_acessa_relatorio(self, client, db_session):
        login(client, "compliance")
        resp = client.get("/auditoria")
        assert resp.status_code == 200
        assert "Relatorio de auditoria" in resp.text


class TestConteudoDoRelatorio:
    def test_interacao_aparece_no_relatorio_e_acesso_titular_nao_conta_como_fora_da_carteira(
        self, client, db_session
    ):
        origem = criar_trader(db_session, "Titular Auditoria")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.post(
            f"/interacoes/nova",
            data={"cliente_id": cliente.id, "canal": "telefone", "resumo": "Discutimos alocacao em renda variavel."},
        )
        client.get(f"/clientes/{cliente.id}")  # acesso do titular -- nao deve aparecer como "fora da carteira"
        client.post("/logout")

        login(client, "compliance")
        resp = client.get(f"/auditoria?cliente_id={cliente.id}")
        assert "Discutimos alocacao" in resp.text

        acessos = db_session.execute(
            select(models.AccessLog).where(models.AccessLog.cliente_id == cliente.id, models.AccessLog.motivo == "TITULAR")
        ).scalars().all()
        assert len(acessos) >= 1
        # o motivo TITULAR nao deve aparecer na secao "fora da carteira titular"
        assert "TITULAR</span>" not in resp.text

    def test_acesso_de_head_mesa_aparece_como_fora_da_carteira_titular(self, client, db_session):
        origem = criar_trader(db_session, "Titular Auditoria 2")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        client.get(f"/clientes/{cliente.id}")
        resp = client.get(f"/auditoria?cliente_id={cliente.id}")
        assert "HEAD_MESA" in resp.text

    def test_filtro_por_trader_restringe_interacoes(self, client, db_session):
        trader_a = criar_trader(db_session, "Trader Filtro A")
        trader_b = criar_trader(db_session, "Trader Filtro B")
        cliente_a = criar_cliente_via_db(db_session, trader_a.id)
        cliente_b = criar_cliente_via_db(db_session, trader_b.id)

        login(client, trader_a.username, SENHA_PADRAO_TESTE)
        client.post(
            "/interacoes/nova",
            data={"cliente_id": cliente_a.id, "canal": "telefone", "resumo": "Interacao unica do trader A."},
        )
        client.post("/logout")

        login(client, trader_b.username, SENHA_PADRAO_TESTE)
        client.post(
            "/interacoes/nova",
            data={"cliente_id": cliente_b.id, "canal": "telefone", "resumo": "Interacao unica do trader B."},
        )
        client.post("/logout")

        login(client, "compliance")
        resp = client.get(f"/auditoria?trader_id={trader_a.id}")
        assert "Interacao unica do trader A" in resp.text
        assert "Interacao unica do trader B" not in resp.text


class TestExportacaoCsv:
    def test_export_csv_contem_interacoes_e_acessos(self, client, db_session):
        origem = criar_trader(db_session, "Titular Auditoria CSV")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.post(
            "/interacoes/nova",
            data={"cliente_id": cliente.id, "canal": "chat_interno", "resumo": "Nota para o CSV de auditoria."},
        )
        client.post("/logout")

        login(client, "head_mesa")
        client.get(f"/clientes/{cliente.id}")

        resp = client.get(f"/auditoria/export.csv?cliente_id={cliente.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]

        linhas = list(csv.reader(io.StringIO(resp.text), delimiter=";"))
        cabecalho = linhas[0]
        assert cabecalho[0] == "tipo_registro"
        tipos = [linha[0] for linha in linhas[1:]]
        assert "INTERACAO" in tipos
        assert "ACESSO_FORA_TITULAR" in tipos

    def test_trader_nao_acessa_export_csv(self, client, db_session):
        login(client, "trader1")
        resp = client.get("/auditoria/export.csv", follow_redirects=False)
        assert resp.status_code == 303
