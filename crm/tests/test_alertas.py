import datetime as dt

from domain.alertas import (
    ALERTA_CONCENTRACAO,
    ALERTA_RISCO_EXERCICIO,
    ALERTA_VENCIMENTO_PROXIMO,
    ItemPosicaoDerivativo,
    detectar_concentracao,
    detectar_risco_exercicio,
    detectar_vencimento_proximo_sem_rolagem,
)
from domain.options_engine import (
    CALL,
    COMPRADO,
    POSICAO_SIMPLES,
    PUT,
    TRAVA_ALTA_CALL,
    VENDIDO,
    EstruturaClassificada,
    OptionLeg,
)


def opcao_simples(ticker, direcao, tipo, strike, dias, vencimento):
    leg = OptionLeg(
        ref_id=1, tipo_derivativo=tipo, direcao=direcao, quantidade=100, strike=strike, data_vencimento=vencimento
    )
    estrutura = EstruturaClassificada(
        tipo=POSICAO_SIMPLES, pernas=[leg], quantidade=100, dias_ate_vencimento=dias
    )
    return ItemPosicaoDerivativo(ticker=ticker, vencimento=vencimento, estrutura=estrutura)


class TestVencimentoProximo:
    def test_dispara_quando_vence_em_ate_5_dias_uteis_e_sem_posicao_posterior(self):
        item = opcao_simples("PETR4", COMPRADO, CALL, 30, dias=3, vencimento=dt.date(2026, 8, 14))
        alertas = detectar_vencimento_proximo_sem_rolagem([item])
        assert len(alertas) == 1
        assert alertas[0].tipo == ALERTA_VENCIMENTO_PROXIMO
        assert alertas[0].ticker == "PETR4"

    def test_nao_dispara_quando_ha_posicao_com_vencimento_posterior_no_mesmo_ticker(self):
        curto = opcao_simples("PETR4", COMPRADO, CALL, 30, dias=3, vencimento=dt.date(2026, 8, 14))
        longo = opcao_simples("PETR4", COMPRADO, CALL, 32, dias=40, vencimento=dt.date(2026, 9, 20))
        alertas = detectar_vencimento_proximo_sem_rolagem([curto, longo])
        assert alertas == []

    def test_nao_dispara_fora_da_janela_de_dias(self):
        item = opcao_simples("PETR4", COMPRADO, CALL, 30, dias=10, vencimento=dt.date(2026, 8, 25))
        assert detectar_vencimento_proximo_sem_rolagem([item]) == []

    def test_nao_dispara_para_vencimento_ja_passado(self):
        item = opcao_simples("PETR4", COMPRADO, CALL, 30, dias=-2, vencimento=dt.date(2026, 8, 5))
        assert detectar_vencimento_proximo_sem_rolagem([item]) == []

    def test_ticker_diferente_nao_conta_como_rolagem(self):
        curto = opcao_simples("PETR4", COMPRADO, CALL, 30, dias=3, vencimento=dt.date(2026, 8, 14))
        outro_ticker = opcao_simples("VALE3", COMPRADO, CALL, 60, dias=40, vencimento=dt.date(2026, 9, 20))
        alertas = detectar_vencimento_proximo_sem_rolagem([curto, outro_ticker])
        assert len(alertas) == 1
        assert alertas[0].ticker == "PETR4"


class TestRiscoExercicio:
    def test_call_vendida_dentro_do_dinheiro_gera_alerta_alta_severidade(self):
        item = opcao_simples("PETR4", VENDIDO, CALL, strike=28, dias=2, vencimento=dt.date(2026, 8, 13))
        alertas = detectar_risco_exercicio([item], {"PETR4": 30.0})
        assert len(alertas) == 1
        assert alertas[0].tipo == ALERTA_RISCO_EXERCICIO
        assert alertas[0].severidade == "alta"

    def test_put_vendida_proxima_ao_strike_gera_alerta_atencao(self):
        # strike 30, preco 30.5 -> 1.67% de distancia, dentro da margem de 3%
        item = opcao_simples("PETR4", VENDIDO, PUT, strike=30, dias=2, vencimento=dt.date(2026, 8, 13))
        alertas = detectar_risco_exercicio([item], {"PETR4": 30.5})
        assert len(alertas) == 1
        assert alertas[0].severidade == "atencao"

    def test_perna_comprada_nao_gera_risco_de_exercicio(self):
        item = opcao_simples("PETR4", COMPRADO, CALL, strike=28, dias=2, vencimento=dt.date(2026, 8, 13))
        assert detectar_risco_exercicio([item], {"PETR4": 30.0}) == []

    def test_strike_longe_do_preco_nao_gera_alerta(self):
        item = opcao_simples("PETR4", VENDIDO, CALL, strike=50, dias=2, vencimento=dt.date(2026, 8, 13))
        assert detectar_risco_exercicio([item], {"PETR4": 30.0}) == []

    def test_sem_preco_atual_disponivel_nao_gera_alerta(self):
        item = opcao_simples("PETR4", VENDIDO, CALL, strike=28, dias=2, vencimento=dt.date(2026, 8, 13))
        assert detectar_risco_exercicio([item], {}) == []

    def test_trava_com_perna_vendida_itm_tambem_dispara(self):
        comprada = OptionLeg(1, CALL, COMPRADO, 100, 25, dt.date(2026, 8, 13), preco_medio_pago=3)
        vendida = OptionLeg(2, CALL, VENDIDO, 100, 28, dt.date(2026, 8, 13), preco_medio_pago=1)
        estrutura = EstruturaClassificada(
            tipo=TRAVA_ALTA_CALL, pernas=[comprada, vendida], quantidade=100, dias_ate_vencimento=2
        )
        item = ItemPosicaoDerivativo(ticker="PETR4", vencimento=dt.date(2026, 8, 13), estrutura=estrutura)
        alertas = detectar_risco_exercicio([item], {"PETR4": 30.0})
        assert len(alertas) == 1


class TestConcentracao:
    def test_dispara_quando_exposicao_ultrapassa_limite(self):
        alertas = detectar_concentracao({"PETR4": 40000.0}, patrimonio_total=100000.0)
        assert len(alertas) == 1
        assert alertas[0].tipo == ALERTA_CONCENTRACAO
        assert alertas[0].ticker == "PETR4"

    def test_exposicao_negativa_conta_pelo_modulo(self):
        alertas = detectar_concentracao({"PETR4": -70000.0}, patrimonio_total=100000.0)
        assert len(alertas) == 1
        assert alertas[0].severidade == "alta"  # >= 2x o limite (70% >= 60%)

    def test_abaixo_do_limite_nao_dispara(self):
        alertas = detectar_concentracao({"PETR4": 10000.0}, patrimonio_total=100000.0)
        assert alertas == []

    def test_patrimonio_zero_nao_gera_divisao_por_zero(self):
        assert detectar_concentracao({"PETR4": 10000.0}, patrimonio_total=0.0) == []

    def test_multiplos_tickers_cada_um_avaliado_independentemente(self):
        alertas = detectar_concentracao(
            {"PETR4": 40000.0, "VALE3": 5000.0}, patrimonio_total=100000.0
        )
        assert len(alertas) == 1
        assert alertas[0].ticker == "PETR4"
