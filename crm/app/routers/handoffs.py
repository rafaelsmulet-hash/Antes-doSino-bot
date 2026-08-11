import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth_deps import require_visao_mesa
from app.database import get_db

router = APIRouter(prefix="/handoffs")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def listar_handoffs(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    handoffs = db.execute(select(models.Handoff).order_by(models.Handoff.inicio.desc())).scalars().all()
    agora = dt.datetime.utcnow()
    return templates.TemplateResponse(
        request,
        "handoffs_list.html",
        {"user": user, "handoffs": handoffs, "agora": agora},
    )


@router.get("/novo")
def novo_handoff_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    traders = db.execute(select(models.User).where(models.User.role == "trader")).scalars().all()
    clientes = db.execute(select(models.Cliente).where(models.Cliente.ativo.is_(True)).order_by(models.Cliente.nome)).scalars().all()
    return templates.TemplateResponse(
        request,
        "handoff_form.html",
        {"user": user, "traders": traders, "clientes": clientes, "erro": None},
    )


@router.post("/novo")
def criar_handoff(
    request: Request,
    trader_origem_id: int = Form(...),
    trader_destino_id: int = Form(...),
    cliente_id: str = Form(""),
    motivo: str = Form(""),
    fim: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    if trader_origem_id == trader_destino_id:
        traders = db.execute(select(models.User).where(models.User.role == "trader")).scalars().all()
        clientes = db.execute(select(models.Cliente).where(models.Cliente.ativo.is_(True)).order_by(models.Cliente.nome)).scalars().all()
        return templates.TemplateResponse(
            request,
            "handoff_form.html",
            {
                "user": user,
                "traders": traders,
                "clientes": clientes,
                "erro": "Trader de origem e de destino devem ser diferentes.",
            },
            status_code=400,
        )

    handoff = models.Handoff(
        trader_origem_id=trader_origem_id,
        trader_destino_id=trader_destino_id,
        cliente_id=int(cliente_id) if cliente_id else None,
        autorizado_por_id=user.id,
        motivo=motivo.strip() or None,
        inicio=dt.datetime.utcnow(),
        fim=dt.datetime.fromisoformat(fim) if fim else None,
    )
    db.add(handoff)
    db.commit()
    return RedirectResponse(url="/handoffs", status_code=303)


@router.post("/{handoff_id}/encerrar")
def encerrar_handoff(
    handoff_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    handoff = db.get(models.Handoff, handoff_id)
    if handoff and handoff.ativo():
        handoff.fim = dt.datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/handoffs", status_code=303)
