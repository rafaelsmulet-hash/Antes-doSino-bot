"""
Relatorio de auditoria exportavel (item 9 da Fase 3).

Consolida, para um periodo (e opcionalmente um trader e/ou cliente):
    - interacoes registradas (o log de contato com o cliente, ja
      append-only -- inclui qualquer recomendacao dada verbalmente ao
      cliente, registrada no campo `resumo` pelo proprio trader);
    - acessos a dados de cliente fora da carteira titular do usuario
      (AccessLog com motivo != TITULAR: COMPARTILHADO, HANDOFF,
      HEAD_MESA ou COMPLIANCE).

So le dados ja registrados por outras partes do sistema -- nao cria nem
infere nenhum registro novo. Uso exclusivo de compliance/head_mesa.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def buscar_interacoes(
    db: Session,
    inicio: dt.datetime,
    fim: dt.datetime,
    trader_id: int | None = None,
    cliente_id: int | None = None,
) -> list[models.Interacao]:
    stmt = select(models.Interacao).where(
        models.Interacao.timestamp >= inicio, models.Interacao.timestamp <= fim
    )
    if trader_id:
        stmt = stmt.where(models.Interacao.trader_id == trader_id)
    if cliente_id:
        stmt = stmt.where(models.Interacao.cliente_id == cliente_id)
    return list(db.execute(stmt.order_by(models.Interacao.timestamp)).scalars().all())


def buscar_acessos_fora_da_carteira_titular(
    db: Session,
    inicio: dt.datetime,
    fim: dt.datetime,
    trader_id: int | None = None,
    cliente_id: int | None = None,
) -> list[models.AccessLog]:
    stmt = select(models.AccessLog).where(
        models.AccessLog.timestamp >= inicio,
        models.AccessLog.timestamp <= fim,
        models.AccessLog.motivo.is_not(None),
        models.AccessLog.motivo != "TITULAR",
    )
    if trader_id:
        stmt = stmt.where(models.AccessLog.user_id == trader_id)
    if cliente_id:
        stmt = stmt.where(models.AccessLog.cliente_id == cliente_id)
    return list(db.execute(stmt.order_by(models.AccessLog.timestamp)).scalars().all())


def gerar_relatorio(
    db: Session,
    inicio: dt.datetime,
    fim: dt.datetime,
    trader_id: int | None = None,
    cliente_id: int | None = None,
) -> dict:
    return {
        "interacoes": buscar_interacoes(db, inicio, fim, trader_id, cliente_id),
        "acessos_fora_titular": buscar_acessos_fora_da_carteira_titular(db, inicio, fim, trader_id, cliente_id),
    }


def exportar_csv(relatorio: dict) -> str:
    """Serializa o relatorio em um unico CSV, com uma coluna `tipo_registro`
    para distinguir interacoes de acessos fora da carteira titular."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["tipo_registro", "timestamp", "usuario", "cliente_codigo", "canal_ou_motivo", "detalhe"]
    )
    for i in relatorio["interacoes"]:
        writer.writerow(
            [
                "INTERACAO",
                i.timestamp.isoformat(),
                i.trader.full_name,
                i.cliente.codigo,
                i.canal,
                i.resumo.replace("\n", " ").replace(";", ","),
            ]
        )
    for a in relatorio["acessos_fora_titular"]:
        writer.writerow(
            [
                "ACESSO_FORA_TITULAR",
                a.timestamp.isoformat(),
                a.user.full_name if a.user else "",
                a.cliente.codigo if a.cliente else "",
                a.motivo or "",
                a.acao,
            ]
        )
    return buffer.getvalue()
