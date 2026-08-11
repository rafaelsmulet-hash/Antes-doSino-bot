"""
Monta a visao de posicao de um cliente (item 4 da Fase 2), combinando o
que foi importado do backoffice (`Posicao`, `PosicaoDerivativo`) com o
motor de classificacao de estruturas (`domain/options_engine.py`) e os
detectores de alerta (`domain/alertas.py`).

Este modulo so LE e agrega dados ja importados -- nunca recalcula
posicao a partir de interacoes ou qualquer dado proprio do CRM. Toda a
visao aqui e informativa, de uso interno da mesa.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import DIAS_UTEIS_ALERTA_VENCIMENTO
from domain.alertas import Alerta, ItemPosicaoDerivativo, gerar_todos_os_alertas
from domain.options_engine import EquityLeg, OptionLeg, classificar_grupo


def _posicoes_correntes(db: Session, cliente_id: int) -> list[models.Posicao]:
    data_mais_recente = db.execute(
        select(models.Posicao.data_referencia)
        .where(models.Posicao.cliente_id == cliente_id)
        .order_by(models.Posicao.data_referencia.desc())
        .limit(1)
    ).scalar_one_or_none()
    if data_mais_recente is None:
        return []
    return list(
        db.execute(
            select(models.Posicao).where(
                models.Posicao.cliente_id == cliente_id,
                models.Posicao.data_referencia == data_mais_recente,
            )
        )
        .scalars()
        .all()
    )


def _derivativos_correntes(db: Session, cliente_id: int) -> list[models.PosicaoDerivativo]:
    data_mais_recente = db.execute(
        select(models.PosicaoDerivativo.data_referencia)
        .where(models.PosicaoDerivativo.cliente_id == cliente_id)
        .order_by(models.PosicaoDerivativo.data_referencia.desc())
        .limit(1)
    ).scalar_one_or_none()
    if data_mais_recente is None:
        return []
    return list(
        db.execute(
            select(models.PosicaoDerivativo).where(
                models.PosicaoDerivativo.cliente_id == cliente_id,
                models.PosicaoDerivativo.data_referencia == data_mais_recente,
            )
        )
        .scalars()
        .all()
    )


def _snapshot_anterior(db: Session, cliente_id: int, antes_de: dt.date) -> list[models.PosicaoHistorico]:
    data_anterior = db.execute(
        select(models.PosicaoHistorico.data_snapshot)
        .where(
            models.PosicaoHistorico.cliente_id == cliente_id,
            models.PosicaoHistorico.data_snapshot < antes_de,
        )
        .order_by(models.PosicaoHistorico.data_snapshot.desc())
        .limit(1)
    ).scalar_one_or_none()
    if data_anterior is None:
        return []
    return list(
        db.execute(
            select(models.PosicaoHistorico).where(
                models.PosicaoHistorico.cliente_id == cliente_id,
                models.PosicaoHistorico.data_snapshot == data_anterior,
            )
        )
        .scalars()
        .all()
    )


def _classificar_derivativos(
    posicoes: list[models.Posicao], derivativos: list[models.PosicaoDerivativo]
) -> list[dict]:
    grupos: dict[tuple[str, dt.date], list[models.PosicaoDerivativo]] = defaultdict(list)
    for d in derivativos:
        grupos[(d.ticker_ativo_objeto, d.data_vencimento)].append(d)

    hoje = dt.date.today()
    estruturas_view: list[dict] = []
    for (ticker, vencimento), pernas_db in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        legs = [
            OptionLeg(
                ref_id=p.id,
                tipo_derivativo=p.tipo_derivativo,
                direcao=p.direcao,
                quantidade=p.quantidade,
                strike=p.strike,
                data_vencimento=p.data_vencimento,
                preco_medio_pago=p.preco_medio_pago,
                delta=p.delta,
            )
            for p in pernas_db
            if p.tipo_derivativo in ("CALL", "PUT", "TERMO", "FUTURO")
        ]
        posicao_acao = next((p for p in posicoes if p.ticker == ticker and p.tipo_ativo == "ACAO"), None)
        equity = (
            EquityLeg(ref_id=posicao_acao.id, quantidade=posicao_acao.quantidade, preco_medio=posicao_acao.preco_medio)
            if posicao_acao
            else None
        )
        for estrutura in classificar_grupo(legs, equity=equity, data_referencia=hoje):
            estruturas_view.append(
                {
                    "ticker": ticker,
                    "vencimento": vencimento,
                    "estrutura": estrutura,
                    "vencimento_proximo": (
                        estrutura.dias_ate_vencimento is not None
                        and 0 <= estrutura.dias_ate_vencimento <= DIAS_UTEIS_ALERTA_VENCIMENTO
                    ),
                    "tem_perna_vendida": any(p.direcao == "VENDIDO" for p in estrutura.pernas),
                }
            )
    return estruturas_view


def montar_visao_posicao(db: Session, cliente_id: int) -> dict:
    posicoes = _posicoes_correntes(db, cliente_id)
    derivativos = _derivativos_correntes(db, cliente_id)
    estruturas_view = _classificar_derivativos(posicoes, derivativos)

    patrimonio_total = sum((p.valor_mercado or 0.0) for p in posicoes)
    data_referencia = posicoes[0].data_referencia if posicoes else None

    anteriores = _snapshot_anterior(db, cliente_id, data_referencia) if data_referencia else []
    variacao_dia = None
    if anteriores:
        patrimonio_anterior = sum((p.valor_mercado or 0.0) for p in anteriores)
        if patrimonio_anterior:
            variacao_dia = {
                "valor": patrimonio_total - patrimonio_anterior,
                "percentual": (patrimonio_total - patrimonio_anterior) / patrimonio_anterior * 100,
            }

    preco_por_ticker = {p.ticker: p.preco_atual for p in posicoes if p.preco_atual is not None}

    exposicao_por_ticker: dict[str, float] = defaultdict(float)
    for p in posicoes:
        exposicao_por_ticker[p.ticker] += p.valor_mercado or 0.0

    exposicao_parcial = False
    for item in estruturas_view:
        estrutura = item["estrutura"]
        preco_ticker = preco_por_ticker.get(item["ticker"])
        if estrutura.delta_liquido is None or preco_ticker is None:
            exposicao_parcial = True
            continue
        exposicao_por_ticker[item["ticker"]] += estrutura.delta_liquido * preco_ticker

    exposicao_liquida = sum(exposicao_por_ticker.values()) if (posicoes or derivativos) else None

    return {
        "posicoes": posicoes,
        "derivativos_estruturas": estruturas_view,
        "patrimonio_total": patrimonio_total,
        "data_referencia": data_referencia,
        "variacao_dia": variacao_dia,
        "exposicao_liquida": exposicao_liquida,
        "exposicao_por_ticker": dict(exposicao_por_ticker),
        "exposicao_parcial": exposicao_parcial,
        "preco_por_ticker": preco_por_ticker,
    }


def alertas_cliente(db: Session, cliente_id: int) -> list[Alerta]:
    """Gera os alertas de posicao (item 5) para um unico cliente."""
    visao = montar_visao_posicao(db, cliente_id)
    itens = [
        ItemPosicaoDerivativo(ticker=e["ticker"], vencimento=e["vencimento"], estrutura=e["estrutura"])
        for e in visao["derivativos_estruturas"]
    ]
    return gerar_todos_os_alertas(
        itens=itens,
        preco_atual_por_ticker=visao["preco_por_ticker"],
        exposicao_por_ticker=visao["exposicao_por_ticker"],
        patrimonio_total=visao["patrimonio_total"],
        dias_uteis_limite=DIAS_UTEIS_ALERTA_VENCIMENTO,
    )


def alertas_carteira(db: Session, clientes: list[models.Cliente]) -> list[dict]:
    """Gera alertas para uma lista de clientes (tipicamente a carteira
    visivel ao usuario logado), ja com o cliente anexado para exibicao."""
    resultado: list[dict] = []
    for cliente in clientes:
        for alerta in alertas_cliente(db, cliente.id):
            resultado.append({"cliente": cliente, "alerta": alerta})
    return resultado
