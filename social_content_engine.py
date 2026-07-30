"""
Social Content Engine - Antes do Sino
========================================

Modulo TOTALMENTE ISOLADO do main.py. Nao importa nenhuma funcao
interna do bot principal - recebe tudo pronto por parametro (dados ja
calculados pelo main() em cada execucao).

Arquitetura (v3 - unificada, sem fluxos paralelos):

    content_mode (opening/breaking/midday/closing)
        │
        ▼
    gerar_conteudo_unificado() ou gerar_conteudo_midday_unificado()
        │  (headline -> instagram -> x -> tiktok, sempre a MESMA forma,
        │   independente do modo - so muda COMO o conteudo e produzido:
        │   IA para opening/breaking/closing, template determinístico
        │   para midday)
        ▼
    item salvo em docs/social_queue.json, status="draft"
        │
        ▼
    notificacao privada no Telegram (preview + ID + instrucao de resposta)
        │
        ▼   (voce responde "Aprovar <ID>" ou "Rejeitar <ID>")
        ▼
    checar_aprovacoes_pendentes() [roda todo ciclo] atualiza o status
        │
        ▼
    status="approved"  -->  social_design_engine gera o ativo visual
        │                    certo (carrossel/card/roteiro, conforme
        │                    TEMPLATE_MAP + DESIGN_MAP - nunca assume
        │                    formato fixo por modo)
        ▼
    status="designed"  (pronto para publicacao manual)
        │
        ▼
    status="published" (RESERVADO para o futuro - nao implementado
                         nesta fase)

Todo conteudo, de qualquer modo, passa pela MESMA maquina de estados.
Nao existe fluxo paralelo para nenhum modo, incluindo Midday.
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone

import requests

BR_TZ = timezone(timedelta(hours=-3))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_AI = bool(GROQ_API_KEY)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

SOCIAL_QUEUE_FILE = "docs/social_queue.json"
BREAKING_STATE_FILE = "docs/social_breaking_state.json"
OPENING_STATE_FILE = "docs/social_opening_state.json"
MIDDAY_STATE_FILE = "docs/social_midday_state.json"
CLOSING_STATE_FILE = "docs/social_content_state.json"
TELEGRAM_OFFSET_FILE = "docs/telegram_updates_offset.json"

# Versao do prompt - registrada em CADA item gerado, para permitir
# comparar desempenho entre versoes quando o prompt for melhorado no
# futuro (A/B de prompt).
PROMPT_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# Duas camadas independentes: modo -> template editorial -> tipo de
# ativo visual. O design NUNCA assume formato fixo por modo - ele so
# conhece o template, e o template e quem diz o tipo de ativo.
# ---------------------------------------------------------------------------

TEMPLATE_MAP = {
    "opening": "deep_dive",
    "closing": "deep_dive",
    "breaking": "quick_insight",
    "midday": "market_snapshot",
}

DESIGN_MAP = {
    "deep_dive": "carousel",
    "quick_insight": "card",
    "market_snapshot": "card",
}

# ---------------------------------------------------------------------------
# Parametros de frequencia/selecao - ponto de partida, calibravel.
# ---------------------------------------------------------------------------

LIMIAR_BREAKING = 6
INTERVALO_MINIMO_BREAKING_MINUTOS = 60
MAX_BREAKING_POR_DIA = 3
LIMIAR_MOVIMENTO_FORTE = 2.0  # %

OPENING_JANELA_INICIO_MINUTOS = 9 * 60
OPENING_JANELA_FIM_MINUTOS = 9 * 60 + 30

MIDDAY_JANELA_INICIO_MINUTOS = 12 * 60
MIDDAY_JANELA_FIM_MINUTOS = 12 * 60 + 15

CLOSING_JANELA_INICIO_MINUTOS = 18 * 60 + 30
CLOSING_JANELA_FIM_MINUTOS = 19 * 60

ENTIDADES_ALTO_IMPACTO = [
    "petrobras", "vale", "itau", "itaú", "bradesco", "banco do brasil",
    "santander", "dolar", "dólar", "juros", "selic", "copom", "fed",
    "fomc", "powell", "campos neto",
]

MARCADORES_POTENCIAL_EDUCACIONAL = [
    "porque", "por que", "entenda", "impacto", "explica", "resultado de",
    "por tras", "consequencia", "o que muda", "reflete", "sinaliza",
]

MARCADORES_EVENTO_MACRO = ["copom", "fed", "fomc", "payroll", "cpi", "selic"]

MARCADORES_MUDANCA_ATENCAO = ["ganhou atenção", "saiu do radar"]


# ---------------------------------------------------------------------------
# Estado - cada modo tem arquivo proprio, isolado
# ---------------------------------------------------------------------------

def _load_json_seguro(caminho, default):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save_json(caminho, dado):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=2)


def load_breaking_state():
    return _load_json_seguro(BREAKING_STATE_FILE, {
        "date": "", "count_today": 0, "last_breaking_at": "", "topicos_publicados_hoje": [],
    })


def save_breaking_state(state):
    _save_json(BREAKING_STATE_FILE, state)


def load_opening_state():
    return _load_json_seguro(OPENING_STATE_FILE, {"last_opening_date": ""})


def save_opening_state(state):
    _save_json(OPENING_STATE_FILE, state)


def load_midday_state():
    return _load_json_seguro(MIDDAY_STATE_FILE, {"last_midday_date": ""})


def save_midday_state(state):
    _save_json(MIDDAY_STATE_FILE, state)


def load_social_content_state():
    return _load_json_seguro(CLOSING_STATE_FILE, {"last_social_content_date": ""})


def save_social_content_state(state):
    _save_json(CLOSING_STATE_FILE, state)


def load_telegram_offset():
    return _load_json_seguro(TELEGRAM_OFFSET_FILE, {"offset": 0})


def save_telegram_offset(state):
    _save_json(TELEGRAM_OFFSET_FILE, state)


# ---------------------------------------------------------------------------
# IA isolada - mesma chave, zero import de main.py
# ---------------------------------------------------------------------------

GROQ_MODEL_LIGHT = "llama-3.1-8b-instant"
GROQ_MODEL_STRONG = "llama-3.3-70b-versatile"


def ask_groq_isolado(prompt, purpose="generation"):
    """Camada centralizada de chamada a Groq, isolada do main.py (nao
    reaproveita a funcao equivalente de la, por design). 'purpose'
    escolhe o modelo:
      purpose="generation" -> modelo FORTE (llama-3.3-70b-versatile)
                               geracao de conteudo final (headline +
                               instagram/x/tiktok) - e o uso padrao
                               deste modulo.
      purpose="analysis"   -> modelo LEVE (llama-3.1-8b-instant)
                               usado so na segunda validacao do
                               Breaking (triagem true/false, nao
                               geracao de texto)."""
    modelo = GROQ_MODEL_LIGHT if purpose == "analysis" else GROQ_MODEL_STRONG

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        data = response.json()
    except Exception as e:
        print("Erro de rede na chamada Groq isolada (" + purpose + "/" + modelo + "): " + str(e))
        raise

    if "choices" not in data:
        erro = data.get("error", {}) if isinstance(data, dict) else {}
        codigo_erro = erro.get("code", "")
        mensagem_erro = erro.get("message", str(data))
        if codigo_erro == "rate_limit_exceeded":
            print("AVISO (rate limit Groq, " + purpose + "/" + modelo + "): " + mensagem_erro)
        else:
            print("Erro na resposta da Groq isolada (" + purpose + "/" + modelo + "): " + mensagem_erro)
        raise ValueError("Resposta sem choices: " + str(data))

    return data["choices"][0]["message"]["content"].strip()


def extract_json_object_isolado(raw_text):
    raw_text = re.sub(r"```[a-zA-Z]*", "", raw_text).replace("```", "").strip()
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = raw_text[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _formata_variacao(change):
    sign = "+" if change >= 0 else ""
    return sign + str(round(change, 2)) + "%"


def _coletar_movimentos_mercado(market_snapshot):
    candidatos = []
    if not market_snapshot:
        return candidatos
    quotes_by_symbol = market_snapshot.get("quotes_by_symbol", {}) or {}
    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa and ibovespa.get("change") is not None:
        candidatos.append(("Ibovespa", ibovespa["change"]))
    for nome, campo in [("Dólar", "usd"), ("Bitcoin", "bitcoin"), ("Petróleo (WTI)", "wti")]:
        dado = market_snapshot.get(campo)
        if dado and dado.get("change") is not None:
            candidatos.append((nome, dado["change"]))
    sp500 = market_snapshot.get("sp500")
    if sp500 and sp500.get("change") is not None:
        candidatos.append(("S&P 500", sp500["change"]))
    return candidatos


def _evento_macro_e_hoje(events):
    hoje = datetime.now(BR_TZ).date()
    for ev in events or []:
        try:
            data_evento = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if data_evento != hoje:
            continue
        texto = (ev.get("label", "") + " " + " ".join(ev.get("keywords", []))).lower()
        if any(m in texto for m in MARCADORES_EVENTO_MACRO):
            return ev
    return None


def gerar_id_unico():
    """ID simples e legivel: timestamp com precisao de microssegundo -
    evita colisao quando 2 itens sao gerados no mesmo segundo (ex: dois
    modos disparando no mesmo ciclo de 5 min)."""
    agora = datetime.now(BR_TZ)
    return agora.strftime("%Y%m%d-%H%M%S-%f")[:-3]


def _calcular_expiracao(content_mode):
    """Cada modo tem uma janela de validade natural - depois disso, o
    conteudo perde o timing mesmo que ainda nao tenha sido aprovado."""
    agora = datetime.now(BR_TZ)
    if content_mode == "breaking":
        return agora + timedelta(hours=2)
    if content_mode == "opening":
        return agora.replace(hour=11, minute=0, second=0, microsecond=0)
    if content_mode == "midday":
        return agora.replace(hour=15, minute=0, second=0, microsecond=0)
    if content_mode == "closing":
        amanha = agora + timedelta(days=1)
        return amanha.replace(hour=9, minute=0, second=0, microsecond=0)
    return agora + timedelta(hours=6)


def _prioridade_por_modo(content_mode):
    return {"breaking": "high", "opening": "high", "midday": "medium", "closing": "medium"}.get(content_mode, "medium")


# ---------------------------------------------------------------------------
# Geracao de conteudo unificada - headline primeiro, depois os 3
# formatos a partir dela. Usada por Opening, Breaking e Closing.
# ---------------------------------------------------------------------------

def montar_prompt_unificado(assunto, entries_today, content_mode):
    manchetes_apoio = ""
    for e in (entries_today or [])[:8]:
        manchetes_apoio += "- " + e.get("title", "") + "\n"

    return (
        "Voce e o redator de conteudo do canal 'Antes do Sino', especializado em "
        "educacao financeira e contexto de mercado para redes sociais. Use SOMENTE "
        "os fatos e numeros fornecidos abaixo - nunca invente dado, numero ou "
        "informacao que nao esteja explicitamente aqui. Nunca de opiniao de "
        "investimento. Priorize educacao e contexto, nunca sensacionalismo.\n\n"
        "ASSUNTO PRINCIPAL:\n" + assunto["titulo"] + "\n\n"
        "CONTEXTO DISPONIVEL:\n" + assunto["contexto"] + "\n\n"
        "MANCHETES DE APOIO:\n" + manchetes_apoio + "\n\n"
        "Gere PRIMEIRO uma headline central, e depois os 3 formatos DERIVADOS "
        "dessa mesma headline (mesma ideia central em todos):\n\n"
        "1. headline: frase unica, direta, que resume o assunto.\n\n"
        "2. instagram (campos separados, cada um sera usado como bloco de "
        "conteudo - pode virar carrossel ou card unico dependendo do formato "
        "escolhido depois, entao cada campo deve fazer sentido sozinho):\n"
        "   hook: gancho forte de abertura\n"
        "   context: o que aconteceu, direto\n"
        "   why_it_matters: por que o mercado reagiu\n"
        "   impact: impacto no mercado (indices/acoes/setores relacionados)\n"
        "   watch_next: o que monitorar agora (proximos eventos ou riscos)\n"
        "   cta: encerramento discreto convidando a acompanhar o Antes do Sino\n\n"
        "3. x: post unico para X/Twitter, MAXIMO 280 caracteres, com angulo "
        "explicativo (nunca so a manchete pura).\n\n"
        "4. tiktok: roteiro falado de ate 45 segundos, em cenas:\n"
        "   scenes: lista de objetos {\"visual\": \"o que aparece na tela\", "
        "\"line\": \"fala do narrador\"}\n"
        "   cta: fechamento com convite discreto\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "...", "cta": "..."}, '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )


def validar_conteudo_unificado(parsed):
    """Validacao defensiva - qualquer campo ausente ou malformado usa
    fallback vazio, nunca quebra a montagem final."""
    if not isinstance(parsed, dict):
        return None

    headline = parsed.get("headline", "")
    headline = str(headline).strip() if isinstance(headline, str) else ""
    if not headline:
        return None

    ig = parsed.get("instagram", {})
    if not isinstance(ig, dict):
        ig = {}
    instagram = {}
    for campo in ["hook", "context", "why_it_matters", "impact", "watch_next", "cta"]:
        valor = ig.get(campo, "")
        instagram[campo] = str(valor).strip() if isinstance(valor, str) else ""

    x_obj = parsed.get("x", {})
    post = x_obj.get("post", "") if isinstance(x_obj, dict) else ""
    post = str(post).strip()[:280] if isinstance(post, str) else ""

    tk = parsed.get("tiktok", {})
    if not isinstance(tk, dict):
        tk = {}
    scenes_raw = tk.get("scenes", [])
    scenes = []
    if isinstance(scenes_raw, list):
        for cena in scenes_raw:
            if isinstance(cena, dict):
                scenes.append({
                    "visual": str(cena.get("visual", "")).strip(),
                    "line": str(cena.get("line", "")).strip(),
                })
    tiktok_cta = tk.get("cta", "")
    tiktok_cta = str(tiktok_cta).strip() if isinstance(tiktok_cta, str) else ""

    return {
        "headline": headline,
        "instagram": instagram,
        "x": {"post": post},
        "tiktok": {"scenes": scenes, "cta": tiktok_cta},
    }


def _fallback_template_conteudo(assunto):
    """Fallback simples por template - usado quando a chamada a IA
    falha (ex: limite diario da Groq atingido). Garante que o Social
    Content Engine NUNCA deixe de gerar conteudo por indisponibilidade
    de IA - o item continua sendo criado, enfileirado e disponivel
    para aprovacao, so com texto mais simples (direto do assunto ja
    identificado pela logica pura, sem parafraseie de IA)."""
    titulo = assunto["titulo"]
    contexto = assunto.get("contexto", titulo)
    return {
        "headline": titulo,
        "instagram": {
            "hook": titulo,
            "context": contexto,
            "why_it_matters": "",
            "impact": "",
            "watch_next": "",
            "cta": "Acompanhe o mercado no Antes do Sino.",
        },
        "x": {"post": titulo[:280]},
        "tiktok": {"scenes": [], "cta": ""},
    }


def gerar_conteudo_unificado(assunto, entries_today, content_mode):
    """Chamada UNICA a IA - gera headline + instagram + x + tiktok
    juntos, sempre a partir da mesma ideia central. Se a IA falhar
    (ex: rate limit diario da Groq), cai no fallback por template em
    vez de descartar o conteudo - nunca deixa de gerar por
    indisponibilidade de IA."""
    if not USE_AI:
        return _fallback_template_conteudo(assunto)
    try:
        prompt = montar_prompt_unificado(assunto, entries_today, content_mode)
        raw_response = ask_groq_isolado(prompt, purpose="generation")
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_unificado(parsed)
        if conteudo is None:
            print("Geracao unificada retornou JSON invalido - usando fallback por template.")
            return _fallback_template_conteudo(assunto)
        return conteudo
    except Exception as e:
        print("Erro na geracao unificada de conteudo (usando fallback por template): " + str(e))
        return _fallback_template_conteudo(assunto)


def gerar_conteudo_midday_unificado(market_snapshot):
    """Mesma FORMA de saida (headline/instagram/x/tiktok), mas por
    template deterministico - sem IA, sem risco de invencao de numero.
    Midday segue a MESMA maquina de estados dos outros modos, so muda
    COMO o conteudo e produzido."""
    linhas = []
    quotes_by_symbol = (market_snapshot or {}).get("quotes_by_symbol", {}) or {}
    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa and ibovespa.get("change") is not None:
        linhas.append("Ibovespa " + _formata_variacao(ibovespa["change"]))
    sp500 = (market_snapshot or {}).get("sp500")
    if sp500 and sp500.get("change") is not None:
        linhas.append("S&P 500 " + _formata_variacao(sp500["change"]))
    usd = (market_snapshot or {}).get("usd")
    if usd and usd.get("change") is not None:
        linhas.append("Dólar " + _formata_variacao(usd["change"]))
    wti = (market_snapshot or {}).get("wti")
    if wti and wti.get("change") is not None:
        linhas.append("Petróleo (WTI) " + _formata_variacao(wti["change"]))
    bitcoin = (market_snapshot or {}).get("bitcoin")
    if bitcoin and bitcoin.get("change") is not None:
        linhas.append("Bitcoin " + _formata_variacao(bitcoin["change"]))
    selic = (market_snapshot or {}).get("selic")
    if selic is not None:
        linhas.append("CDI " + str(selic) + "% a.a.")

    if not linhas:
        return None

    resumo = " | ".join(linhas)
    headline = "Mercado ao meio-dia: " + resumo

    return {
        "headline": headline,
        "instagram": {
            "hook": headline,
            "context": resumo,
            "why_it_matters": "",
            "impact": "",
            "watch_next": "",
            "cta": "Acompanhe o mercado em tempo real no Antes do Sino.",
        },
        "x": {"post": headline[:280]},
        "tiktok": {"scenes": [], "cta": ""},
    }


# ---------------------------------------------------------------------------
# Escolha de assunto - logica pura, sem IA (Opening e Closing usam a
# mesma; Breaking tem a sua propria com score)
# ---------------------------------------------------------------------------

def escolher_assunto_principal(clusters, market_insights, market_snapshot, events):
    """Ordem de prioridade:
    1. Mudanca de atencao (market_intelligence)
    2. Movimento relevante de mercado
    3. Cluster de noticias mais relevante
    4. Evento importante proximo
    Retorna (assunto, reason:list[str]) ou (None, [])."""
    home_insights = (market_insights or {}).get("home", [])
    for frase in home_insights:
        if any(marcador in frase for marcador in MARCADORES_MUDANCA_ATENCAO):
            return {"titulo": frase, "contexto": frase}, ["Mudança de atenção identificada pelo market intelligence"]

    movimentos = _coletar_movimentos_mercado(market_snapshot)
    if movimentos:
        movimentos.sort(key=lambda par: abs(par[1]), reverse=True)
        nome, variacao = movimentos[0]
        if abs(variacao) >= LIMIAR_MOVIMENTO_FORTE:
            titulo = nome + " " + _formata_variacao(variacao)
            contexto = nome + " teve variação de " + _formata_variacao(variacao) + " no dia."
            return {"titulo": titulo, "contexto": contexto}, [nome + " com movimento relevante (" + _formata_variacao(variacao) + ")"]

    if clusters:
        top = clusters[0]
        rep = top.get("representative", {})
        titulo = rep.get("title", "")
        if titulo:
            corpo = rep.get("body", "")
            contexto = titulo + (". " + corpo if corpo else "")
            return {"titulo": titulo, "contexto": contexto}, ["Cluster de notícia mais relevante: " + titulo]

    if events:
        hoje = datetime.now(BR_TZ).date()
        candidatos_eventos = []
        for ev in events:
            try:
                data_evento = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            dias_ate = (data_evento - hoje).days
            if dias_ate >= 0:
                candidatos_eventos.append((dias_ate, ev))
        if candidatos_eventos:
            candidatos_eventos.sort(key=lambda par: par[0])
            _, evento_escolhido = candidatos_eventos[0]
            titulo = evento_escolhido.get("label", "")
            contexto = titulo + (". " + evento_escolhido["why"] if evento_escolhido.get("why") else "")
            return {"titulo": titulo, "contexto": contexto}, ["Evento próximo: " + titulo]

    return None, []


# ---------------------------------------------------------------------------
# MODO: BREAKING - score + segunda validacao por IA
# ---------------------------------------------------------------------------

def calcular_score_relevancia(clusters, market_snapshot, events):
    """Score 100% deterministico (sem IA) de 0 a 12. Avalia impacto
    financeiro E potencial de conteudo. Retorna (score, motivos:list, assunto)."""
    score = 0
    motivos = []

    top_cluster = clusters[0] if clusters else None
    texto_cluster = ""
    if top_cluster:
        rep = top_cluster.get("representative", {})
        texto_cluster = (rep.get("title", "") + " " + rep.get("body", "")).lower()

    if texto_cluster and any(ent in texto_cluster for ent in ENTIDADES_ALTO_IMPACTO):
        score += 3
        motivos.append("Menciona ativo/tema de alto impacto")

    movimentos = _coletar_movimentos_mercado(market_snapshot)
    maior_movimento = None
    if movimentos:
        movimentos.sort(key=lambda par: abs(par[1]), reverse=True)
        maior_movimento = movimentos[0]
        if abs(maior_movimento[1]) >= LIMIAR_MOVIMENTO_FORTE:
            score += 3
            motivos.append(maior_movimento[0] + " com movimento forte (" + _formata_variacao(maior_movimento[1]) + ")")

    if top_cluster and top_cluster.get("distinct_sources", 0) >= 2:
        score += 2
        motivos.append("Coberto por " + str(top_cluster["distinct_sources"]) + " fontes distintas")

    if texto_cluster and any(m in texto_cluster for m in MARCADORES_POTENCIAL_EDUCACIONAL):
        score += 2
        motivos.append("Tema com potencial explicativo/educacional")

    evento_macro = _evento_macro_e_hoje(events)
    if evento_macro:
        score += 2
        motivos.append("Evento macro hoje: " + evento_macro.get("label", ""))

    assunto = None
    if top_cluster and score > 0:
        rep = top_cluster.get("representative", {})
        titulo = rep.get("title", "")
        if titulo:
            corpo = rep.get("body", "")
            assunto = {"titulo": titulo, "contexto": titulo + (". " + corpo if corpo else "")}
    if assunto is None and evento_macro:
        assunto = {
            "titulo": evento_macro.get("label", ""),
            "contexto": evento_macro.get("label", "") + (". " + evento_macro["why"] if evento_macro.get("why") else ""),
        }
    if assunto is None and maior_movimento and abs(maior_movimento[1]) >= LIMIAR_MOVIMENTO_FORTE:
        nome, variacao = maior_movimento
        assunto = {
            "titulo": nome + " " + _formata_variacao(variacao),
            "contexto": nome + " teve variação de " + _formata_variacao(variacao) + " no dia.",
        }

    return score, motivos, assunto


def validar_potencial_conteudo_ia(assunto, motivos):
    """Segunda camada de validacao do Breaking - so roda quando o
    score ja passou do limiar. Pergunta pra IA se o assunto realmente
    vale virar post (nao so 'e relevante pro mercado'). Fallback
    seguro: em caso de falha da IA, permite a geracao (nao trava o
    fluxo por indisponibilidade da IA)."""
    if not USE_AI:
        return True
    try:
        prompt = (
            "Voce e o editor de conteudo do canal 'Antes do Sino'. Avalie se o "
            "assunto abaixo tem potencial real para virar um post educativo e "
            "relevante para redes sociais - considere potencial educativo, "
            "curiosidade, impacto para investidores, e capacidade de gerar "
            "engajamento. Nao avalie so se e relevante para o mercado - avalie se "
            "vale a pena virar CONTEUDO.\n\n"
            "ASSUNTO: " + assunto["titulo"] + "\n"
            "CONTEXTO: " + assunto["contexto"] + "\n"
            "SINAIS QUE LEVARAM A ESSA AVALIACAO: " + "; ".join(motivos) + "\n\n"
            "Responda APENAS 'true' ou 'false', sem explicacao."
        )
        raw_response = ask_groq_isolado(prompt, purpose="analysis").strip().lower()
        return "false" not in raw_response
    except Exception as e:
        print("Erro na validacao de potencial de conteudo (fallback seguro=permite): " + str(e))
        return True


def _limpar_estado_breaking_se_novo_dia(state):
    hoje = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    if state.get("date") != hoje:
        return {"date": hoje, "count_today": 0, "last_breaking_at": "", "topicos_publicados_hoje": []}
    return state


def _assunto_ja_publicado_hoje(assunto, topicos_publicados_hoje):
    titulo_normalizado = assunto["titulo"].strip().lower()
    for topico_anterior in topicos_publicados_hoje:
        anterior_normalizado = topico_anterior.strip().lower()
        palavras_comuns = set(titulo_normalizado.split()) & set(anterior_normalizado.split())
        if len(palavras_comuns) >= 2:
            return True
    return False


def should_generate_breaking_content(score, assunto, breaking_state):
    if score < LIMIAR_BREAKING or assunto is None:
        return False, "Score abaixo do limiar (" + str(score) + "/" + str(LIMIAR_BREAKING) + ")"
    if breaking_state.get("count_today", 0) >= MAX_BREAKING_POR_DIA:
        return False, "Teto diário de " + str(MAX_BREAKING_POR_DIA) + " posts Breaking já atingido"
    last_at = breaking_state.get("last_breaking_at", "")
    if last_at:
        try:
            ultimo = datetime.strptime(last_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BR_TZ)
            minutos_desde_ultimo = (datetime.now(BR_TZ) - ultimo).total_seconds() / 60
            if minutos_desde_ultimo < INTERVALO_MINIMO_BREAKING_MINUTOS:
                return False, "Intervalo mínimo entre posts Breaking ainda não passou"
        except Exception:
            pass
    if _assunto_ja_publicado_hoje(assunto, breaking_state.get("topicos_publicados_hoje", [])):
        return False, "Assunto muito parecido com um já publicado hoje"
    return True, "Score " + str(score) + " atingiu o limiar, com assunto novo"


def avaliar_breaking_content(entries_today, clusters, market_snapshot, events):
    score, motivos, assunto = calcular_score_relevancia(clusters, market_snapshot, events)
    breaking_state = _limpar_estado_breaking_se_novo_dia(load_breaking_state())

    deve_gerar, motivo_decisao = should_generate_breaking_content(score, assunto, breaking_state)
    if not deve_gerar:
        return None

    if not validar_potencial_conteudo_ia(assunto, motivos):
        print("Social Content Engine (Breaking): IA avaliou que o assunto não vale virar post - descartado mesmo com score " + str(score) + ".")
        return None

    conteudo = gerar_conteudo_unificado(assunto, entries_today, "breaking")
    if conteudo is None:
        print("Social Content Engine (Breaking): geração de conteúdo falhou - nada gerado.")
        return None

    item = _montar_item(conteudo, "breaking", score, motivos)

    breaking_state["count_today"] = breaking_state.get("count_today", 0) + 1
    breaking_state["last_breaking_at"] = datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S")
    topicos = breaking_state.get("topicos_publicados_hoje", [])
    topicos.append(assunto["titulo"])
    breaking_state["topicos_publicados_hoje"] = topicos
    save_breaking_state(breaking_state)

    return item


# ---------------------------------------------------------------------------
# MODO: OPENING (09h00-09h30)
# ---------------------------------------------------------------------------

def should_generate_opening_content():
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_opening_state()
    if state.get("last_opening_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return OPENING_JANELA_INICIO_MINUTOS <= minutes <= OPENING_JANELA_FIM_MINUTOS


def avaliar_opening_content(entries_today, clusters, market_insights, market_snapshot, events):
    if not should_generate_opening_content():
        return None

    assunto, reason = escolher_assunto_principal(clusters, market_insights, market_snapshot, events)
    if assunto is None:
        print("Social Content Engine (Opening): nenhum assunto disponível hoje - nada gerado.")
        return None

    conteudo = gerar_conteudo_unificado(assunto, entries_today, "opening")
    if conteudo is None:
        print("Social Content Engine (Opening): geração de conteúdo falhou - nada gerado.")
        return None

    item = _montar_item(conteudo, "opening", None, reason)

    state = load_opening_state()
    state["last_opening_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_opening_state(state)

    return item


# ---------------------------------------------------------------------------
# MODO: MIDDAY (12h00-12h15) - mesma maquina de estados, sem IA
# ---------------------------------------------------------------------------

def should_generate_midday_content():
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_midday_state()
    if state.get("last_midday_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return MIDDAY_JANELA_INICIO_MINUTOS <= minutes <= MIDDAY_JANELA_FIM_MINUTOS


def avaliar_midday_snapshot(market_snapshot):
    if not should_generate_midday_content():
        return None

    conteudo = gerar_conteudo_midday_unificado(market_snapshot)
    if conteudo is None:
        print("Social Content Engine (Midday): sem dados de mercado disponíveis - nada gerado.")
        return None

    item = _montar_item(conteudo, "midday", None, ["Snapshot de meio de pregão programado (12h00)"])
    item["prompt_version"] = "midday-template-" + PROMPT_VERSION

    state = load_midday_state()
    state["last_midday_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_midday_state(state)

    return item


# ---------------------------------------------------------------------------
# MODO: CLOSING (18h30-19h00)
# ---------------------------------------------------------------------------

def should_generate_closing_content():
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_social_content_state()
    if state.get("last_social_content_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return CLOSING_JANELA_INICIO_MINUTOS <= minutes <= CLOSING_JANELA_FIM_MINUTOS


def avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events):
    if not should_generate_closing_content():
        return None

    assunto, reason = escolher_assunto_principal(clusters, market_insights, market_snapshot, events)
    if assunto is None:
        print("Social Content Engine (Closing): nenhum assunto disponível hoje - nada gerado.")
        return None

    conteudo = gerar_conteudo_unificado(assunto, entries_today, "closing")
    if conteudo is None:
        print("Social Content Engine (Closing): geração de conteúdo falhou - nada gerado.")
        return None

    item = _montar_item(conteudo, "closing", None, reason)

    state = load_social_content_state()
    state["last_social_content_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_social_content_state(state)

    return item


# ---------------------------------------------------------------------------
# Montagem do item - centraliza os campos comuns a QUALQUER modo
# ---------------------------------------------------------------------------

def _montar_item(conteudo, content_mode, score, reason):
    return {
        "id": gerar_id_unico(),
        "content_mode": content_mode,
        "content_template": TEMPLATE_MAP.get(content_mode, "quick_insight"),
        "headline": conteudo["headline"],
        "instagram": conteudo["instagram"],
        "x": conteudo["x"],
        "tiktok": conteudo["tiktok"],
        "score": score,
        "reason": reason,
        "priority": _prioridade_por_modo(content_mode),
        "expires_at": _calcular_expiracao(content_mode).strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_version": PROMPT_VERSION,
        "status": "draft",
        "expired_notice_sent": False,
    }


# ---------------------------------------------------------------------------
# Persistencia - fila acumulativa, nunca sobrescreve
# ---------------------------------------------------------------------------

def load_social_queue():
    data = _load_json_seguro(SOCIAL_QUEUE_FILE, [])
    return data if isinstance(data, list) else []


def save_social_queue_full(fila):
    _save_json(SOCIAL_QUEUE_FILE, fila)


def _find_item_index_by_id(fila, item_id):
    for i, item in enumerate(fila):
        if item.get("id") == item_id:
            return i
    return None


def enfileirar_item(item):
    """Acumula historico - nunca sobrescreve. Adiciona date/metrics e
    envia a notificacao de draft."""
    if item is None:
        return

    fila = load_social_queue()

    novo_item = dict(item)
    novo_item["date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    novo_item["metrics"] = {"views": None, "likes": None, "shares": None, "comments": None}

    fila.append(novo_item)
    save_social_queue_full(fila)

    print(
        "Social Content Engine: item " + novo_item["id"] + " criado (modo=" + novo_item["content_mode"]
        + ", status=draft, template=" + novo_item["content_template"] + ")"
    )

    notificar_draft(novo_item)


# ---------------------------------------------------------------------------
# Notificacao privada de draft - com ID e instrucao de resposta
# ---------------------------------------------------------------------------

def _enviar_telegram_admin(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Content Engine: TELEGRAM_ADMIN_CHAT_ID não configurado - aviso privado não enviado.")
        return
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificação privada (isolado, item já está salvo): " + str(e))


def notificar_draft(item):
    modo_label = {"opening": "Opening", "breaking": "Breaking", "midday": "Midday", "closing": "Closing"}.get(item["content_mode"], item["content_mode"])

    preview = item["headline"]
    if item.get("instagram", {}).get("hook"):
        preview += "\n" + item["instagram"]["hook"]

    texto = (
        "🆕 <b>Novo conteúdo (draft)</b>\n\n"
        "Modo: " + modo_label + "\n"
        "Assunto: " + item["headline"] + "\n"
    )
    if item.get("score") is not None:
        texto += "Score: " + str(item["score"]) + "\n"
    if item.get("reason"):
        texto += "Motivo: " + "; ".join(item["reason"]) + "\n"
    texto += (
        "\nPrévia:\n" + preview
        + "\n\nID: <code>" + item["id"] + "</code>"
        + "\n\nResponda:\nAprovar " + item["id"] + "\nou\nRejeitar " + item["id"]
    )
    _enviar_telegram_admin(texto)


def notificar_expirado(item):
    texto = (
        "⚠️ <b>Esse conteúdo perdeu o timing</b>\n\n"
        "Modo: " + item["content_mode"] + "\n"
        "Assunto: " + item["headline"] + "\n"
        "ID: <code>" + item["id"] + "</code>\n\n"
        "Ainda está como draft e já passou da validade esperada para esse tipo de conteúdo."
    )
    _enviar_telegram_admin(texto)


# ---------------------------------------------------------------------------
# Aprovacao por resposta de texto - consulta getUpdates, sem botao
# ---------------------------------------------------------------------------

def checar_aprovacoes_pendentes():
    """Roda TODO ciclo. Le mensagens novas do Telegram (so as vindas do
    chat privado do admin), procura 'Aprovar <ID>' / 'Rejeitar <ID>',
    atualiza o status do item correspondente (so se ainda estiver
    'draft' - nunca reverte um item ja aprovado/rejeitado/desenhado).
    Tambem avisa (uma unica vez) sobre itens draft que expiraram."""
    if not TELEGRAM_BOT_TOKEN:
        return

    offset_state = load_telegram_offset()
    offset = offset_state.get("offset", 0)

    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/getUpdates"
        params = {"offset": offset, "timeout": 0}
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        updates = data.get("result", []) if data.get("ok") else []
    except Exception as e:
        print("Erro ao consultar getUpdates (isolado): " + str(e))
        updates = []

    fila = load_social_queue()
    fila_alterada = False
    maior_update_id = offset - 1

    for update in updates:
        update_id = update.get("update_id", 0)
        if update_id > maior_update_id:
            maior_update_id = update_id

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        texto = message.get("text", "") or ""

        if TELEGRAM_ADMIN_CHAT_ID and chat_id != str(TELEGRAM_ADMIN_CHAT_ID):
            continue

        match = re.match(r"(?i)^\s*(aprovar|rejeitar)\s+(\S+)\s*$", texto)
        if not match:
            continue

        acao = match.group(1).lower()
        item_id = match.group(2).strip()

        indice = _find_item_index_by_id(fila, item_id)
        if indice is None:
            continue

        item = fila[indice]
        if item.get("status") != "draft":
            continue

        novo_status = "approved" if acao == "aprovar" else "rejected"
        fila[indice]["status"] = novo_status
        fila_alterada = True
        print("Social Content Engine: item " + item_id + " marcado como " + novo_status + " via Telegram.")

    # Avisa (uma vez) sobre itens draft expirados
    agora = datetime.now(BR_TZ)
    for item in fila:
        if item.get("status") != "draft" or item.get("expired_notice_sent"):
            continue
        try:
            expira_em = datetime.strptime(item["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BR_TZ)
        except Exception:
            continue
        if agora > expira_em:
            notificar_expirado(item)
            item["expired_notice_sent"] = True
            fila_alterada = True

    if fila_alterada:
        save_social_queue_full(fila)

    if maior_update_id >= offset:
        save_telegram_offset({"offset": maior_update_id + 1})


# ---------------------------------------------------------------------------
# Ponto de entrada unico - e a UNICA funcao que o main.py precisa
# chamar para GERACAO (aprovacao e chamada separadamente, antes)
# ---------------------------------------------------------------------------

def run_social_content_engine(entries_today, clusters, market_insights, market_snapshot, events):
    """Roda TODO ciclo do bot. Avalia os 4 modos - na grande maioria
    dos ciclos, nenhum gera nada (comportamento esperado)."""
    for item in [
        avaliar_opening_content(entries_today, clusters, market_insights, market_snapshot, events),
        avaliar_breaking_content(entries_today, clusters, market_snapshot, events),
        avaliar_midday_snapshot(market_snapshot),
        avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events),
    ]:
        if item:
            enfileirar_item(item)
