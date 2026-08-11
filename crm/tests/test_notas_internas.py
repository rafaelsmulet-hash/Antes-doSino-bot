import datetime as dt
import uuid

from sqlalchemy import select

from app import models
from tests.conftest import SENHA_PADRAO_TESTE, criar_trader, login


def criar_cliente_via_db(db_session, trader_id, codigo=None):
    codigo = codigo or f"NOTA-{uuid.uuid4().hex[:8]}"
    cliente = models.Cliente(
        codigo=codigo, nome=f"Cliente {codigo}", tipo="PF", trader_titular_id=trader_id, data_cadastro=dt.date.today()
    )
    db_session.add(cliente)
    db_session.commit()
    db_session.refresh(cliente)
    return cliente


class TestNotasInternas:
    def test_titular_cria_nota_e_ela_aparece_na_ficha(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, origem.username, SENHA_PADRAO_TESTE)
        resp = client.post(
            f"/clientes/{cliente.id}/notas", data={"texto": "Cliente pediu para nao ligar antes das 10h."}
        )
        assert resp.status_code in (200, 303)

        detalhe = client.get(f"/clientes/{cliente.id}")
        assert "nao ligar antes das 10h" in detalhe.text
        assert "nao enviar ao cliente" in detalhe.text

    def test_nota_e_append_only_sem_rota_de_edicao_ou_delecao(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas 2")
        cliente = criar_cliente_via_db(db_session, origem.id)
        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.post(f"/clientes/{cliente.id}/notas", data={"texto": "Nota original."})

        nota = db_session.execute(
            select(models.NotaInterna).where(models.NotaInterna.cliente_id == cliente.id)
        ).scalars().first()
        assert client.put(f"/clientes/{cliente.id}/notas/{nota.id}").status_code == 404
        assert client.delete(f"/clientes/{cliente.id}/notas/{nota.id}").status_code == 404

    def test_outro_trader_sem_relacao_nao_ve_nem_cria_nota(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas 3")
        outro = criar_trader(db_session, "Outro Trader Notas")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, outro.username, SENHA_PADRAO_TESTE)
        resp = client.post(
            f"/clientes/{cliente.id}/notas", data={"texto": "Tentativa indevida."}, follow_redirects=False
        )
        assert resp.status_code == 303  # Forbidden -> redireciona, nota nao deve ser criada

        qtd_notas = db_session.execute(
            select(models.NotaInterna).where(models.NotaInterna.cliente_id == cliente.id)
        ).scalars().all()
        assert qtd_notas == []

    def test_handoff_ativo_libera_criacao_de_nota_para_trader_destino(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas 4")
        destino = criar_trader(db_session, "Cobertura Notas 4")
        cliente = criar_cliente_via_db(db_session, origem.id)

        login(client, "head_mesa")
        client.post(
            "/handoffs/novo",
            data={"trader_origem_id": origem.id, "trader_destino_id": destino.id, "cliente_id": str(cliente.id)},
        )
        client.post("/logout")

        login(client, destino.username, SENHA_PADRAO_TESTE)
        resp = client.post(f"/clientes/{cliente.id}/notas", data={"texto": "Nota durante cobertura."})
        assert resp.status_code in (200, 303)

        notas = db_session.execute(
            select(models.NotaInterna).where(models.NotaInterna.cliente_id == cliente.id)
        ).scalars().all()
        assert len(notas) == 1
        assert notas[0].autor_id == destino.id

    def test_head_mesa_ve_nota_de_qualquer_cliente(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas 5")
        cliente = criar_cliente_via_db(db_session, origem.id)
        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.post(f"/clientes/{cliente.id}/notas", data={"texto": "Nota visivel para head_mesa."})
        client.post("/logout")

        login(client, "head_mesa")
        detalhe = client.get(f"/clientes/{cliente.id}")
        assert "Nota visivel para head_mesa" in detalhe.text

    def test_texto_vazio_nao_cria_nota(self, client, db_session):
        origem = criar_trader(db_session, "Titular Notas 6")
        cliente = criar_cliente_via_db(db_session, origem.id)
        login(client, origem.username, SENHA_PADRAO_TESTE)
        client.post(f"/clientes/{cliente.id}/notas", data={"texto": "   "})

        notas = db_session.execute(
            select(models.NotaInterna).where(models.NotaInterna.cliente_id == cliente.id)
        ).scalars().all()
        assert notas == []
