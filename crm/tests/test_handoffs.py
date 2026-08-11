import datetime as dt
import uuid

from sqlalchemy import select

from app import models
from tests.conftest import SENHA_PADRAO_TESTE, criar_trader, login


def usuario(db_session, username):
    return db_session.execute(select(models.User).where(models.User.username == username)).scalar_one()


def criar_cliente_via_db(db_session, trader_id, codigo=None):
    codigo = codigo or f"HAND-{uuid.uuid4().hex[:8]}"
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


class TestCriacaoDeHandoff:
    def test_head_mesa_cria_handoff_de_carteira_inteira(self, client, db_session):
        origem = criar_trader(db_session, "Origem A")
        destino = criar_trader(db_session, "Destino A")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        resp = client.post(
            "/handoffs/novo",
            data={
                "trader_origem_id": origem.id,
                "trader_destino_id": destino.id,
                "cliente_id": "",
                "motivo": "ferias",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        handoff = db_session.execute(select(models.Handoff).order_by(models.Handoff.id.desc())).scalars().first()
        assert handoff.cliente_id is None
        assert handoff.trader_origem_id == origem.id
        assert handoff.trader_destino_id == destino.id
        assert handoff.autorizado_por_id == usuario(db_session, "head_mesa").id
        assert handoff.ativo() is True

        client.post("/logout")
        login(client, destino.username, SENHA_PADRAO_TESTE)
        lista = client.get("/clientes")
        assert cliente.codigo in lista.text

        detalhe = client.get(f"/clientes/{cliente.id}", follow_redirects=False)
        assert detalhe.status_code == 200

    def test_trader_nao_pode_criar_handoff(self, client, db_session):
        login(client, "trader1")
        resp = client.get("/handoffs", follow_redirects=False)
        assert resp.status_code == 303  # Forbidden -> redireciona

    def test_origem_igual_destino_e_rejeitado(self, client, db_session):
        origem = criar_trader(db_session, "Mesma Pessoa")
        login(client, "head_mesa")
        resp = client.post(
            "/handoffs/novo",
            data={"trader_origem_id": origem.id, "trader_destino_id": origem.id, "cliente_id": ""},
        )
        assert resp.status_code == 400
        assert "diferentes" in resp.text.lower()


class TestVisibilidadeEEncerramento:
    def test_handoff_de_cliente_especifico_nao_libera_o_resto_da_carteira(self, client, db_session):
        origem = criar_trader(db_session, "Origem B")
        destino = criar_trader(db_session, "Destino B")
        cliente_compartilhado = criar_cliente_via_db(db_session, origem.id)
        outro_cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        client.post(
            "/handoffs/novo",
            data={
                "trader_origem_id": origem.id,
                "trader_destino_id": destino.id,
                "cliente_id": str(cliente_compartilhado.id),
            },
        )
        client.post("/logout")

        login(client, destino.username, SENHA_PADRAO_TESTE)
        lista = client.get("/clientes")
        assert cliente_compartilhado.codigo in lista.text
        assert outro_cliente.codigo not in lista.text

    def test_encerrar_handoff_revoga_acesso_imediatamente(self, client, db_session):
        origem = criar_trader(db_session, "Origem C")
        destino = criar_trader(db_session, "Destino C")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        client.post(
            "/handoffs/novo",
            data={"trader_origem_id": origem.id, "trader_destino_id": destino.id, "cliente_id": str(cliente.id)},
        )
        handoff = db_session.execute(select(models.Handoff).order_by(models.Handoff.id.desc())).scalars().first()

        client.post(f"/handoffs/{handoff.id}/encerrar", follow_redirects=False)
        db_session.refresh(handoff)
        assert handoff.ativo() is False
        client.post("/logout")

        login(client, destino.username, SENHA_PADRAO_TESTE)
        resp = client.get(f"/clientes/{cliente.id}", follow_redirects=False)
        assert resp.status_code == 303  # acesso revogado -> Forbidden

    def test_handoff_com_fim_no_passado_nao_concede_acesso(self, client, db_session):
        origem = criar_trader(db_session, "Origem D")
        destino = criar_trader(db_session, "Destino D")
        cliente = criar_cliente_via_db(db_session, origem.id)

        handoff = models.Handoff(
            trader_origem_id=origem.id,
            trader_destino_id=destino.id,
            cliente_id=cliente.id,
            autorizado_por_id=usuario(db_session, "head_mesa").id,
            inicio=dt.datetime.utcnow() - dt.timedelta(days=10),
            fim=dt.datetime.utcnow() - dt.timedelta(days=1),
        )
        db_session.add(handoff)
        db_session.commit()

        login(client, destino.username, SENHA_PADRAO_TESTE)
        resp = client.get(f"/clientes/{cliente.id}", follow_redirects=False)
        assert resp.status_code == 303


class TestMotivoDeAcessoRegistrado:
    def test_acesso_via_handoff_e_registrado_com_motivo_handoff(self, client, db_session):
        origem = criar_trader(db_session, "Origem E")
        destino = criar_trader(db_session, "Destino E")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        client.post(
            "/handoffs/novo",
            data={"trader_origem_id": origem.id, "trader_destino_id": destino.id, "cliente_id": str(cliente.id)},
        )
        client.post("/logout")

        login(client, destino.username, SENHA_PADRAO_TESTE)
        client.get(f"/clientes/{cliente.id}")

        log = db_session.execute(
            select(models.AccessLog)
            .where(models.AccessLog.cliente_id == cliente.id, models.AccessLog.user_id == destino.id)
            .order_by(models.AccessLog.id.desc())
        ).scalars().first()
        assert log is not None
        assert log.motivo == "HANDOFF"

    def test_acesso_do_titular_e_registrado_com_motivo_titular(self, client, db_session):
        origem = criar_trader(db_session, "Origem F")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.get(f"/clientes/{cliente.id}")

        log = db_session.execute(
            select(models.AccessLog)
            .where(models.AccessLog.cliente_id == cliente.id, models.AccessLog.user_id == origem.id)
            .order_by(models.AccessLog.id.desc())
        ).scalars().first()
        assert log.motivo == "TITULAR"

    def test_acesso_do_compliance_e_registrado_com_motivo_compliance(self, client, db_session):
        origem = criar_trader(db_session, "Origem G")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "compliance")
        client.get(f"/clientes/{cliente.id}")

        log = db_session.execute(
            select(models.AccessLog)
            .where(
                models.AccessLog.cliente_id == cliente.id,
                models.AccessLog.user_id == usuario(db_session, "compliance").id,
            )
            .order_by(models.AccessLog.id.desc())
        ).scalars().first()
        assert log.motivo == "COMPLIANCE"
