"""
CRM offline da mesa de sales trading -- ponto de entrada da aplicacao.

ATENCAO: este processo nao deve nunca fazer chamadas HTTP para fora da
rede interna. Nao adicione clientes de API externos, SDKs de nuvem ou
qualquer biblioteca com telemetria "phone home" habilitada por padrao.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth_deps import Forbidden, NotAuthenticated
from app.config import SECRET_KEY
from app.database import init_db
from app.routers import auditoria, auth, clientes, dashboard, handoffs, interacoes, mural, notas, posicoes
from app.seed import seed_default_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_default_users()
    yield


app = FastAPI(title="CRM Mesa de Sales Trading (offline)", lifespan=lifespan)

# Sessao assinada localmente (itsdangerous) -- nao envolve nenhum servico
# externo de identidade. O cookie guarda apenas o id do usuario e o papel.
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(posicoes.router)
app.include_router(interacoes.router)
app.include_router(notas.router)
app.include_router(handoffs.router)
app.include_router(mural.router)
app.include_router(auditoria.router)
app.include_router(dashboard.router)


@app.exception_handler(NotAuthenticated)
def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(Forbidden)
def handle_forbidden(request: Request, exc: Forbidden):
    return RedirectResponse(url="/?erro=acesso_negado", status_code=303)
