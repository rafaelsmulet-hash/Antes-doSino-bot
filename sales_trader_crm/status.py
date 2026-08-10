"""Regras de status de contato: dias desde o último contato e cor do alerta."""
from datetime import date

CONTACT_LIMIT_DAYS = 60
WARNING_THRESHOLD_DAYS = 20  # amarelo quando restam <= 20 dias


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def days_since(last_contact_date: str, today: date | None = None) -> int:
    today = today or date.today()
    return (today - parse_date(last_contact_date)).days


def days_remaining(last_contact_date: str, today: date | None = None) -> int:
    return CONTACT_LIMIT_DAYS - days_since(last_contact_date, today)


def status_for(last_contact_date: str, today: date | None = None) -> str:
    """Retorna 'red', 'yellow' ou 'green' conforme os dias restantes até o limite de 60 dias."""
    remaining = days_remaining(last_contact_date, today)
    if remaining < 0:
        return "red"
    if remaining <= WARNING_THRESHOLD_DAYS:
        return "yellow"
    return "green"


def client_status(last_contact_date: str | None, today: date | None = None) -> dict:
    """Monta o pacote de informações de status usado nas telas.

    last_contact_date=None cobre o caso defensivo de cliente sem nenhum
    contato registrado; na prática o cadastro sempre cria o contato inicial.
    """
    if last_contact_date is None:
        return {
            "last_contact_date": None,
            "days_since": None,
            "days_remaining": None,
            "status": "red",
        }
    return {
        "last_contact_date": last_contact_date,
        "days_since": days_since(last_contact_date, today),
        "days_remaining": days_remaining(last_contact_date, today),
        "status": status_for(last_contact_date, today),
    }
