"""Cria usuarios iniciais se o banco estiver vazio.

Em uso real, troque as senhas padrao no primeiro acesso -- elas existem
apenas para permitir o primeiro login em uma instalacao nova.
"""
from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.security import hash_password

USUARIOS_PADRAO = [
    {"username": "head_mesa", "full_name": "Head da Mesa", "role": "head_mesa", "password": "mude-esta-senha"},
    {"username": "compliance", "full_name": "Compliance", "role": "compliance", "password": "mude-esta-senha"},
    {"username": "trader1", "full_name": "Trader Exemplo", "role": "trader", "password": "mude-esta-senha"},
]


def seed_default_users() -> None:
    db = SessionLocal()
    try:
        existe_algum = db.execute(select(models.User.id).limit(1)).scalar_one_or_none()
        if existe_algum:
            return
        for u in USUARIOS_PADRAO:
            db.add(
                models.User(
                    username=u["username"],
                    full_name=u["full_name"],
                    role=u["role"],
                    password_hash=hash_password(u["password"]),
                    active=True,
                )
            )
        db.commit()
    finally:
        db.close()
