from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    return templates.TemplateResponse(
        request, "login.html", {"erro": None, "next": next}
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(models.User).where(models.User.username == username.strip().lower())
    ).scalar_one_or_none()

    if not user or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Usuario ou senha invalidos.", "next": next},
            status_code=401,
        )

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    request.session["full_name"] = user.full_name
    return RedirectResponse(url=next or "/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/logout")
def logout_get(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
