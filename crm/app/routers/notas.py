from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth_deps import Forbidden, require_user
from app.database import get_db

router = APIRouter(prefix="/clientes")


@router.post("/{cliente_id}/notas")
def criar_nota_interna(
    cliente_id: int,
    texto: str = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    cliente = db.get(models.Cliente, cliente_id)
    if not cliente or not crud.pode_ver_cliente(db, user, cliente):
        raise Forbidden()

    texto = texto.strip()
    if texto:
        db.add(models.NotaInterna(cliente_id=cliente.id, autor_id=user.id, texto=texto))
        db.commit()

    return RedirectResponse(url=f"/clientes/{cliente.id}#notas", status_code=303)
