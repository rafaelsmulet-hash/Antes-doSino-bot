"""
Motor de classificacao de estruturas de opcoes.

Modulo isolado, sem dependencia de banco de dados, framework web ou
qualquer servico externo -- e uma funcao pura testavel, propositalmente
separada da interface (ver Fase 2 do escopo: "comecando pelo motor de
classificacao... como modulo isolado e testavel antes de integra-lo a
interface").

Reconhecimento 100% baseado em regras deterministicas (comparacao de
strikes, direcao e quantidade). Nao ha heuristica probabilistica nem
modelo de linguagem envolvido -- toda a logica abaixo e auditavel linha a
linha por compliance.

Ordem de reconhecimento (conforme especificacao), aplicada sobre o
"balaio" de pernas de um mesmo (cliente, ticker do ativo-objeto, data de
vencimento):
    1. Trava de alta com CALL (bull call spread)
    2. Trava de baixa com CALL (bear call spread)
    3. Trava de alta com PUT   (bull put spread)
    4. Trava de baixa com PUT  (bear put spread)
    5. Straddle comprado
    6. Strangle comprado
    7. Collar (acao comprada + PUT comprada + CALL vendida)
    8. Sobra sem padrao -> POSICAO_SIMPLES

Quantidades nao perfeitamente pareadas (ex: 800 vs 1000 contratos) geram
uma estrutura parcial identificada (com aviso) mais o excedente como
posicao solta (tambem com aviso) -- a identificacao nunca e descartada e
nenhum pareamento incorreto e forcado.

Premissas assumidas (documentadas para auditoria):
    - 1 contrato de opcao representa a mesma unidade de quantidade que a
      acao-objeto (sem multiplicador de lote na conta -- se o dado de
      origem usar lotes, normalize antes de chamar este modulo).
    - "Dias uteis ate o vencimento" conta segunda a sexta-feira, sem
      calendario de feriados (ajustavel futuramente sem mudar a
      assinatura publica do modulo).
    - Formulas de risco/ganho/ponto de equilibrio ignoram custos de
      corretagem, emolumentos e imposto.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Optional

CALL = "CALL"
PUT = "PUT"
TERMO = "TERMO"
FUTURO = "FUTURO"

COMPRADO = "COMPRADO"
VENDIDO = "VENDIDO"

TRAVA_ALTA_CALL = "TRAVA_ALTA_CALL"
TRAVA_BAIXA_CALL = "TRAVA_BAIXA_CALL"
TRAVA_ALTA_PUT = "TRAVA_ALTA_PUT"
TRAVA_BAIXA_PUT = "TRAVA_BAIXA_PUT"
STRADDLE_COMPRADO = "STRADDLE_COMPRADO"
STRANGLE_COMPRADO = "STRANGLE_COMPRADO"
COLLAR = "COLLAR"
POSICAO_SIMPLES = "POSICAO_SIMPLES"

_EPSILON = 1e-9


@dataclasses.dataclass
class OptionLeg:
    """Uma perna de derivativo dentro de um balaio (cliente, ticker, vencimento)."""

    ref_id: Any
    tipo_derivativo: str  # CALL | PUT | TERMO | FUTURO
    direcao: str  # COMPRADO | VENDIDO
    quantidade: float
    strike: Optional[float]
    data_vencimento: dt.date
    preco_medio_pago: Optional[float] = None
    delta: Optional[float] = None

    def __post_init__(self):
        if self.quantidade <= 0:
            raise ValueError(f"quantidade da perna {self.ref_id!r} deve ser positiva")
        if self.direcao not in (COMPRADO, VENDIDO):
            raise ValueError(f"direcao invalida: {self.direcao!r}")
        if self.tipo_derivativo not in (CALL, PUT, TERMO, FUTURO):
            raise ValueError(f"tipo_derivativo invalido: {self.tipo_derivativo!r}")


@dataclasses.dataclass
class EquityLeg:
    """Posicao a vista no ativo-objeto, usada apenas para identificar collar."""

    ref_id: Any
    quantidade: float
    preco_medio: Optional[float] = None
    direcao: str = COMPRADO


@dataclasses.dataclass
class EstruturaClassificada:
    tipo: str
    pernas: list = dataclasses.field(default_factory=list)
    quantidade: float = 0.0
    dias_ate_vencimento: Optional[int] = None
    risco_maximo: Optional[float] = None
    ganho_maximo: Optional[float] = None
    ganho_maximo_ilimitado: bool = False
    ponto_equilibrio: Optional[list] = None
    delta_liquido: Optional[float] = None
    aviso: Optional[str] = None


def classificar_grupo(
    legs: list,
    equity: Optional[EquityLeg] = None,
    data_referencia: Optional[dt.date] = None,
) -> list:
    """Classifica as pernas de um unico balaio (cliente, ticker, vencimento).

    Nao muta a lista `legs` recebida. Retorna uma lista de
    EstruturaClassificada, incluindo POSICAO_SIMPLES para tudo que sobrar
    sem padrao reconhecido.
    """
    data_referencia = data_referencia or dt.date.today()
    restantes = [dataclasses.replace(l) for l in legs]
    quantidades_originais = {id(l): l.quantidade for l in restantes}

    estruturas: list = []
    estruturas += _casar_travas(restantes, CALL, TRAVA_ALTA_CALL, TRAVA_BAIXA_CALL, data_referencia)
    estruturas += _casar_travas(restantes, PUT, TRAVA_ALTA_PUT, TRAVA_BAIXA_PUT, data_referencia)
    estruturas += _casar_straddle_strangle(restantes, data_referencia)
    if equity is not None:
        estruturas += _casar_collar(restantes, equity, data_referencia)

    for leg in restantes:
        if leg.quantidade <= _EPSILON:
            continue
        parcial = leg.quantidade < quantidades_originais[id(leg)] - _EPSILON
        aviso = (
            "Excedente nao pareado: parte desta posicao foi consumida em "
            "outra estrutura identificada; o saldo abaixo ficou sem par."
            if parcial
            else None
        )
        estruturas.append(_posicao_simples(leg, data_referencia, aviso))

    return estruturas


def _leg_com_qtd(leg: OptionLeg, qty: float) -> OptionLeg:
    return dataclasses.replace(leg, quantidade=qty)


def _casar_travas(restantes, tipo, tipo_alta, tipo_baixa, data_referencia) -> list:
    estruturas: list = []
    compradas = sorted(
        (l for l in restantes if l.tipo_derivativo == tipo and l.direcao == COMPRADO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )
    vendidas = sorted(
        (l for l in restantes if l.tipo_derivativo == tipo and l.direcao == VENDIDO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )

    i = j = 0
    while i < len(compradas) and j < len(vendidas):
        c = compradas[i]
        v = vendidas[j]
        if c.quantidade <= _EPSILON:
            i += 1
            continue
        if v.quantidade <= _EPSILON:
            j += 1
            continue
        if c.strike is None or v.strike is None or c.strike == v.strike:
            # Strikes iguais (ou ausentes) nao formam trava valida -- deixa
            # como esta para virar posicao simples; avanca a perna vendida
            # para tentar o proximo strike disponivel.
            j += 1
            continue

        qty = min(c.quantidade, v.quantidade)
        pareamento_desigual = abs(c.quantidade - v.quantidade) > _EPSILON
        tipo_estrutura = tipo_alta if v.strike > c.strike else tipo_baixa

        perna_c = _leg_com_qtd(c, qty)
        perna_v = _leg_com_qtd(v, qty)
        risco, ganho, breakeven = _financeiro_trava(tipo_estrutura, perna_c, perna_v, qty)

        estruturas.append(
            EstruturaClassificada(
                tipo=tipo_estrutura,
                pernas=[perna_c, perna_v],
                quantidade=qty,
                dias_ate_vencimento=_dias_uteis_ate(data_referencia, c.data_vencimento),
                risco_maximo=risco,
                ganho_maximo=ganho,
                ponto_equilibrio=breakeven,
                delta_liquido=_delta_liquido([perna_c, perna_v]),
                aviso=(
                    "Pareamento parcial: as pernas tinham quantidades "
                    "diferentes: o excedente aparece como posicao solta."
                    if pareamento_desigual
                    else None
                ),
            )
        )

        c.quantidade -= qty
        v.quantidade -= qty
        if c.quantidade <= _EPSILON:
            i += 1
        if v.quantidade <= _EPSILON:
            j += 1

    restantes[:] = [l for l in restantes if l.quantidade > _EPSILON]
    return estruturas


def _financeiro_trava(tipo_estrutura, perna_comprada, perna_vendida, qty):
    strike_c, strike_v = perna_comprada.strike, perna_vendida.strike
    premio_c, premio_v = perna_comprada.preco_medio_pago, perna_vendida.preco_medio_pago
    if premio_c is None or premio_v is None:
        return None, None, None

    largura = abs(strike_v - strike_c)

    if tipo_estrutura == TRAVA_ALTA_CALL:
        debito = premio_c - premio_v
        risco = max(debito, 0.0) * qty
        ganho = max(largura - debito, 0.0) * qty
        breakeven = [strike_c + debito]
    elif tipo_estrutura == TRAVA_BAIXA_CALL:
        credito = premio_v - premio_c
        ganho = max(credito, 0.0) * qty
        risco = max(largura - credito, 0.0) * qty
        breakeven = [strike_v + credito]
    elif tipo_estrutura == TRAVA_ALTA_PUT:
        credito = premio_v - premio_c
        ganho = max(credito, 0.0) * qty
        risco = max(largura - credito, 0.0) * qty
        breakeven = [strike_v - credito]
    elif tipo_estrutura == TRAVA_BAIXA_PUT:
        debito = premio_c - premio_v
        risco = max(debito, 0.0) * qty
        ganho = max(largura - debito, 0.0) * qty
        breakeven = [strike_c - debito]
    else:  # pragma: no cover - defensivo
        return None, None, None

    return risco, ganho, breakeven


def _casar_straddle_strangle(restantes, data_referencia) -> list:
    estruturas: list = []
    calls = sorted(
        (l for l in restantes if l.tipo_derivativo == CALL and l.direcao == COMPRADO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )
    puts = sorted(
        (l for l in restantes if l.tipo_derivativo == PUT and l.direcao == COMPRADO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )

    i = j = 0
    while i < len(calls) and j < len(puts):
        c = calls[i]
        p = puts[j]
        if c.quantidade <= _EPSILON:
            i += 1
            continue
        if p.quantidade <= _EPSILON:
            j += 1
            continue

        qty = min(c.quantidade, p.quantidade)
        pareamento_desigual = abs(c.quantidade - p.quantidade) > _EPSILON
        tipo_estrutura = STRADDLE_COMPRADO if c.strike == p.strike else STRANGLE_COMPRADO

        perna_c = _leg_com_qtd(c, qty)
        perna_p = _leg_com_qtd(p, qty)
        risco, breakeven = _financeiro_straddle_strangle(perna_c, perna_p, qty)

        estruturas.append(
            EstruturaClassificada(
                tipo=tipo_estrutura,
                pernas=[perna_c, perna_p],
                quantidade=qty,
                dias_ate_vencimento=_dias_uteis_ate(data_referencia, c.data_vencimento),
                risco_maximo=risco,
                ganho_maximo=None,
                ganho_maximo_ilimitado=True,
                ponto_equilibrio=breakeven,
                delta_liquido=_delta_liquido([perna_c, perna_p]),
                aviso=(
                    "Pareamento parcial: as pernas tinham quantidades "
                    "diferentes: o excedente aparece como posicao solta."
                    if pareamento_desigual
                    else None
                ),
            )
        )

        c.quantidade -= qty
        p.quantidade -= qty
        if c.quantidade <= _EPSILON:
            i += 1
        if p.quantidade <= _EPSILON:
            j += 1

    restantes[:] = [l for l in restantes if l.quantidade > _EPSILON]
    return estruturas


def _financeiro_straddle_strangle(perna_call, perna_put, qty):
    if perna_call.preco_medio_pago is None or perna_put.preco_medio_pago is None:
        return None, None
    premio_unit = perna_call.preco_medio_pago + perna_put.preco_medio_pago
    risco = premio_unit * qty
    breakeven = sorted([perna_put.strike - premio_unit, perna_call.strike + premio_unit])
    return risco, breakeven


def _casar_collar(restantes, equity: EquityLeg, data_referencia) -> list:
    if equity.quantidade <= _EPSILON or equity.direcao != COMPRADO:
        return []

    puts = sorted(
        (l for l in restantes if l.tipo_derivativo == PUT and l.direcao == COMPRADO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )
    calls = sorted(
        (l for l in restantes if l.tipo_derivativo == CALL and l.direcao == VENDIDO and l.quantidade > _EPSILON),
        key=lambda l: l.strike,
    )
    if not puts or not calls:
        return []

    estruturas: list = []
    equity_restante = equity.quantidade
    i = j = 0
    while i < len(puts) and j < len(calls) and equity_restante > _EPSILON:
        p = puts[i]
        c = calls[j]
        if p.quantidade <= _EPSILON:
            i += 1
            continue
        if c.quantidade <= _EPSILON:
            j += 1
            continue

        qty = min(p.quantidade, c.quantidade, equity_restante)
        pareamento_desigual = not (
            abs(p.quantidade - qty) <= _EPSILON
            and abs(c.quantidade - qty) <= _EPSILON
            and abs(equity_restante - qty) <= _EPSILON
        )

        perna_p = _leg_com_qtd(p, qty)
        perna_c = _leg_com_qtd(c, qty)
        risco, ganho, breakeven = _financeiro_collar(equity, perna_p, perna_c, qty)

        estruturas.append(
            EstruturaClassificada(
                tipo=COLLAR,
                pernas=[perna_p, perna_c],
                quantidade=qty,
                dias_ate_vencimento=_dias_uteis_ate(data_referencia, p.data_vencimento),
                risco_maximo=risco,
                ganho_maximo=ganho,
                ponto_equilibrio=breakeven,
                delta_liquido=_delta_liquido([perna_p, perna_c]),
                aviso=(
                    "Pareamento parcial: acao, PUT comprada e CALL vendida "
                    "tinham quantidades diferentes: o excedente aparece "
                    "como posicao solta."
                    if pareamento_desigual
                    else None
                ),
            )
        )

        p.quantidade -= qty
        c.quantidade -= qty
        equity_restante -= qty
        if p.quantidade <= _EPSILON:
            i += 1
        if c.quantidade <= _EPSILON:
            j += 1

    restantes[:] = [l for l in restantes if l.quantidade > _EPSILON]
    return estruturas


def _financeiro_collar(equity: EquityLeg, perna_put, perna_call, qty):
    if equity.preco_medio is None:
        return None, None, None
    premio_put = perna_put.preco_medio_pago or 0.0
    premio_call = perna_call.preco_medio_pago or 0.0
    custo_liquido = premio_put - premio_call  # positivo = custo liquido pago

    risco = (equity.preco_medio - perna_put.strike + custo_liquido) * qty
    ganho = (perna_call.strike - equity.preco_medio - custo_liquido) * qty
    breakeven = [equity.preco_medio + custo_liquido]
    return risco, ganho, breakeven


def _posicao_simples(leg, data_referencia, aviso) -> EstruturaClassificada:
    return EstruturaClassificada(
        tipo=POSICAO_SIMPLES,
        pernas=[leg],
        quantidade=leg.quantidade,
        dias_ate_vencimento=_dias_uteis_ate(data_referencia, leg.data_vencimento),
        risco_maximo=None,
        ganho_maximo=None,
        ponto_equilibrio=None,
        delta_liquido=(leg.delta * leg.quantidade if leg.delta is not None else None),
        aviso=aviso,
    )


def _dias_uteis_ate(data_referencia: dt.date, data_alvo: Optional[dt.date]) -> Optional[int]:
    """Dias uteis (seg-sex, sem calendario de feriados) entre data_referencia
    (exclusiva) e data_alvo (inclusiva). Negativo se data_alvo for anterior
    a data_referencia (vencimento ja passado)."""
    if data_alvo is None:
        return None
    delta_dias = (data_alvo - data_referencia).days
    if delta_dias == 0:
        return 0
    passo = 1 if delta_dias > 0 else -1
    dias_uteis = 0
    d = data_referencia
    for _ in range(abs(delta_dias)):
        d += dt.timedelta(days=passo)
        if d.weekday() < 5:
            dias_uteis += 1
    return dias_uteis * passo


def _delta_liquido(pernas: list) -> Optional[float]:
    if any(p.delta is None for p in pernas):
        return None
    total = 0.0
    for p in pernas:
        sinal = 1.0 if p.direcao == COMPRADO else -1.0
        total += sinal * p.delta * p.quantidade
    return total
