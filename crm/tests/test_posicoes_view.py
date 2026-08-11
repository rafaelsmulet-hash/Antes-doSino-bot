import datetime as dt
import uuid

from sqlalchemy import select

from app import models
from scripts.importar_posicoes import MAPEAMENTO_PADRAO, executar_importacao
from tests.conftest import login


def criar_cliente_via_db(db_session, trader_id, codigo=None):
    codigo = codigo or f"POS-{uuid.uuid4().hex[:8]}"
    cliente = models.Cliente(
        codigo=codigo,
        nome=f"Cliente {codigo}",
        tipo="PF",
        trader_titular_id=trader_id,
        data_cadastro=dt.date.today(),
    )
    db_session.add(cliente)
    db_session.commit()
    db_session.refresh(cliente)
    return cliente


def trader1(db_session):
    return db_session.execute(select(models.User).where(models.User.username == "trader1")).scalar_one()


class TestTelaDePosicao:
    def test_pagina_sem_posicao_importada(self, client, db_session):
        login(client, "trader1")
        cliente = criar_cliente_via_db(db_session, trader1(db_session).id)
        resp = client.get(f"/clientes/{cliente.id}/posicao")
        assert resp.status_code == 200
        assert "Nenhuma posicao importada" in resp.text

    def test_pagina_mostra_acoes_e_patrimonio(self, client, db_session, tmp_path):
        login(client, "trader1")
        cliente = criar_cliente_via_db(db_session, trader1(db_session).id)

        arquivo = tmp_path / "posicao.csv"
        arquivo.write_text(
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;1000,00;28,50;30,00\n",
            encoding="utf-8",
        )
        executar_importacao(db_session, arquivo, MAPEAMENTO_PADRAO, dt.date(2026, 8, 11))

        resp = client.get(f"/clientes/{cliente.id}/posicao")
        assert resp.status_code == 200
        assert "PETR4" in resp.text
        assert "30000.00" in resp.text  # patrimonio total

    def test_pagina_classifica_trava_de_alta_call_e_gera_alerta_de_vencimento(self, client, db_session):
        login(client, "trader1")
        cliente = criar_cliente_via_db(db_session, trader1(db_session).id)
        vencimento = dt.date.today() + dt.timedelta(days=2)

        db_session.add_all(
            [
                models.PosicaoDerivativo(
                    cliente_id=cliente.id,
                    ticker_ativo_objeto="PETR4",
                    tipo_derivativo="CALL",
                    codigo_serie="PETRJ30",
                    direcao="COMPRADO",
                    quantidade=100,
                    strike=30,
                    data_vencimento=vencimento,
                    preco_medio_pago=3,
                    data_referencia=dt.date.today(),
                ),
                models.PosicaoDerivativo(
                    cliente_id=cliente.id,
                    ticker_ativo_objeto="PETR4",
                    tipo_derivativo="CALL",
                    codigo_serie="PETRJ35",
                    direcao="VENDIDO",
                    quantidade=100,
                    strike=35,
                    data_vencimento=vencimento,
                    preco_medio_pago=1,
                    data_referencia=dt.date.today(),
                ),
            ]
        )
        db_session.commit()

        resp = client.get(f"/clientes/{cliente.id}/posicao")
        assert resp.status_code == 200
        assert "TRAVA_ALTA_CALL" in resp.text
        assert "vence em breve" in resp.text  # vencimento_proximo destacado

        dashboard = client.get("/")
        assert cliente.nome in dashboard.text
        assert "VENCIMENTO_PROXIMO_SEM_ROLAGEM" not in dashboard.text  # mensagem, nao o codigo do tipo
        assert "possivel rolagem pendente" in dashboard.text

    def test_outro_trader_nao_acessa_posicao_de_cliente_alheio(self, client, db_session):
        login(client, "trader1")
        cliente = criar_cliente_via_db(db_session, trader1(db_session).id)
        client.post("/logout")
        login(client, "trader2")
        resp = client.get(f"/clientes/{cliente.id}/posicao", follow_redirects=False)
        assert resp.status_code == 303

    def test_head_mesa_acesso_a_posicao_gera_trilha_de_auditoria(self, client, db_session):
        login(client, "trader1")
        cliente = criar_cliente_via_db(db_session, trader1(db_session).id)
        client.post("/logout")

        login(client, "head_mesa")
        resp = client.get(f"/clientes/{cliente.id}/posicao")
        assert resp.status_code == 200

        logs = db_session.execute(
            select(models.AccessLog).where(
                models.AccessLog.cliente_id == cliente.id,
                models.AccessLog.acao == "visualizou_posicao_cliente",
            )
        ).scalars().all()
        assert len(logs) == 1
