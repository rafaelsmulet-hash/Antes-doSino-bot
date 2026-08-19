"""Autenticação por sessão: login simples (usuário/senha), sem provedor externo."""
from functools import wraps

from flask import g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_conn


def hash_password(raw):
    return generate_password_hash(raw)


def verify_password(raw, password_hash):
    return check_password_hash(password_hash, raw)


def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    g.user = dict(row) if row else None
    if g.user is None:
        session.clear()


def current_user():
    return getattr(g, "user", None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("login", next=request.path))
        if not user["is_admin"]:
            return "Acesso restrito ao administrador.", 403
        return view(*args, **kwargs)
    return wrapped
