"""
Social Content Engine - Antes do Sino
========================================

Modulo TOTALMENTE ISOLADO do main.py. Nao importa nenhuma funcao
interna do bot principal - recebe tudo pronto por parametro (dados ja
calculados pelo main() em cada execucao) e faz sua propria chamada a
IA, com sua propria constante de timezone e seu proprio arquivo de
estado.

Gera automaticamente conteudo para Instagram, TikTok/Reels e X a
partir dos mesmos dados que o bot ja possui - nunca inventa fato,
numero ou informacao que nao esteja no input recebido.

Tres modos, cada um com seu proprio gatilho, rodando dentro do MESMO
ciclo de 5 minutos do bot (o main.py chama run_social_content_engine
todo ciclo - a decisao de "e a hora/e relevante o suficiente" fica
isolada aqui dentro):

  1. Breaking  - avaliado TODO ciclo, so dispara quando o score de
                 relevancia (logica pura, sem IA) ultrapassa o limiar.
                 Prioridade X/Twitter, angulo explicativo, nao manchete.
  2. Midday    - janela 12h00-12h15, 1x/dia, fotografia do mercado.
  3. Closing   - janela 18h30-19h00, 1x/dia, analise completa do dia
                 (Instagram + TikTok + X).

O conteudo gerado e so ENFILEIRADO em docs/social_queue.json, com
status "pending" - nada e publicado automaticamente ainda.
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone

import requests

BR_TZ = timezone(timedelta(hours=-3))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_AI = bool(GROQ_API_KEY)

# Notificacao PRIVADA de novo conteudo gerado - reaproveita o MESMO bot
# (mesmo token) ja usado pelo resto do projeto, mas envia para um chat
# PRIVADO distinto do canal publico pago (TELEGRAM_CHAT_ID). Sem essa
# separacao, um aviso de "conteudo ainda nao revisado" vazaria rascunho
# interno para os assinantes.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

SOCIAL_QUEUE_FILE = "docs/social_queue.json"
BREAKING_STATE_FILE = "docs/social_breaking_state.json"
MIDDAY_STATE_FILE = "docs/social_midday_state.json"
CLOSING_STATE_FILE = "docs/social_content_state.json"

# ---------------------------------------------------------------------------
# Parametros de frequencia/selecao - ponto de partida, calibravel depois
# de observar comportamento real (nao sao numeros definitivos).
# ---------------------------------------------------------------------------

LIMIAR_BREAKING = 6
INTERVALO_MINIMO_BREAKING_MINUTOS = 60
MAX_BREAKING_POR_DIA = 3

LIMIAR_MOVIMENTO_FORTE = 2.0  # % - usado no criterio B do score de Breaking

MIDDAY_JANELA_INICIO_MINUTOS = 12 * 60
MIDDAY_JANELA_FIM_MINUTOS = 12 * 60 + 15

CLOSING_JANELA_INICIO_MINUTOS = 18 * 60 + 30
CLOSING_JANELA_FIM_MINUTOS = 19 * 60

# Entidades/temas de alto impacto - criterio A do score de Breaking.
ENTIDADES_ALTO_IMPACTO = [
    "petrobras", "vale", "itau", "itaú", "bradesco", "banco do brasil",
    "santander", "dolar", "dólar", "juros", "selic", "copom", "fed",
    "fomc", "powell", "campos neto",
]

# Marcadores de potencial explicativo/educacional - criterio D do score
# de Breaking. Heuristica de palavra-chave (sem IA) - propositalmente
# simples: serve so para PONTUAR o potencial, a IA depois e quem
# escreve o angulo explicativo de verdade no texto final.
MARCADORES_POTENCIAL_EDUCACIONAL = [
    "porque", "por que", "entenda", "impacto", "explica", "resultado de",
    "por tras", "consequencia", "o que muda", "reflete", "sinaliza",
]

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
        json.dump(dado, f, ensure_ascii=False)


def load_breaking_state():
    return _load_json_seguro(BREAKING_STATE_FILE, {
        "date": "", "count_today": 0, "last_breaking_at": "", "topicos_publicados_hoje": [],
    })


def save_breaking_state(state):
    _save_json(BREAKING_STATE_FILE, state)


def load_midday_state():
    return _load_json_seguro(MIDDAY_STATE_FILE, {"last_midday_date": ""})


def save_midday_state(state):
    _save_json(MIDDAY_STATE_FILE, state)


def load_social_content_state():
    return _load_json_seguro(CLOSING_STATE_FILE, {"last_social_content_date": ""})


def save_social_content_state(state):
    _save_json(CLOSING_STATE_FILE, state)


# ---------------------------------------------------------------------------
# IA isolada - mesma chave, zero import de main.py
# ---------------------------------------------------------------------------

def ask_groq_isolado(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()
    if "choices" not in data:
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
    """Lista (nome, variacao) de tudo que tiver 'change' disponivel no
    snapshot - usada tanto no score de Breaking quanto na escolha de
    assunto do Closing."""
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


# ---------------------------------------------------------------------------
# MODO 1: BREAKING - avaliado todo ciclo, so dispara acima do limiar
# ---------------------------------------------------------------------------

def calcular_score_relevancia(clusters, market_snapshot, events):
    """Score 100% deterministico (sem IA) de 0 a 10, com os motivos
    que justificaram cada ponto. Avalia impacto financeiro E potencial
    de conteudo, como pedido - nao so tamanho do movimento de preco.

    Retorna (score:int, motivos:list[str], assunto:dict|None)."""
    score = 0
    motivos = []

    top_cluster = clusters[0] if clusters else None
    texto_cluster = ""
    if top_cluster:
        rep = top_cluster.get("representative", {})
        texto_cluster = (rep.get("title", "") + " " + rep.get("body", "")).lower()

    # Criterio A (+3): noticia com impacto direto em ativo/tema de alto impacto
    if texto_cluster and any(ent in texto_cluster for ent in ENTIDADES_ALTO_IMPACTO):
        score += 3
        motivos.append("menciona ativo/tema de alto impacto (ex: Petrobras, Vale, juros, Fed)")

    # Criterio B (+3): movimento forte de mercado/ativo
    movimentos = _coletar_movimentos_mercado(market_snapshot)
    maior_movimento = None
    if movimentos:
        movimentos.sort(key=lambda par: abs(par[1]), reverse=True)
        maior_movimento = movimentos[0]
        if abs(maior_movimento[1]) >= LIMIAR_MOVIMENTO_FORTE:
            score += 3
            motivos.append(
                maior_movimento[0] + " com movimento forte (" + _formata_variacao(maior_movimento[1]) + ")"
            )

    # Criterio C (+2): cluster com multiplas fontes ou grande repercussao
    if top_cluster and top_cluster.get("distinct_sources", 0) >= 2:
        score += 2
        motivos.append(
            "coberto por " + str(top_cluster["distinct_sources"]) + " fontes distintas"
        )

    # Criterio D (+2): potencial educacional/explicativo (heuristica de
    # palavra-chave - a IA e quem escreve o angulo de verdade depois,
    # isso aqui so pontua o POTENCIAL, sem gastar chamada de IA)
    if texto_cluster and any(m in texto_cluster for m in MARCADORES_POTENCIAL_EDUCACIONAL):
        score += 2
        motivos.append("tema com potencial explicativo/educacional")

    # Assunto candidato: prioriza o cluster (mais rico em conteudo); se
    # nada de cluster relevante mas o movimento de mercado foi o que
    # pontuou, usa o movimento como assunto.
    assunto = None
    if top_cluster and (score > 0):
        rep = top_cluster.get("representative", {})
        titulo = rep.get("title", "")
        if titulo:
            corpo = rep.get("body", "")
            assunto = {
                "titulo": titulo,
                "contexto": titulo + (". " + corpo if corpo else ""),
            }
    if assunto is None and maior_movimento and abs(maior_movimento[1]) >= LIMIAR_MOVIMENTO_FORTE:
        nome, variacao = maior_movimento
        assunto = {
            "titulo": nome + " " + _formata_variacao(variacao),
            "contexto": nome + " teve variação de " + _formata_variacao(variacao) + " no dia.",
        }

    return score, motivos, assunto


def _limpar_estado_breaking_se_novo_dia(state):
    hoje = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    if state.get("date") != hoje:
        return {"date": hoje, "count_today": 0, "last_breaking_at": "", "topicos_publicados_hoje": []}
    return state


def _assunto_ja_publicado_hoje(assunto, topicos_publicados_hoje):
    """Deduplicacao simples por similaridade de texto - evita repetir
    o mesmo assunto (ex: Ibovespa caindo por horas seguidas) varias
    vezes no mesmo dia."""
    titulo_normalizado = assunto["titulo"].strip().lower()
    for topico_anterior in topicos_publicados_hoje:
        anterior_normalizado = topico_anterior.strip().lower()
        palavras_comuns = set(titulo_normalizado.split()) & set(anterior_normalizado.split())
        if len(palavras_comuns) >= 2:
            return True
    return False


def should_generate_breaking_content(score, assunto, breaking_state):
    if score < LIMIAR_BREAKING or assunto is None:
        return False, "score abaixo do limiar (" + str(score) + "/" + str(LIMIAR_BREAKING) + ")"

    if breaking_state.get("count_today", 0) >= MAX_BREAKING_POR_DIA:
        return False, "teto diario de " + str(MAX_BREAKING_POR_DIA) + " posts Breaking ja atingido"

    last_at = breaking_state.get("last_breaking_at", "")
    if last_at:
        try:
            ultimo = datetime.strptime(last_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BR_TZ)
            minutos_desde_ultimo = (datetime.now(BR_TZ) - ultimo).total_seconds() / 60
            if minutos_desde_ultimo < INTERVALO_MINIMO_BREAKING_MINUTOS:
                return False, "intervalo minimo entre posts Breaking ainda nao passou"
        except Exception:
            pass

    if _assunto_ja_publicado_hoje(assunto, breaking_state.get("topicos_publicados_hoje", [])):
        return False, "assunto muito parecido com um ja publicado hoje"

    return True, "score " + str(score) + " atingiu o limiar, com assunto novo"


def gerar_post_breaking(assunto, motivos):
    """Chamada UNICA a IA para o conteudo Breaking - prioridade X,
    texto curto, com angulo explicativo (nunca so a manchete)."""
    instrucao = (
        "Voce e o redator do canal 'Antes do Sino', especializado em contexto de "
        "mercado financeiro. Use SOMENTE os fatos abaixo - nunca invente dado, numero "
        "ou informacao que nao esteja aqui. Nunca de opiniao de investimento. Escreva "
        "com angulo EXPLICATIVO, nunca so a manchete pura.\n\n"
        "Exemplo do que EVITAR (manchete pura, sem angulo):\n"
        "\"Petrobras cai 5% nesta quarta-feira.\"\n\n"
        "Exemplo do que fazer (angulo explicativo):\n"
        "\"Petrobras cai 5% e pressiona o Ibovespa. Mas o movimento reflete uma mudanca "
        "na expectativa dos investidores sobre...\"\n\n"
        "ASSUNTO:\n" + assunto["titulo"] + "\n\n"
        "CONTEXTO DISPONIVEL:\n" + assunto["contexto"] + "\n\n"
        "Gere um post para X/Twitter, MAXIMO 280 caracteres, com angulo explicativo, "
        "sem soar como propaganda.\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"x_post": "..."}'
    )
    raw_response = ask_groq_isolado(instrucao)
    parsed = extract_json_object_isolado(raw_response)
    if not isinstance(parsed, dict):
        return None
    x_post = parsed.get("x_post", "")
    if not isinstance(x_post, str) or not x_post.strip():
        return None
    return {"x_post": x_post.strip()[:280]}


def avaliar_breaking_content(clusters, market_snapshot, events):
    """Roda TODO ciclo. So gera conteudo quando o score ultrapassa o
    limiar E passa nas travas de frequencia/dedup. Retorna o item pra
    fila, ou None na grande maioria dos ciclos."""
    score, motivos, assunto = calcular_score_relevancia(clusters, market_snapshot, events)

    breaking_state = _limpar_estado_breaking_se_novo_dia(load_breaking_state())

    deve_gerar, motivo_decisao = should_generate_breaking_content(score, assunto, breaking_state)
    if not deve_gerar:
        return None

    if not USE_AI:
        print("Social Content Engine (Breaking): GROQ_API_KEY nao configurada - nada gerado.")
        return None

    try:
        conteudo_ia = gerar_post_breaking(assunto, motivos)
        if conteudo_ia is None:
            print("Social Content Engine (Breaking): resposta da IA invalida - nada gerado.")
            return None

        reason = "; ".join(motivos) if motivos else motivo_decisao

        item = {
            "content_mode": "breaking",
            "score": score,
            "reason": reason,
            "topic": assunto["titulo"],
            "x_post": conteudo_ia["x_post"],
        }

        breaking_state["count_today"] = breaking_state.get("count_today", 0) + 1
        breaking_state["last_breaking_at"] = datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S")
        topicos = breaking_state.get("topicos_publicados_hoje", [])
        topicos.append(assunto["titulo"])
        breaking_state["topicos_publicados_hoje"] = topicos
        save_breaking_state(breaking_state)

        return item
    except Exception as e:
        print("Erro no Social Content Engine (Breaking, isolado): " + str(e))
        return None


# ---------------------------------------------------------------------------
# MODO 2: MIDDAY - janela 12h00-12h15, 1x/dia, sem chamada de IA
# (numeros diretos do snapshot - menor risco, menor custo)
# ---------------------------------------------------------------------------

def should_generate_midday_content():
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_midday_state()
    if state.get("last_midday_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return MIDDAY_JANELA_INICIO_MINUTOS <= minutes <= MIDDAY_JANELA_FIM_MINUTOS


def gerar_conteudo_midday(market_snapshot):
    """Sem chamada de IA - texto simples e direto a partir dos numeros
    reais do snapshot. Omite qualquer dado ausente, nunca inventa."""
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

    x_post = "Mercado ao meio-dia: " + " | ".join(linhas)
    return {"x_post": x_post[:280]}


def avaliar_midday_snapshot(market_snapshot):
    if not should_generate_midday_content():
        return None

    conteudo = gerar_conteudo_midday(market_snapshot)
    if conteudo is None:
        print("Social Content Engine (Midday): sem dados de mercado disponiveis - nada gerado.")
        return None

    item = {
        "content_mode": "midday",
        "score": None,
        "reason": "Snapshot de meio de pregão programado (12h00)",
        "topic": "Snapshot de mercado - meio-dia",
        "x_post": conteudo["x_post"],
    }

    state = load_midday_state()
    state["last_midday_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_midday_state(state)

    return item


# ---------------------------------------------------------------------------
# MODO 3: CLOSING - janela 18h30-19h00, 1x/dia, conteudo completo
# (Instagram + TikTok + X) - mesma logica que ja existia
# ---------------------------------------------------------------------------

def should_generate_closing_content():
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_social_content_state()
    if state.get("last_social_content_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return CLOSING_JANELA_INICIO_MINUTOS <= minutes <= CLOSING_JANELA_FIM_MINUTOS


def escolher_assunto_principal(clusters, market_insights, market_snapshot, events):
    """Escolha do assunto do Closing - ordem de prioridade:
    1. Mudanca de atencao (market_intelligence)
    2. Movimento relevante de mercado
    3. Cluster de noticias mais relevante
    4. Evento importante proximo
    100% logica pura, sem IA."""
    home_insights = (market_insights or {}).get("home", [])
    for frase in home_insights:
        if any(marcador in frase for marcador in MARCADORES_MUDANCA_ATENCAO):
            return {"tipo": "mudanca_atencao", "titulo": frase, "contexto": frase}

    movimentos = _coletar_movimentos_mercado(market_snapshot)
    if movimentos:
        movimentos.sort(key=lambda par: abs(par[1]), reverse=True)
        nome, variacao = movimentos[0]
        if abs(variacao) >= LIMIAR_MOVIMENTO_FORTE:
            titulo = nome + " " + _formata_variacao(variacao)
            contexto = nome + " teve variação de " + _formata_variacao(variacao) + " no dia."
            return {"tipo": "movimento_mercado", "titulo": titulo, "contexto": contexto}

    if clusters:
        top = clusters[0]
        rep = top.get("representative", {})
        titulo = rep.get("title", "")
        if titulo:
            corpo = rep.get("body", "")
            contexto = titulo + (". " + corpo if corpo else "")
            return {"tipo": "cluster_noticia", "titulo": titulo, "contexto": contexto}

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
            return {"tipo": "evento_proximo", "titulo": titulo, "contexto": contexto}

    return None


def montar_prompt_closing(assunto, entries_today):
    manchetes_apoio = ""
    for e in (entries_today or [])[:8]:
        manchetes_apoio += "- " + e.get("title", "") + "\n"

    return (
        "Voce e o redator de conteudo do canal 'Antes do Sino', especializado em "
        "educacao financeira e contexto de mercado para redes sociais (Instagram, "
        "TikTok e X). Use SOMENTE os fatos e numeros fornecidos abaixo - nunca "
        "invente dado, numero ou informacao que nao esteja explicitamente aqui. "
        "Nunca de opiniao de investimento. Priorize educacao e contexto, nunca "
        "sensacionalismo. Este e o conteudo de FECHAMENTO do dia - foque em "
        "analise: principais movimentos do dia, o que explicou a bolsa, acoes/"
        "setores em destaque, e expectativa para o proximo pregao.\n\n"
        "ASSUNTO PRINCIPAL DE HOJE:\n" + assunto["titulo"] + "\n\n"
        "CONTEXTO DISPONIVEL:\n" + assunto["contexto"] + "\n\n"
        "MANCHETES DE APOIO DO DIA:\n" + manchetes_apoio + "\n\n"
        "Gere TRES conteudos, simultaneamente, mantendo o MESMO contexto editorial:\n\n"
        "1. INSTAGRAM (carrossel de exatamente 6 slides):\n"
        "   Slide 1: titulo com gancho forte\n"
        "   Slide 2: o que aconteceu\n"
        "   Slide 3: por que o mercado reagiu\n"
        "   Slide 4: quem e afetado\n"
        "   Slide 5: resumo final\n"
        "   Slide 6: CTA discreto para acompanhar o mercado no Antes do Sino\n\n"
        "2. TIKTOK/REELS (roteiro falado de ate 45 segundos):\n"
        "   gancho, explicacao, contexto, fechamento_cta\n\n"
        "3. X/TWITTER (post unico, MAXIMO 280 caracteres):\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"instagram_carousel": {"slide_1": "...", "slide_2": "...", "slide_3": "...", '
        '"slide_4": "...", "slide_5": "...", "slide_6": "..."}, '
        '"tiktok_script": {"gancho": "...", "explicacao": "...", "contexto": "...", '
        '"fechamento_cta": "..."}, '
        '"x_post": "..."}'
    )


def validar_conteudo_closing(parsed):
    if not isinstance(parsed, dict):
        return None

    ig = parsed.get("instagram_carousel", {})
    if not isinstance(ig, dict):
        ig = {}
    instagram_carousel = {}
    for i in range(1, 7):
        chave = "slide_" + str(i)
        valor = ig.get(chave, "")
        instagram_carousel[chave] = str(valor).strip() if isinstance(valor, str) else ""

    tk = parsed.get("tiktok_script", {})
    if not isinstance(tk, dict):
        tk = {}
    tiktok_script = {}
    for campo in ["gancho", "explicacao", "contexto", "fechamento_cta"]:
        valor = tk.get(campo, "")
        tiktok_script[campo] = str(valor).strip() if isinstance(valor, str) else ""

    x_post = parsed.get("x_post", "")
    x_post = str(x_post).strip()[:280] if isinstance(x_post, str) else ""

    return {
        "instagram_carousel": instagram_carousel,
        "tiktok_script": tiktok_script,
        "x_post": x_post,
    }


def avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events):
    if not should_generate_closing_content():
        return None

    assunto = escolher_assunto_principal(clusters, market_insights, market_snapshot, events)
    if assunto is None:
        print("Social Content Engine (Closing): nenhum assunto disponivel hoje - nada gerado.")
        return None

    if not USE_AI:
        print("Social Content Engine (Closing): GROQ_API_KEY nao configurada - nada gerado.")
        return None

    try:
        prompt = montar_prompt_closing(assunto, entries_today)
        raw_response = ask_groq_isolado(prompt)
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_closing(parsed)
        if conteudo is None:
            print("Social Content Engine (Closing): resposta da IA invalida - nada gerado.")
            return None

        item = {
            "content_mode": "closing",
            "score": None,
            "reason": "Fechamento diário programado (18h30-19h00) - assunto: " + assunto["tipo"],
            "topic": assunto["titulo"],
            "instagram_carousel": conteudo["instagram_carousel"],
            "tiktok_script": conteudo["tiktok_script"],
            "x_post": conteudo["x_post"],
        }

        state = load_social_content_state()
        state["last_social_content_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
        save_social_content_state(state)

        return item
    except Exception as e:
        print("Erro no Social Content Engine (Closing, isolado): " + str(e))
        return None


# ---------------------------------------------------------------------------
# Persistencia - fila acumulativa, nunca sobrescreve
# ---------------------------------------------------------------------------

def load_social_queue():
    data = _load_json_seguro(SOCIAL_QUEUE_FILE, [])
    return data if isinstance(data, list) else []


def notificar_admin_telegram(item):
    """Notificacao PRIVADA (nunca vai para o canal publico pago) -
    avisa que um novo conteudo foi gerado e ja esta salvo na fila,
    pronto para revisao manual. So e chamada DEPOIS que o item ja foi
    escrito com sucesso em docs/social_queue.json. Falha aqui nunca
    desfaz o que ja foi salvo - so o aviso que nao chega."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Content Engine: TELEGRAM_ADMIN_CHAT_ID nao configurado - aviso privado nao enviado.")
        return

    modo = item.get("content_mode", "?")
    topico = item.get("topic", "")
    score = item.get("score")
    reason = item.get("reason", "")

    preview = ""
    if item.get("x_post"):
        preview = item["x_post"][:200]
    elif isinstance(item.get("instagram_carousel"), dict) and item["instagram_carousel"].get("slide_1"):
        preview = item["instagram_carousel"]["slide_1"][:200]

    texto = (
        "🆕 <b>Novo conteúdo gerado</b>\n\n"
        "Modo: " + modo + "\n"
        "Assunto: " + topico
    )
    if score is not None:
        texto += "\nScore: " + str(score)
    if reason:
        texto += "\nMotivo: " + reason
    if preview:
        texto += "\n\nPrévia:\n" + preview

    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificacao privada (isolado, item ja esta salvo na fila): " + str(e))


def save_social_queue(item):
    """Acumula historico - nunca sobrescreve. Cada item ja vem com
    content_mode/score/reason definidos por quem gerou (Breaking/
    Midday/Closing) - aqui so adiciona date, status e metrics
    (preparado para integracao futura, nao coletado ainda)."""
    if item is None:
        return

    fila = load_social_queue()

    novo_item = dict(item)
    novo_item["date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    novo_item.setdefault("status", "pending")
    novo_item["metrics"] = {
        "views": None,
        "likes": None,
        "shares": None,
        "comments": None,
    }

    fila.append(novo_item)
    _save_json(SOCIAL_QUEUE_FILE, fila)

    print(
        "Social Content Engine: item adicionado a docs/social_queue.json "
        "(modo=" + novo_item.get("content_mode", "?") + ", topico=" + novo_item.get("topic", "") + ")"
    )

    # Notificacao privada so acontece AQUI - depois que o item ja esta
    # gravado com sucesso no arquivo, nunca antes.
    notificar_admin_telegram(novo_item)


# ---------------------------------------------------------------------------
# Ponto de entrada unico - e a UNICA funcao que o main.py precisa chamar
# ---------------------------------------------------------------------------

def run_social_content_engine(entries_today, clusters, market_insights, market_snapshot, events):
    """Roda TODO ciclo do bot (a cada 5 min). Avalia os 3 modos, cada
    um com seu proprio gatilho isolado - na grande maioria dos ciclos,
    nenhum dos 3 gera nada (comportamento esperado, nao falha)."""
    item_breaking = avaliar_breaking_content(clusters, market_snapshot, events)
    if item_breaking:
        save_social_queue(item_breaking)

    item_midday = avaliar_midday_snapshot(market_snapshot)
    if item_midday:
        save_social_queue(item_midday)

    item_closing = avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events)
    if item_closing:
        save_social_queue(item_closing)
