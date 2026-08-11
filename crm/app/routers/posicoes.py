from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, position_view
from app.auth_deps import Forbidden, require_user
from app.database import get_db

router = APIRouter(prefix="/clientes")
templates = Jinja2Templates(directory="app/templates")


@router.get("/{cliente_id}/posicao")
def visao_posicao(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    cliente = db.get(models.Cliente, cliente_id)
    if not cliente or not crud.pode_ver_cliente(db, user, cliente):
        raise Forbidden()

    motivo = crud.determinar_motivo_acesso(db, user, cliente)
    crud.registrar_acesso(db, user, cliente.id, "visualizou_posicao_cliente", motivo)

    visao = position_view.montar_visao_posicao(db, cliente.id)
    alertas = position_view.alertas_cliente(db, cliente.id)

    return templates.TemplateResponse(
        request,
        "cliente_posicao.html",
        {
            "user": user,
            "cliente": cliente,
            "visao": visao,
            "alertas": alertas,
        },
    )
