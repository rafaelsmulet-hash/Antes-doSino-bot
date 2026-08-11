"""Regras de acesso e consultas compartilhadas pelas rotas.

Regra de visibilidade de carteira:
    - trader: clientes cujo trader_titular e ele mesmo, mais clientes
      explicitamente compartilhados (ClienteCompartilhamento), mais
      clientes cobertos por um Handoff ativo em que ele e o destino
      (carteira inteira do trader de origem, ou um cliente especifico).
    - head_mesa / compliance: todos os clientes.

Todo acesso a ficha ou posicao de um cliente e registrado em AccessLog
(item 10 da Fase 3), com o motivo do acesso (TITULAR, COMPARTILHADO,
HANDOFF, HEAD_MESA ou COMPLIANCE) -- essa trilha e a base do relatorio de
auditoria (item 9).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def _handoff_esta_ativo_clausula(agora: dt.datetime):
    return (models.Handoff.fim.is_(None)) | (models.Handoff.fim > agora)


def clientes_visiveis_query(db: Session, user: models.User):
    """Retorna a query base de clientes visiveis para o usuario."""
    stmt = select(models.Cliente).where(models.Cliente.ativo.is_(True))
    if user.role in ("head_mesa", "compliance"):
        return stmt

    agora = dt.datetime.utcnow()
    handoff_ativo = _handoff_esta_ativo_clausula(agora)

    compartilhados_ids = select(models.ClienteCompartilhamento.cliente_id).where(
        models.ClienteCompartilhamento.user_id == user.id
    )
    handoff_carteiras_origem_ids = select(models.Handoff.trader_origem_id).where(
        models.Handoff.trader_destino_id == user.id,
        models.Handoff.cliente_id.is_(None),
        handoff_ativo,
    )
    handoff_clientes_ids = select(models.Handoff.cliente_id).where(
        models.Handoff.trader_destino_id == user.id,
        models.Handoff.cliente_id.is_not(None),
        handoff_ativo,
    )

    return stmt.where(
        (models.Cliente.trader_titular_id == user.id)
        | (models.Cliente.id.in_(compartilhados_ids))
        | (models.Cliente.trader_titular_id.in_(handoff_carteiras_origem_ids))
        | (models.Cliente.id.in_(handoff_clientes_ids))
    )


def pode_ver_cliente(db: Session, user: models.User, cliente: models.Cliente) -> bool:
    if user.role in ("head_mesa", "compliance"):
        return True
    encontrado = db.execute(
        clientes_visiveis_query(db, user).where(models.Cliente.id == cliente.id)
    ).scalar_one_or_none()
    return encontrado is not None


def determinar_motivo_acesso(db: Session, user: models.User, cliente: models.Cliente) -> str:
    """Determina, de forma deterministica, por que o usuario pode ver este
    cliente -- usado para preencher AccessLog.motivo."""
    if user.role == "compliance":
        return "COMPLIANCE"
    if user.role == "head_mesa":
        return "HEAD_MESA"
    if cliente.trader_titular_id == user.id:
        return "TITULAR"

    agora = dt.datetime.utcnow()
    handoff = db.execute(
        select(models.Handoff).where(
            models.Handoff.trader_destino_id == user.id,
            _handoff_esta_ativo_clausula(agora),
            (models.Handoff.cliente_id == cliente.id)
            | (
                (models.Handoff.cliente_id.is_(None))
                & (models.Handoff.trader_origem_id == cliente.trader_titular_id)
            ),
        ).limit(1)
    ).scalar_one_or_none()
    if handoff is not None:
        return "HANDOFF"

    return "COMPARTILHADO"


def registrar_acesso(
    db: Session, user: models.User, cliente_id: int | None, acao: str, motivo: str | None = None
) -> None:
    """Grava trilha de auditoria (item 10). Chamado sempre que alguem abre
    a ficha ou a posicao de um cliente especifico."""
    log = models.AccessLog(
        user_id=user.id,
        cliente_id=cliente_id,
        acao=acao,
        motivo=motivo,
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
