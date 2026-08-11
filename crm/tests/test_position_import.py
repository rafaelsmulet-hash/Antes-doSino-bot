import datetime as dt

import pytest

from domain.position_import import ColumnMapping, PositionImportError, parse_position_file


def linhas(*rows):
    return list(rows)


def test_parse_basico_formato_br():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente",
        ticker="cod_ativo",
        tipo_ativo="tipo",
        quantidade="qtd",
        preco_medio="pm",
        preco_atual="preco_atual",
        delimitador=";",
        separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm;preco_atual\n",
        "CLI001;PETR4;ACAO;1.000,00;28,50;30,10\n",
        "CLI001;VALE3;ACAO;500,00;65,00;67,25\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    assert len(resultado.posicoes) == 2
    assert resultado.rejeitadas == []
    assert resultado.total_lido == 2
    p1 = resultado.posicoes[0]
    assert p1.cliente_codigo == "CLI001"
    assert p1.ticker == "PETR4"
    assert p1.tipo_ativo == "ACAO"
    assert p1.quantidade == pytest.approx(1000.0)
    assert p1.preco_medio == pytest.approx(28.50)
    assert p1.preco_atual == pytest.approx(30.10)
    assert p1.data_referencia == dt.date(2026, 8, 11)
    assert p1.numero_linha == 2


def test_mapeamento_de_colunas_customizado_para_outro_formato_de_backoffice():
    # Simula um backoffice diferente, com nomes de coluna totalmente distintos
    # e separador de campo por virgula em vez de ponto e virgula.
    mapping = ColumnMapping(
        cliente_codigo="ClientCode",
        ticker="Symbol",
        tipo_ativo="AssetType",
        quantidade="Qty",
        preco_medio="AvgPrice",
        delimitador=",",
        separador_decimal=".",
    )
    arquivo = linhas(
        "ClientCode,Symbol,AssetType,Qty,AvgPrice\n",
        "CLI002,MXRF11,FII,200,10.5\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    assert len(resultado.posicoes) == 1
    assert resultado.posicoes[0].ticker == "MXRF11"
    assert resultado.posicoes[0].quantidade == pytest.approx(200.0)
    assert resultado.posicoes[0].preco_medio == pytest.approx(10.5)


def test_coluna_de_data_referencia_no_proprio_arquivo():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente",
        ticker="cod_ativo",
        tipo_ativo="tipo",
        quantidade="qtd",
        preco_medio="pm",
        data_referencia="data",
        separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm;data\n",
        "CLI001;PETR4;ACAO;100,00;28,50;11/08/2026\n",
    )
    resultado = parse_position_file(arquivo, mapping)
    assert resultado.posicoes[0].data_referencia == dt.date(2026, 8, 11)


def test_linhas_vazias_sao_ignoradas():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm\n",
        "CLI001;PETR4;ACAO;100,00;28,50\n",
        ";;;;\n",
        "\n",
        "CLI001;VALE3;ACAO;50,00;65,00\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    assert len(resultado.posicoes) == 2
    assert resultado.rejeitadas == []


def test_coluna_obrigatoria_ausente_gera_erro_estrutural():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd\n",  # falta a coluna pm
        "CLI001;PETR4;ACAO;100\n",
    )
    with pytest.raises(PositionImportError, match="pm"):
        parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))


def test_valor_numerico_invalido_vira_linha_rejeitada_sem_derrubar_importacao():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm\n",
        "CLI001;PETR4;ACAO;100,00;28,50\n",
        "CLI001;VALE3;ACAO;N/D;65,00\n",
        "CLI001;ITUB4;ACAO;200,00;30,00\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    # As linhas validas (1a e 3a de dados) devem ser importadas mesmo com
    # uma linha invalida no meio -- a importacao do dia nao pode parar por
    # causa de uma unica linha suja.
    assert len(resultado.posicoes) == 2
    assert [p.ticker for p in resultado.posicoes] == ["PETR4", "ITUB4"]
    assert len(resultado.rejeitadas) == 1
    rejeitada = resultado.rejeitadas[0]
    assert rejeitada.numero_linha == 3
    assert "qtd" in rejeitada.motivo
    assert rejeitada.conteudo["cod_ativo"] == "VALE3"


def test_cliente_ou_ticker_ausente_vira_linha_rejeitada():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm\n",
        ";PETR4;ACAO;100,00;28,50\n",
        "CLI001;VALE3;ACAO;50,00;65,00\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    assert len(resultado.posicoes) == 1
    assert len(resultado.rejeitadas) == 1
    assert "obrigatorios" in resultado.rejeitadas[0].motivo


def test_data_invalida_na_coluna_do_arquivo_vira_linha_rejeitada():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", data_referencia="data", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm;data\n",
        "CLI001;PETR4;ACAO;100,00;28,50;32/13/2026\n",
    )
    resultado = parse_position_file(arquivo, mapping)
    assert resultado.posicoes == []
    assert len(resultado.rejeitadas) == 1
    assert "data invalida" in resultado.rejeitadas[0].motivo


def test_multiplas_linhas_invalidas_sao_todas_reportadas():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm\n",
        "CLI001;PETR4;ACAO;N/D;28,50\n",
        "CLI001;VALE3;ACAO;100,00;N/D\n",
        ";ITUB4;ACAO;100,00;30,00\n",
    )
    resultado = parse_position_file(arquivo, mapping, data_referencia_padrao=dt.date(2026, 8, 11))
    assert resultado.posicoes == []
    assert [r.numero_linha for r in resultado.rejeitadas] == [2, 3, 4]
    assert resultado.total_lido == 3


def test_sem_data_referencia_e_sem_default_gera_erro_estrutural():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm", separador_decimal=",",
    )
    arquivo = linhas(
        "cod_cliente;cod_ativo;tipo;qtd;pm\n",
        "CLI001;PETR4;ACAO;100,00;28,50\n",
    )
    with pytest.raises(PositionImportError, match="data de referencia"):
        parse_position_file(arquivo, mapping, data_referencia_padrao=None)


def test_arquivo_sem_cabecalho_gera_erro():
    mapping = ColumnMapping(
        cliente_codigo="cod_cliente", ticker="cod_ativo", tipo_ativo="tipo",
        quantidade="qtd", preco_medio="pm",
    )
    with pytest.raises(PositionImportError):
        parse_position_file([], mapping, data_referencia_padrao=dt.date(2026, 8, 11))
