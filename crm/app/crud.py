"""Regras de acesso e consultas compartilhadas pelas rotas.

Regra de visibilidade de carteira:
    - trader: apenas clientes cujo trader_titular e ele mesmo, mais
      clientes explicitamente compartilhados com ele (ClienteCompartilhamento).
    - head_mesa / compliance: todos os clientes. Todo acesso de
      head_mesa/compliance a um cliente especifico e registrado em
      AccessLog para trilha de auditoria.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def clientes_visiveis_query(db: Session, user: models.User):
    """Retorna a query base de clientes visiveis para o usuario."""
    stmt = select(models.Cliente).where(models.Cliente.ativo.is_(True))
    if user.role in ("head_mesa", "compliance"):
        return stmt
    compartilhados_ids = select(models.ClienteCompartilhamento.cliente_id).where(
        models.ClienteCompartilhamento.user_id == user.id
    )
    return stmt.where(
        (models.Cliente.trader_titular_id == user.id)
        | (models.Cliente.id.in_(compartilhados_ids))
    )


def pode_ver_cliente(db: Session, user: models.User, cliente: models.Cliente) -> bool:
    if user.role in ("head_mesa", "compliance"):
        return True
    if cliente.trader_titular_id == user.id:
        return True
    compartilhado = db.execute(
        select(models.ClienteCompartilhamento).where(
            models.ClienteCompartilhamento.cliente_id == cliente.id,
            models.ClienteCompartilhamento.user_id == user.id,
        )
    ).scalar_one_or_none()
    return compartilhado is not None


def registrar_acesso(db: Session, user: models.User, cliente_id: int | None, acao: str) -> None:
    """Grava trilha de auditoria. Chamado sempre que head_mesa/compliance
    (ou qualquer usuario) abre a ficha detalhada de um cliente."""
    log = models.AccessLog(
        user_id=user.id,
        cliente_id=cliente_id,
        acao=acao,
        timestamp=dt.datetime.utcnow(),
    )
    db.add(log)
    db.commit()


def clientes_sem_contato(db: Session, user: models.User, dias: int) -> list[dict]:
    """Clientes visiveis ao usuario sem nenhuma interacao ha mais de `dias` dias
    (ou nunca contatados)."""
    limite = dt.datetime.utcnow() - dt.timedelta(days=dias)
    clientes = db.execute(clientes_visiveis_query(db, user)).scalars().all()
    resultado = []
    for cliente in clientes:
        ultima = db.execute(
            select(models.Interacao.timestamp)
            .where(models.Interacao.cliente_id == cliente.id)
            .order_by(models.Interacao.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        if ultima is None or ultima < limite:
            resultado.append({"cliente": cliente, "ultima_interacao": ultima})
    resultado.sort(key=lambda r: r["ultima_interacao"] or dt.datetime.min)
    return resultado


def followups_pendentes(db: Session, user: models.User, ate: dt.date) -> list[models.Interacao]:
    """Follow-ups com data <= `ate` cujo cliente nao recebeu nenhuma interacao
    posterior a data do follow-up (regra deterministica de "ainda pendente")."""
    clientes_ids = {c.id for c in db.execute(clientes_visiveis_query(db, user)).scalars().all()}
    if not clientes_ids:
        return []
    candidatas = db.execute(
        select(models.Interacao)
        .where(
            models.Interacao.cliente_id.in_(clientes_ids),
            models.Interacao.follow_up_data.is_not(None),
            models.Interacao.follow_up_data <= ate,
        )
        .order_by(models.Interacao.follow_up_data.asc())
    ).scalars().all()

    pendentes = []
    for interacao in candidatas:
        houve_contato_posterior = db.execute(
            select(models.Interacao.id).where(
                models.Interacao.cliente_id == interacao.cliente_id,
                models.Interacao.timestamp > interacao.timestamp,
            ).limit(1)
        ).scalar_one_or_none()
        if not houve_contato_posterior:
            pendentes.append(interacao)
    return pendentes


def feed_interacoes_recentes(db: Session, user: models.User, limite: int = 30) -> list[models.Interacao]:
    stmt = (
        select(models.Interacao)
        .join(models.Cliente, models.Interacao.cliente_id == models.Cliente.id)
        .order_by(models.Interacao.timestamp.desc())
        .limit(limite)
    )
    if user.role not in ("head_mesa", "compliance"):
        compartilhados_ids = select(models.ClienteCompartilhamento.cliente_id).where(
            models.ClienteCompartilhamento.user_id == user.id
        )
        stmt = stmt.where(
            (models.Cliente.trader_titular_id == user.id)
            | (models.Cliente.id.in_(compartilhados_ids))
        )
    return db.execute(stmt).scalars().all()
