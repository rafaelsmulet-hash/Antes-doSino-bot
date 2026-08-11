import datetime as dt
import json
import uuid

import pytest
from sqlalchemy import select

from app import models
from scripts.importar_posicoes import MAPEAMENTO_PADRAO, executar_importacao


def criar_cliente(db_session, trader_id, codigo=None):
    codigo = codigo or f"IMP-{uuid.uuid4().hex[:8]}"
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


def trader1_id(db_session):
    return db_session.execute(select(models.User).where(models.User.username == "trader1")).scalar_one().id


def escrever_arquivo(tmp_path, conteudo, nome="posicao.csv"):
    caminho = tmp_path / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


class TestImportacaoBasica:
    def test_importa_posicoes_validas_e_calcula_valor_mercado_e_pnl(self, db_session, tmp_path):
        cliente = criar_cliente(db_session, trader1_id(db_session))
        conteudo = (
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;1000,00;28,50;30,00\n"
        )
        arquivo = escrever_arquivo(tmp_path, conteudo)

        execucao = executar_importacao(db_session, arquivo, MAPEAMENTO_PADRAO, dt.date(2026, 8, 11))

        assert execucao.total_importado == 1
        assert execucao.total_rejeitado == 0

        posicao = db_session.execute(
            select(models.Posicao).where(models.Posicao.cliente_id == cliente.id, models.Posicao.ticker == "PETR4")
        ).scalar_one()
        assert posicao.quantidade == pytest.approx(1000.0)
        assert posicao.valor_mercado == pytest.approx(30000.0)
        assert posicao.pnl_nao_realizado == pytest.approx(1500.0)
        assert posicao.data_referencia == dt.date(2026, 8, 11)

        historico = db_session.execute(
            select(models.PosicaoHistorico).where(
                models.PosicaoHistorico.cliente_id == cliente.id, models.PosicaoHistorico.ticker == "PETR4"
            )
        ).scalars().all()
        assert len(historico) == 1

    def test_cliente_nao_cadastrado_e_rejeitado_sem_derrubar_importacao(self, db_session, tmp_path):
        cliente = criar_cliente(db_session, trader1_id(db_session))
        conteudo = (
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;100,00;28,50;30,00\n"
            "CODIGO-INEXISTENTE;VALE3;ACAO;50,00;65,00;67,00\n"
        )
        arquivo = escrever_arquivo(tmp_path, conteudo)

        execucao = executar_importacao(db_session, arquivo, MAPEAMENTO_PADRAO, dt.date(2026, 8, 11))

        assert execucao.total_importado == 1
        assert execucao.total_rejeitado == 1

        rejeitadas = db_session.execute(
            select(models.ImportacaoLinhaRejeitada).where(models.ImportacaoLinhaRejeitada.execucao_id == execucao.id)
        ).scalars().all()
        assert len(rejeitadas) == 1
        assert "CODIGO-INEXISTENTE" in rejeitadas[0].motivo
        conteudo_salvo = json.loads(rejeitadas[0].conteudo)
        assert conteudo_salvo["ticker"] == "VALE3"

    def test_linha_malformada_do_parser_tambem_e_registrada(self, db_session, tmp_path):
        cliente = criar_cliente(db_session, trader1_id(db_session))
        conteudo = (
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;N/D;28,50;30,00\n"
        )
        arquivo = escrever_arquivo(tmp_path, conteudo)

        execucao = executar_importacao(db_session, arquivo, MAPEAMENTO_PADRAO, dt.date(2026, 8, 11))

        assert execucao.total_importado == 0
        assert execucao.total_rejeitado == 1
        assert execucao.total_lido == 1

    def test_rerun_no_mesmo_dia_atualiza_corrente_mas_nao_duplica_historico(self, db_session, tmp_path):
        cliente = criar_cliente(db_session, trader1_id(db_session))
        snapshot = dt.date(2026, 8, 11)

        arquivo1 = escrever_arquivo(
            tmp_path,
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;1000,00;28,50;30,00\n",
            nome="posicao1.csv",
        )
        executar_importacao(db_session, arquivo1, MAPEAMENTO_PADRAO, snapshot, data_snapshot=snapshot)

        arquivo2 = escrever_arquivo(
            tmp_path,
            "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
            f"{cliente.codigo};PETR4;ACAO;1000,00;28,50;31,50\n",  # preco atualizado no fechamento
            nome="posicao2.csv",
        )
        executar_importacao(db_session, arquivo2, MAPEAMENTO_PADRAO, snapshot, data_snapshot=snapshot)

        posicoes = db_session.execute(
            select(models.Posicao).where(models.Posicao.cliente_id == cliente.id, models.Posicao.ticker == "PETR4")
        ).scalars().all()
        assert len(posicoes) == 1
        assert posicoes[0].preco_atual == pytest.approx(31.50)

        historico = db_session.execute(
            select(models.PosicaoHistorico).where(
                models.PosicaoHistorico.cliente_id == cliente.id,
                models.PosicaoHistorico.ticker == "PETR4",
                models.PosicaoHistorico.data_snapshot == snapshot,
            )
        ).scalars().all()
        assert len(historico) == 1  # nao duplicou o snapshot do dia

    def test_execucao_registra_totais_mesmo_com_arquivo_totalmente_vazio_de_dados(self, db_session, tmp_path):
        arquivo = escrever_arquivo(
            tmp_path, "cod_cliente;cod_ativo;tipo_ativo;quantidade;preco_medio;preco_atual\n"
        )
        execucao = executar_importacao(db_session, arquivo, MAPEAMENTO_PADRAO, dt.date(2026, 8, 11))
        assert execucao.total_lido == 0
        assert execucao.total_importado == 0
        assert execucao.total_rejeitado == 0
