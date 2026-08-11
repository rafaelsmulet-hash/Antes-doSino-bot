"""Dependencias de autenticacao/autorizacao baseadas em sessao de cookie local.

Nao ha integracao obrigatoria com identidade externa (AD/LDAP e um hook
opcional de fase futura, fora do escopo do MVP).
"""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


class NotAuthenticated(Exception):
    """Levantada quando nao ha sessao valida. Tratada em app/main.py."""


class Forbidden(Exception):
    """Levantada quando o usuario autenticado nao tem papel suficiente."""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise NotAuthenticated()
    user = db.get(models.User, user_id)
    if not user or not user.active:
        raise NotAuthenticated()
    return user


def require_roles(*roles: str):
    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if roles and user.role not in roles:
            raise Forbidden()
        return user

    return dependency


# Qualquer usuario autenticado, de qualquer papel.
require_user = require_roles()
# Somente head da mesa e compliance (visao ampla da mesa).
require_visao_mesa = require_roles("head_mesa", "compliance")
