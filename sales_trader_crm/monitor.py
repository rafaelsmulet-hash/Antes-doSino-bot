"""Regras de negócio do monitoramento de estruturas: status de barreira,
alertas e parsing de datas em texto livre (dd/mm/aaaa)."""
import re
from datetime import date, datetime

DEFAULT_SETTINGS = {
    "barrier_proximity_pct": 5.0,
    "loss_threshold_pct": -10.0,
    "fixing_alert_days": [5, 2, 1, 0],
}


def parse_flexible_date(raw):
    """Converte dd/mm/aaaa ou aaaa-mm-dd (texto) para ISO aaaa-mm-dd. None se não reconhecer."""
    if not raw:
        return None
    raw = raw.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def days_between(iso_from, iso_to):
    a = date.fromisoformat(iso_from)
    b = date.fromisoformat(iso_to)
    return (b - a).days


def today_iso():
    return date.today().isoformat()


def fixing_days_list(raw_csv):
    days = []
    for part in (raw_csv or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            days.append(int(part))
        except ValueError:
            continue
    return days or list(DEFAULT_SETTINGS["fixing_alert_days"])


def barrier_status_for(estrutura, barrier_proximity_pct):
    """estrutura: dict/Row com barreira_acionada_em e dis_barreira_pct."""
    if estrutura["barreira_acionada_em"]:
        return "atingida"
    dist = estrutura["dis_barreira_pct"]
    if dist is not None and abs(dist) <= barrier_proximity_pct:
        return "proxima"
    return "normal"


def compute_alerts(estruturas, settings):
    """estruturas: lista de dicts/Rows (só as ativas do operador). settings: dict com
    barrier_proximity_pct, loss_threshold_pct, fixing_alert_days (lista de ints)."""
    alerts = []
    today = today_iso()
    barrier_pct = settings["barrier_proximity_pct"]
    loss_pct = settings["loss_threshold_pct"]
    fixing_days = settings["fixing_alert_days"]

    for e in estruturas:
        status = barrier_status_for(e, barrier_pct)

        if status == "atingida":
            alerts.append({
                "type": "barreira_atingida",
                "severity": "critical",
                "estrutura": e,
                "title": f"Barreira atingida — {e['nome_cliente']} · {e['estrutura']}",
                "detail": f"{e['ativo']} · acionada em {e['barreira_acionada_em']}",
            })
        elif status == "proxima":
            alerts.append({
                "type": "barreira_proxima",
                "severity": "warning",
                "estrutura": e,
                "title": f"Barreira próxima — {e['nome_cliente']} · {e['estrutura']}",
                "detail": f"{e['ativo']} · distância {fmt_num(e['dis_barreira_pct'])}%",
            })

        if e["fixing_iso"]:
            days_left = days_between(today, e["fixing_iso"])
            if days_left in fixing_days:
                label = "hoje" if days_left == 0 else f"em {days_left}d"
                alerts.append({
                    "type": "fixing_proximo",
                    "severity": "critical" if days_left <= 1 else "warning",
                    "estrutura": e,
                    "title": f"Fixing {label} — {e['nome_cliente']} · {e['estrutura']}",
                    "detail": f"{e['ativo']} · fixing {e['fixing'] or e['fixing_iso']}",
                })

        if e["resultado_pct"] is not None and e["resultado_pct"] <= loss_pct:
            alerts.append({
                "type": "perda_relevante",
                "severity": "critical",
                "estrutura": e,
                "title": f"Perda relevante — {e['nome_cliente']} · {e['estrutura']}",
                "detail": f"{e['ativo']} · resultado {fmt_pct(e['resultado_pct'])}",
            })

    order = {"critical": 0, "warning": 1}
    alerts.sort(key=lambda a: order[a["severity"]])
    return alerts


def fmt_num(n, decimals=None):
    if n is None:
        return "—"
    if decimals is None:
        decimals = 0 if float(n).is_integer() else 2
    return f"{n:,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_pct(n):
    if n is None:
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{fmt_num(n, 2)}%"


def fmt_money(n):
    if n is None:
        return "—"
    return fmt_num(n, 2)


def build_draft_text(e, barrier_proximity_pct=None):
    if barrier_proximity_pct is None:
        barrier_proximity_pct = DEFAULT_SETTINGS["barrier_proximity_pct"]
    status = barrier_status_for(e, barrier_proximity_pct)
    lines = []
    lines.append(f"Olá {e['nome_cliente'] or ''}, tudo bem?")
    lines.append("")
    lines.append(f"Passando para atualizar sobre a estrutura {e['estrutura'] or '—'} em {e['ativo'] or '—'}:")
    if e["fixing"]:
        lines.append(f"- Fixing: {e['fixing']}")
    if e["dis_barreira_pct"] is not None:
        lines.append(f"- Distância até a barreira: {fmt_num(e['dis_barreira_pct'], 2)}%")
    if e["barreira_acionada_em"]:
        lines.append(f"- A barreira foi ATINGIDA em {e['barreira_acionada_em']}.")
    elif status == "proxima":
        lines.append("- A estrutura está próxima da barreira, vale a pena acompanharmos de perto.")
    if e["resultado_pct"] is not None:
        extra = f" ({fmt_money(e['resultado_rs'])})" if e["resultado_rs"] is not None else ""
        lines.append(f"- Resultado atual: {fmt_pct(e['resultado_pct'])}{extra}")
    lines.append("")
    lines.append("Fico à disposição para conversarmos sobre os próximos passos.")
    lines.append("")
    lines.append("[revisar antes de enviar]")
    return "\n".join(lines)
