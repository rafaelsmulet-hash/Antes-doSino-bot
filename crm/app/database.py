"""
Conexao com o banco local (SQLite por padrao).

Nenhum driver de rede externo e usado aqui. Para o cenario multiusuario,
basta trocar CRM_DATABASE_URL (ver app/config.py) para uma URL
postgresql://... apontando para o servidor PostgreSQL da rede interna da
mesa -- a aplicacao nao muda.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import app.models  # noqa: F401  garante que os modelos estao registrados
    Base.metadata.create_all(bind=engine)
