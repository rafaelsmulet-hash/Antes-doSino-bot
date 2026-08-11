import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models
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
        },
    )
