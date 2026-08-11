import datetime as dt

import pytest

from domain.options_engine import (
    CALL,
    COLLAR,
    COMPRADO,
    PUT,
    STRADDLE_COMPRADO,
    STRANGLE_COMPRADO,
    TRAVA_ALTA_CALL,
    TRAVA_ALTA_PUT,
    TRAVA_BAIXA_CALL,
    TRAVA_BAIXA_PUT,
    VENDIDO,
    POSICAO_SIMPLES,
    EquityLeg,
    OptionLeg,
    classificar_grupo,
)

VENC = dt.date(2026, 9, 18)
HOJE = dt.date(2026, 8, 11)


def leg(ref_id, tipo, direcao, qty, strike, premio=None, delta=None, venc=VENC):
    return OptionLeg(
        ref_id=ref_id,
        tipo_derivativo=tipo,
        direcao=direcao,
        quantidade=qty,
        strike=strike,
        data_vencimento=venc,
        preco_medio_pago=premio,
        delta=delta,
    )


def only(estruturas, tipo):
    achados = [e for e in estruturas if e.tipo == tipo]
    assert len(achados) == 1, f"esperado exatamente 1 {tipo}, achou {len(achados)}: {estruturas}"
    return achados[0]


class TestTravaCall:
    def test_trava_alta_call_bull_spread(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=30, premio=3),
            leg("v1", CALL, VENDIDO, 100, strike=35, premio=1),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == TRAVA_ALTA_CALL
        assert estrutura.quantidade == 100
        assert estrutura.risco_maximo == pytest.approx(200.0)
        assert estrutura.ganho_maximo == pytest.approx(300.0)
        assert estrutura.ponto_equilibrio == pytest.approx([32.0])
        assert estrutura.aviso is None

    def test_trava_baixa_call_bear_spread(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=35, premio=1),
            leg("v1", CALL, VENDIDO, 100, strike=30, premio=3),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == TRAVA_BAIXA_CALL
        assert estrutura.ganho_maximo == pytest.approx(200.0)
        assert estrutura.risco_maximo == pytest.approx(300.0)
        assert estrutura.ponto_equilibrio == pytest.approx([32.0])

    def test_mesmo_strike_nao_forma_trava(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=30, premio=3),
            leg("v1", CALL, VENDIDO, 100, strike=30, premio=1),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        assert all(e.tipo == POSICAO_SIMPLES for e in estruturas)
        assert len(estruturas) == 2


class TestTravaPut:
    def test_trava_alta_put_bull_put_spread_credito(self):
        legs = [
            leg("c1", PUT, COMPRADO, 100, strike=30, premio=1),
            leg("v1", PUT, VENDIDO, 100, strike=35, premio=3),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == TRAVA_ALTA_PUT
        assert estrutura.ganho_maximo == pytest.approx(200.0)
        assert estrutura.risco_maximo == pytest.approx(300.0)
        assert estrutura.ponto_equilibrio == pytest.approx([33.0])

    def test_trava_baixa_put_bear_put_spread_debito(self):
        legs = [
            leg("c1", PUT, COMPRADO, 100, strike=35, premio=3),
            leg("v1", PUT, VENDIDO, 100, strike=30, premio=1),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == TRAVA_BAIXA_PUT
        assert estrutura.risco_maximo == pytest.approx(200.0)
        assert estrutura.ganho_maximo == pytest.approx(300.0)
        assert estrutura.ponto_equilibrio == pytest.approx([33.0])


class TestStraddleStrangle:
    def test_straddle_comprado_mesmo_strike(self):
        legs = [
            leg("c1", CALL, COMPRADO, 50, strike=40, premio=2),
            leg("p1", PUT, COMPRADO, 50, strike=40, premio=2.5),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == STRADDLE_COMPRADO
        assert estrutura.risco_maximo == pytest.approx(225.0)
        assert estrutura.ganho_maximo is None
        assert estrutura.ganho_maximo_ilimitado is True
        assert estrutura.ponto_equilibrio == pytest.approx([35.5, 44.5])

    def test_strangle_comprado_strikes_diferentes(self):
        legs = [
            leg("c1", CALL, COMPRADO, 50, strike=45, premio=1.5),
            leg("p1", PUT, COMPRADO, 50, strike=35, premio=1.0),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == STRANGLE_COMPRADO
        assert estrutura.risco_maximo == pytest.approx(125.0)
        assert estrutura.ganho_maximo_ilimitado is True
        assert estrutura.ponto_equilibrio == pytest.approx([32.5, 47.5])

    def test_call_vendida_nao_forma_straddle(self):
        legs = [
            leg("c1", CALL, VENDIDO, 50, strike=40, premio=2),
            leg("p1", PUT, COMPRADO, 50, strike=40, premio=2.5),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        assert all(e.tipo == POSICAO_SIMPLES for e in estruturas)


class TestCollar:
    def test_collar_completo(self):
        legs = [
            leg("p1", PUT, COMPRADO, 1000, strike=45, premio=2),
            leg("c1", CALL, VENDIDO, 1000, strike=55, premio=1.5),
        ]
        equity = EquityLeg(ref_id="acao1", quantidade=1000, preco_medio=50)
        [estrutura] = classificar_grupo(legs, equity=equity, data_referencia=HOJE)
        assert estrutura.tipo == COLLAR
        assert estrutura.risco_maximo == pytest.approx(5500.0)
        assert estrutura.ganho_maximo == pytest.approx(4500.0)
        assert estrutura.ponto_equilibrio == pytest.approx([50.5])
        assert estrutura.aviso is None

    def test_collar_sem_acao_nao_e_identificado(self):
        legs = [
            leg("p1", PUT, COMPRADO, 1000, strike=45, premio=2),
            leg("c1", CALL, VENDIDO, 1000, strike=55, premio=1.5),
        ]
        estruturas = classificar_grupo(legs, equity=None, data_referencia=HOJE)
        assert all(e.tipo == POSICAO_SIMPLES for e in estruturas)


class TestQuantidadesDesiguais:
    def test_quantidade_parcial_800_vs_1000(self):
        legs = [
            leg("c1", CALL, COMPRADO, 1000, strike=30, premio=3),
            leg("v1", CALL, VENDIDO, 800, strike=35, premio=1),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        trava = only(estruturas, TRAVA_ALTA_CALL)
        assert trava.quantidade == 800
        assert trava.aviso is not None

        sobra = only(estruturas, POSICAO_SIMPLES)
        assert sobra.quantidade == 200
        assert sobra.pernas[0].ref_id == "c1"
        assert sobra.aviso is not None

    def test_nunca_descarta_identificacao_por_causa_do_excedente(self):
        legs = [
            leg("c1", CALL, COMPRADO, 500, strike=20, premio=2),
            leg("v1", CALL, VENDIDO, 50, strike=25, premio=1),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        trava = only(estruturas, TRAVA_ALTA_CALL)
        assert trava.quantidade == 50
        sobra = only(estruturas, POSICAO_SIMPLES)
        assert sobra.quantidade == 450


class TestMaisDeDuasPernas:
    def test_duas_travas_call_independentes(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=10, premio=2),
            leg("v1", CALL, VENDIDO, 100, strike=12, premio=1),
            leg("c2", CALL, COMPRADO, 200, strike=20, premio=3),
            leg("v2", CALL, VENDIDO, 200, strike=22, premio=2),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        travas = [e for e in estruturas if e.tipo == TRAVA_ALTA_CALL]
        assert len(travas) == 2
        quantidades = sorted(t.quantidade for t in travas)
        assert quantidades == [100, 200]
        assert all(e.tipo != POSICAO_SIMPLES for e in estruturas)

    def test_call_spread_mais_straddle_no_mesmo_balaio(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=10, premio=2),
            leg("v1", CALL, VENDIDO, 100, strike=12, premio=1),
            leg("c2", CALL, COMPRADO, 50, strike=15, premio=1),
            leg("p1", PUT, COMPRADO, 50, strike=15, premio=1),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        assert only(estruturas, TRAVA_ALTA_CALL).quantidade == 100
        assert only(estruturas, STRADDLE_COMPRADO).quantidade == 50


class TestPernasSemPar:
    def test_call_vendida_isolada_vira_posicao_simples(self):
        legs = [leg("v1", CALL, VENDIDO, 100, strike=30, premio=1)]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == POSICAO_SIMPLES
        assert estrutura.aviso is None

    def test_termo_e_futuro_ficam_como_posicao_simples(self):
        legs = [
            leg("t1", "TERMO", COMPRADO, 100, strike=None, premio=None),
            leg("f1", "FUTURO", VENDIDO, 100, strike=None, premio=None),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        assert all(e.tipo == POSICAO_SIMPLES for e in estruturas)
        assert len(estruturas) == 2


class TestOrdemDeReconhecimento:
    def test_spread_call_tem_prioridade_sobre_straddle(self):
        # CALL comprada K=10 poderia formar straddle com PUT comprada K=10,
        # mas a CALL vendida K=12 deve ser pareada primeiro (trava tem
        # prioridade na ordem de reconhecimento).
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=10, premio=2),
            leg("v1", CALL, VENDIDO, 100, strike=12, premio=1),
            leg("p1", PUT, COMPRADO, 100, strike=10, premio=2),
        ]
        estruturas = classificar_grupo(legs, data_referencia=HOJE)
        assert only(estruturas, TRAVA_ALTA_CALL).quantidade == 100
        assert only(estruturas, POSICAO_SIMPLES).pernas[0].ref_id == "p1"


class TestCamposAuxiliares:
    def test_dias_ate_vencimento_e_delta_liquido(self):
        legs = [
            leg(
                "c1", CALL, COMPRADO, 100, strike=30, premio=3, delta=0.6,
                venc=dt.date(2026, 8, 18),
            ),
            leg(
                "v1", CALL, VENDIDO, 100, strike=35, premio=1, delta=0.3,
                venc=dt.date(2026, 8, 18),
            ),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=dt.date(2026, 8, 11))
        # 11/08/2026 (terca) -> 18/08/2026 (terca): 5 dias uteis (qua..ter, sem sabado/domingo)
        assert estrutura.dias_ate_vencimento == 5
        assert estrutura.delta_liquido == pytest.approx(0.6 * 100 - 0.3 * 100)

    def test_sem_premio_nao_calcula_financeiro_mas_ainda_classifica(self):
        legs = [
            leg("c1", CALL, COMPRADO, 100, strike=30, premio=None),
            leg("v1", CALL, VENDIDO, 100, strike=35, premio=None),
        ]
        [estrutura] = classificar_grupo(legs, data_referencia=HOJE)
        assert estrutura.tipo == TRAVA_ALTA_CALL
        assert estrutura.risco_maximo is None
        assert estrutura.ganho_maximo is None
        assert estrutura.ponto_equilibrio is None

    def test_nao_muta_lista_de_entrada(self):
        legs = [
            leg("c1", CALL, COMPRADO, 1000, strike=30, premio=3),
            leg("v1", CALL, VENDIDO, 800, strike=35, premio=1),
        ]
        quantidades_antes = [l.quantidade for l in legs]
        classificar_grupo(legs, data_referencia=HOJE)
        assert [l.quantidade for l in legs] == quantidades_antes
