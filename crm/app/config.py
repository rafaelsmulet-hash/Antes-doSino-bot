"""
Configuracao central do CRM offline.

Este sistema nunca deve fazer chamadas de rede externas. Todas as
configuracoes abaixo apontam exclusivamente para recursos locais
(arquivo SQLite, pastas de rede interna).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CRM_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("CRM_DATABASE_URL", f"sqlite:///{DATA_DIR / 'crm.db'}")

# Chave de assinatura do cookie de sessao. Em producao, defina via variavel
# de ambiente CRM_SECRET_KEY (nao versionar segredo real no repositorio).
SECRET_KEY = os.environ.get("CRM_SECRET_KEY", "troque-esta-chave-em-producao")

# Pasta de rede interna designada para exportacao de backup do banco.
BACKUP_DIR = Path(os.environ.get("CRM_BACKUP_DIR", BASE_DIR / "data" / "backups"))

# Pasta de rede interna onde o backoffice/custodia deposita arquivos de posicao.
IMPORT_DIR = Path(os.environ.get("CRM_IMPORT_DIR", BASE_DIR / "data" / "importacao"))

# Numero de dias sem contato para um cliente aparecer no alerta do dashboard.
DIAS_SEM_CONTATO_ALERTA = int(os.environ.get("CRM_DIAS_SEM_CONTATO_ALERTA", "10"))

# Dias uteis limite para alerta de vencimento de opcao proximo.
DIAS_UTEIS_ALERTA_VENCIMENTO = int(os.environ.get("CRM_DIAS_UTEIS_ALERTA_VENCIMENTO", "5"))
