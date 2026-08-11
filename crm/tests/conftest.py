import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_tmp_dir = tempfile.mkdtemp(prefix="crm_test_")
os.environ.setdefault("CRM_DATA_DIR", _tmp_dir)
os.environ.setdefault("CRM_DATABASE_URL", f"sqlite:///{_tmp_dir}/test_crm.db")
os.environ.setdefault("CRM_SECRET_KEY", "test-secret-key")

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.seed import seed_default_users  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _preparar_banco():
    init_db()
    seed_default_users()
    db = SessionLocal()
    try:
        if not db.query(models.User).filter_by(username="trader2").first():
            db.add(
                models.User(
                    username="trader2",
                    full_name="Segundo Trader",
                    role="trader",
                    password_hash=hash_password("mude-esta-senha"),
                    active=True,
                )
            )
            db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def login(client, username="trader1", password="mude-esta-senha"):
    resp = client.post(
        "/login", data={"username": username, "password": password, "next": "/"}, follow_redirects=False
    )
    assert resp.status_code == 303, resp.text
    return resp
