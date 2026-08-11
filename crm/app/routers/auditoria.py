import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auditoria, models
from app.auth_deps import require_visao_mesa
from app.database import get_db

router = APIRouter(prefix="/auditoria")
templates = Jinja2Templates(directory="app/templates")


def _periodo_padrao() -> tuple[dt.date, dt.date]:
    fim = dt.date.today()
    inicio = fim - dt.timedelta(days=30)
    return inicio, fim


def _resolver_periodo(data_inicio: str | None, data_fim: str | None) -> tuple[dt.date, dt.date]:
    inicio_padrao, fim_padrao = _periodo_padrao()
    inicio = dt.date.fromisoformat(data_inicio) if data_inicio else inicio_padrao
    fim = dt.date.fromisoformat(data_fim) if data_fim else fim_padrao
    return inicio, fim


@router.get("")
def relatorio_auditoria(
    request: Request,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    trader_id: int | None = None,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    inicio, fim = _resolver_periodo(data_inicio, data_fim)
    inicio_dt = dt.datetime.combine(inicio, dt.time.min)
    fim_dt = dt.datetime.combine(fim, dt.time.max)

    relatorio = auditoria.gerar_relatorio(db, inicio_dt, fim_dt, trader_id, cliente_id)

    traders = db.execute(select(models.User).where(models.User.role == "trader")).scalars().all()
    clientes = db.execute(select(models.Cliente).order_by(models.Cliente.nome)).scalars().all()

    return templates.TemplateResponse(
        request,
        "auditoria.html",
        {
            "user": user,
            "relatorio": relatorio,
            "traders": traders,
            "clientes": clientes,
            "data_inicio": inicio,
            "data_fim": fim,
            "trader_id": trader_id,
            "cliente_id": cliente_id,
        },
    )


@router.get("/export.csv")
def exportar_auditoria_csv(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    trader_id: int | None = None,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_visao_mesa),
):
    inicio, fim = _resolver_periodo(data_inicio, data_fim)
    inicio_dt = dt.datetime.combine(inicio, dt.time.min)
    fim_dt = dt.datetime.combine(fim, dt.time.max)

    relatorio = auditoria.gerar_relatorio(db, inicio_dt, fim_dt, trader_id, cliente_id)
    conteudo_csv = auditoria.exportar_csv(relatorio)

    nome_arquivo = f"auditoria_{inicio.isoformat()}_a_{fim.isoformat()}.csv"
    return Response(
        content=conteudo_csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
