"""Executa o CRM localmente: `python run.py`.

Sobe um servidor uvicorn em 127.0.0.1 (ou no IP interno definido por
CRM_HOST) -- nunca exposto diretamente a internet.
"""
import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("CRM_HOST", "127.0.0.1")
    port = int(os.environ.get("CRM_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
