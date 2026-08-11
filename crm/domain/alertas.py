"""
Alertas deterministicos sobre posicao (item 5 da Fase 2).

Assim como o motor de classificacao de estruturas, este modulo e
proposital e exclusivamente baseado em regras explicitas (comparacao de
datas, strikes e valores) -- nada de heuristica probabilistica ou modelo
de linguagem. Cada alerta e auditavel por compliance lendo a funcao que o
gera.

Estes alertas sao **informativos, de uso interno da mesa**. Nenhuma
funcao aqui gera texto ou recomendacao endereçada ao cliente final, nem
sugere uma acao de hedge especifica -- apenas sinaliza uma condicao
factual (vencimento proximo, strike perto do preco, concentracao) para o
trader avaliar.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Optional

from domain.options_engine import CALL, PUT, VENDIDO, EstruturaClassificada

ALERTA_VENCIMENTO_PROXIMO = "VENCIMENTO_PROXIMO_SEM_ROLAGEM"
ALERTA_RISCO_EXERCICIO = "RISCO_DE_EXERCICIO"
ALERTA_CONCENTRACAO = "CONCENTRACAO_DE_RISCO"

SEVERIDADE_ATENCAO = "atencao"
SEVERIDADE_ALTA = "alta"


@dataclasses.dataclass
class ItemPosicaoDerivativo:
    """Uma estrutura ja classificada, no contexto de (ticker, vencimento)
    de um cliente -- a unidade de entrada dos detectores de alerta."""

    ticker: str
    vencimento: dt.date
    estrutura: EstruturaClassificada


@dataclasses.dataclass
class Alerta:
    tipo: str
    ticker: str
    severidade: str
    mensagem: str
    vencimento: Optional[dt.date] = None


def detectar_vencimento_proximo_sem_rolagem(
    itens: list[ItemPosicaoDerivativo], dias_uteis_limite: int = 5
) -> list[Alerta]:
    """Opcao (ou estrutura) vencendo em ate `dias_uteis_limite` dias uteis.

    "Sem posicao de rolagem identificada" e verificado de forma
    deterministica: existe, no mesmo ticker, alguma outra posicao com
    data de vencimento posterior a desta? Se sim, considera-se que ha uma
    posicao candidata a rolagem ja aberta e o alerta nao dispara para
    essa perna. Esta e uma aproximacao documentada -- nao inferimos
    intencao do trader, apenas comparamos datas.
    """
    vencimentos_por_ticker: dict[str, set[dt.date]] = {}
    for item in itens:
        vencimentos_por_ticker.setdefault(item.ticker, set()).add(item.vencimento)

    alertas: list[Alerta] = []
    for item in itens:
        dias = item.estrutura.dias_ate_vencimento
        if dias is None or dias < 0 or dias > dias_uteis_limite:
            continue
        tem_vencimento_posterior = any(
            v > item.vencimento for v in vencimentos_por_ticker.get(item.ticker, ())
        )
        if tem_vencimento_posterior:
            continue
        alertas.append(
            Alerta(
                tipo=ALERTA_VENCIMENTO_PROXIMO,
                ticker=item.ticker,
                severidade=SEVERIDADE_ATENCAO,
                vencimento=item.vencimento,
                mensagem=(
                    f"{item.ticker}: estrutura {item.estrutura.tipo} vence em "
                    f"{dias} dia(s) util(eis) e nao ha posicao com vencimento "
                    "posterior identificada no mesmo ticker (possivel rolagem pendente)."
                ),
            )
        )
    return alertas


def detectar_risco_exercicio(
    itens: list[ItemPosicaoDerivativo],
    preco_atual_por_ticker: dict[str, float],
    dias_uteis_limite: int = 5,
    margem_strike_pct: float = 0.03,
) -> list[Alerta]:
    """Perna VENDIDA de CALL/PUT com vencimento proximo e strike dentro do
    dinheiro (ITM) ou a ate `margem_strike_pct` do preco atual do
    ativo-objeto -- risco de exercicio."""
    alertas: list[Alerta] = []
    for item in itens:
        dias = item.estrutura.dias_ate_vencimento
        if dias is None or dias < 0 or dias > dias_uteis_limite:
            continue
        preco_atual = preco_atual_por_ticker.get(item.ticker)
        if preco_atual is None:
            continue

        for perna in item.estrutura.pernas:
            if perna.direcao != VENDIDO or perna.tipo_derivativo not in (CALL, PUT) or perna.strike is None:
                continue

            dentro_do_dinheiro = (
                (perna.tipo_derivativo == CALL and preco_atual >= perna.strike)
                or (perna.tipo_derivativo == PUT and preco_atual <= perna.strike)
            )
            proximo = perna.strike != 0 and abs(preco_atual - perna.strike) / abs(perna.strike) <= margem_strike_pct

            if not (dentro_do_dinheiro or proximo):
                continue

            severidade = SEVERIDADE_ALTA if dentro_do_dinheiro else SEVERIDADE_ATENCAO
            situacao = "dentro do dinheiro" if dentro_do_dinheiro else "proximo ao strike"
            alertas.append(
                Alerta(
                    tipo=ALERTA_RISCO_EXERCICIO,
                    ticker=item.ticker,
                    severidade=severidade,
                    vencimento=item.vencimento,
                    mensagem=(
                        f"{item.ticker}: {perna.tipo_derivativo} vendida strike "
                        f"{perna.strike:g} {situacao} (preco atual {preco_atual:g}), "
                        f"vence em {dias} dia(s) util(eis) -- risco de exercicio."
                    ),
                )
            )
    return alertas


def detectar_concentracao(
    exposicao_por_ticker: dict[str, float],
    patrimonio_total: float,
    limite_pct: float = 0.30,
) -> list[Alerta]:
    """Exposicao direcional (modulo) concentrada em um unico ticker acima
    de `limite_pct` do patrimonio total do cliente."""
    if not patrimonio_total or patrimonio_total <= 0:
        return []
    alertas: list[Alerta] = []
    for ticker, exposicao in exposicao_por_ticker.items():
        percentual = abs(exposicao) / patrimonio_total
        if percentual >= limite_pct:
            alertas.append(
                Alerta(
                    tipo=ALERTA_CONCENTRACAO,
                    ticker=ticker,
                    severidade=SEVERIDADE_ALTA if percentual >= 2 * limite_pct else SEVERIDADE_ATENCAO,
                    mensagem=(
                        f"{ticker}: exposicao derivativa concentrada em "
                        f"{percentual * 100:.1f}% do patrimonio do cliente "
                        f"(limite de referencia: {limite_pct * 100:.0f}%)."
                    ),
                )
            )
    return alertas


def gerar_todos_os_alertas(
    itens: list[ItemPosicaoDerivativo],
    preco_atual_por_ticker: dict[str, float],
    exposicao_por_ticker: dict[str, float],
    patrimonio_total: float,
    dias_uteis_limite: int = 5,
) -> list[Alerta]:
    return (
        detectar_vencimento_proximo_sem_rolagem(itens, dias_uteis_limite)
        + detectar_risco_exercicio(itens, preco_atual_por_ticker, dias_uteis_limite)
        + detectar_concentracao(exposicao_por_ticker, patrimonio_total)
    )
