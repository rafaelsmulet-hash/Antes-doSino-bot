from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth_deps import require_user
from app.database import get_db

router = APIRouter(prefix="/mural")
templates = Jinja2Templates(directory="app/templates")

TAMANHO_MAXIMO_POSTAGEM = 500


@router.get("")
def listar_mural(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    postagens = db.execute(
        select(models.PostagemMural).order_by(models.PostagemMural.criado_em.desc()).limit(100)
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "mural.html",
        {"user": user, "postagens": postagens, "erro": None, "tamanho_maximo": TAMANHO_MAXIMO_POSTAGEM},
    )


@router.post("")
def criar_postagem(
    request: Request,
    texto: str = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    texto = texto.strip()
    if not texto or len(texto) > TAMANHO_MAXIMO_POSTAGEM:
        postagens = db.execute(
            select(models.PostagemMural).order_by(models.PostagemMural.criado_em.desc()).limit(100)
        ).scalars().all()
        return templates.TemplateResponse(
            request,
            "mural.html",
            {
                "user": user,
                "postagens": postagens,
                "erro": f"A postagem deve ter entre 1 e {TAMANHO_MAXIMO_POSTAGEM} caracteres.",
                "tamanho_maximo": TAMANHO_MAXIMO_POSTAGEM,
            },
            status_code=400,
        )

    db.add(models.PostagemMural(autor_id=user.id, texto=texto))
    db.commit()
    return RedirectResponse(url="/mural", status_code=303)
