import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models
from app.auth_deps import Forbidden, require_user
from app.database import get_db

router = APIRouter(prefix="/interacoes")
templates = Jinja2Templates(directory="app/templates")


@router.get("/nova")
def nova_interacao_form(
    request: Request,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    clientes = db.execute(
        crud.clientes_visiveis_query(db, user).order_by(models.Cliente.nome)
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "interacao_form.html",
        {
            "user": user,
            "clientes": clientes,
            "cliente_id": cliente_id,
            "canais": models.CANAIS_INTERACAO,
            "sentimentos": models.SENTIMENTOS,
            "erro": None,
            "corrige": None,
        },
    )


@router.post("/nova")
def criar_interacao(
    request: Request,
    cliente_id: int = Form(...),
    canal: str = Form(...),
    resumo: str = Form(...),
    tickers_mencionados: str = Form(""),
    sentimento: str = Form(""),
    follow_up_data: str = Form(""),
    corrige_interacao_id: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    cliente = db.get(models.Cliente, cliente_id)
    if not cliente or not crud.pode_ver_cliente(db, user, cliente):
        raise Forbidden()

    tickers = ",".join(t.strip().upper() for t in tickers_mencionados.split(",") if t.strip())
    interacao = models.Interacao(
        cliente_id=cliente.id,
        trader_id=user.id,
        canal=canal,
        timestamp=dt.datetime.utcnow(),
        resumo=resumo.strip(),
        tickers_mencionados=tickers or None,
        sentimento=sentimento or None,
        follow_up_data=dt.date.fromisoformat(follow_up_data) if follow_up_data else None,
        corrige_interacao_id=int(corrige_interacao_id) if corrige_interacao_id else None,
    )
    db.add(interacao)
    db.commit()
    return RedirectResponse(url=f"/clientes/{cliente.id}", status_code=303)


@router.get("/{interacao_id}/corrigir")
def corrigir_interacao_form(
    request: Request,
    interacao_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    original = db.get(models.Interacao, interacao_id)
    if not original or not crud.pode_ver_cliente(db, user, original.cliente):
        raise Forbidden()
    clientes = [original.cliente]
    return templates.TemplateResponse(
        request,
        "interacao_form.html",
        {
            "user": user,
            "clientes": clientes,
            "cliente_id": original.cliente_id,
            "canais": models.CANAIS_INTERACAO,
            "sentimentos": models.SENTIMENTOS,
            "erro": None,
            "corrige": original,
        },
    )
