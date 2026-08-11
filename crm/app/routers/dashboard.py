import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models, position_view
from app.auth_deps import require_user
from app.config import DIAS_SEM_CONTATO_ALERTA
from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(
    request: Request,
    dias: int = DIAS_SEM_CONTATO_ALERTA,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    hoje = dt.date.today()
    sem_contato = crud.clientes_sem_contato(db, user, dias)
    followups = crud.followups_pendentes(db, user, hoje)
    feed = crud.feed_interacoes_recentes(db, user, limite=30)

    clientes_com_derivativo_ids = set(
        db.execute(select(models.PosicaoDerivativo.cliente_id).distinct()).scalars().all()
    )
    clientes_visiveis = db.execute(crud.clientes_visiveis_query(db, user)).scalars().all()
    clientes_com_posicao = [c for c in clientes_visiveis if c.id in clientes_com_derivativo_ids]
    alertas_posicao = position_view.alertas_carteira(db, clientes_com_posicao)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "hoje": hoje,
            "dias": dias,
            "sem_contato": sem_contato,
            "followups": followups,
            "feed": feed,
            "alertas_posicao": alertas_posicao,
        },
    )
