"""
Rotina de backup do CRM.

Copia o arquivo SQLite (via `sqlite3 .backup`, seguro para banco em uso)
para a pasta de rede interna definida em CRM_BACKUP_DIR. Nao envia dados
para nenhum servico externo -- o destino e sempre um caminho de disco
local ou de compartilhamento de rede interno (ex: \\\\servidor\\backups\\crm
montado localmente, ou um caminho NFS/SMB interno).

Uso:
    python scripts/backup.py
    python scripts/backup.py --destino /caminho/de/rede/interna
"""
import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BACKUP_DIR, DATABASE_URL  # noqa: E402


def caminho_banco_sqlite(database_url: str) -> Path:
    if not database_url.startswith("sqlite"):
        raise SystemExit(
            "Backup automatico via este script so cobre SQLite. Para "
            "PostgreSQL, use pg_dump apontando para o servidor interno da mesa."
        )
    caminho = database_url.split("sqlite:///", 1)[1]
    return Path(caminho)


def executar_backup(destino_dir: Path) -> Path:
    origem = caminho_banco_sqlite(DATABASE_URL)
    if not origem.exists():
        raise SystemExit(f"Banco nao encontrado em {origem}.")

    destino_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = destino_dir / f"crm_backup_{timestamp}.db"

    origem_conn = sqlite3.connect(str(origem))
    destino_conn = sqlite3.connect(str(destino))
    with destino_conn:
        origem_conn.backup(destino_conn)
    origem_conn.close()
    destino_conn.close()
    return destino


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup do banco do CRM para pasta de rede interna.")
    parser.add_argument("--destino", type=str, default=None, help="Pasta de destino (default: CRM_BACKUP_DIR).")
    args = parser.parse_args()

    destino_dir = Path(args.destino) if args.destino else BACKUP_DIR
    caminho_final = executar_backup(destino_dir)
    print(f"Backup gravado em: {caminho_final}")
