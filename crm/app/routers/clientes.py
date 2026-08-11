import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models
from app.auth_deps import Forbidden, require_user
from app.database import get_db

router = APIRouter(prefix="/clientes")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def listar_clientes(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    stmt = crud.clientes_visiveis_query(db, user)
    if q:
        termo = f"%{q.strip()}%"
        stmt = stmt.where(models.Cliente.nome.ilike(termo) | models.Cliente.codigo.ilike(termo))
    clientes = db.execute(stmt.order_by(models.Cliente.nome)).scalars().all()
    return templates.TemplateResponse(
        request,
        "clientes_list.html",
        {"user": user, "clientes": clientes, "q": q},
    )


@router.get("/novo")
def novo_cliente_form(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    traders = db.execute(select(models.User).where(models.User.role == "trader")).scalars().all()
    return templates.TemplateResponse(
        request,
        "cliente_form.html",
        {"user": user, "traders": traders, "cliente": None, "erro": None},
    )


@router.post("/novo")
def criar_cliente(
    request: Request,
    codigo: str = Form(...),
    nome: str = Form(...),
    tipo: str = Form(...),
    book: str = Form(""),
    perfil_risco: str = Form(""),
    trader_titular_id: int = Form(...),
    tags: str = Form(""),
    produtos: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    existente = db.execute(
        select(models.Cliente).where(models.Cliente.codigo == codigo.strip())
    ).scalar_one_or_none()
    if existente:
        traders = db.execute(select(models.User).where(models.User.role == "trader")).scalars().all()
        return templates.TemplateResponse(
            request,
            "cliente_form.html",
            {
                "user": user,
                "traders": traders,
                "cliente": None,
                "erro": f"Ja existe um cliente com o codigo {codigo}.",
            },
            status_code=400,
        )

    cliente = models.Cliente(
        codigo=codigo.strip(),
        nome=nome.strip(),
        tipo=tipo,
        book=book.strip() or None,
        perfil_risco=perfil_risco.strip() or None,
        trader_titular_id=trader_titular_id,
        data_cadastro=dt.date.today(),
    )
    db.add(cliente)
    db.flush()

    for nome_tag in [t.strip() for t in tags.split(",") if t.strip()]:
        tag = db.execute(select(models.Tag).where(models.Tag.nome == nome_tag)).scalar_one_or_none()
        if not tag:
            tag = models.Tag(nome=nome_tag)
            db.add(tag)
            db.flush()
        cliente.tags.append(tag)

    for produto in [p.strip() for p in produtos.split(",") if p.strip()]:
        db.add(models.ClienteProduto(cliente_id=cliente.id, produto=produto))

    db.commit()
    return RedirectResponse(url=f"/clientes/{cliente.id}", status_code=303)


@router.get("/{cliente_id}")
def detalhe_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    cliente = db.get(models.Cliente, cliente_id)
    if not cliente or not crud.pode_ver_cliente(db, user, cliente):
        raise Forbidden()

    if user.role in ("head_mesa", "compliance"):
        crud.registrar_acesso(db, user, cliente.id, "visualizou_ficha_cliente")

    interacoes = db.execute(
        select(models.Interacao)
        .where(models.Interacao.cliente_id == cliente.id)
        .order_by(models.Interacao.timestamp.desc())
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "cliente_detail.html",
        {
            "user": user,
            "cliente": cliente,
            "interacoes": interacoes,
            "canais": models.CANAIS_INTERACAO,
            "sentimentos": models.SENTIMENTOS,
        },
    )
