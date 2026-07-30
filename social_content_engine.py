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

Roda 1x por dia, na janela 18h30-19h00 (apos o fechamento do mercado e
o Evening Briefing), controlado por estado proprio em
docs/social_content_state.json.
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone

import requests

BR_TZ = timezone(timedelta(hours=-3))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_AI = bool(GROQ_API_KEY)

SOCIAL_CONTENT_STATE_FILE = "docs/social_content_state.json"
SOCIAL_QUEUE_FILE = "docs/social_queue.json"

# Janela de execucao: 18h30 as 19h00, apos o fechamento do mercado e o
# Evening Briefing, quando ja temos o conjunto completo de noticias do dia.
JANELA_INICIO_MINUTOS = 18 * 60 + 30
JANELA_FIM_MINUTOS = 19 * 60

# Limiar de variacao percentual para um dado de mercado ser considerado
# "movimento relevante" (prioridade 2 na escolha do assunto).
LIMIAR_MOVIMENTO_RELEVANTE = 1.5

# Marcadores de texto usados para detectar, dentro das frases ja
# prontas de market_insights["home"], se alguma delas e do tipo
# "mudanca de atencao" (rising/disappeared) - sem precisar importar a
# logica interna do main.py, so reconhecendo o padrao de texto que ela
# mesma produz.
MARCADORES_MUDANCA_ATENCAO = ["ganhou atenção", "saiu do radar"]


# ---------------------------------------------------------------------------
# Estado - gate de horario, isolado (nao compartilha arquivo com briefings)
# ---------------------------------------------------------------------------

def load_social_content_state():
    if os.path.exists(SOCIAL_CONTENT_STATE_FILE):
        try:
            with open(SOCIAL_CONTENT_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_social_content_date": ""}
    return {"last_social_content_date": ""}


def save_social_content_state(state):
    os.makedirs(os.path.dirname(SOCIAL_CONTENT_STATE_FILE), exist_ok=True)
    with open(SOCIAL_CONTENT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_generate_social_content():
    """Janela de 18h30 as 19h00, uma vez por dia. Se falhar dentro da
    janela, o estado nao e marcado como concluido - a proxima execucao
    (dentro da mesma janela) tenta de novo."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_social_content_state()
    if state.get("last_social_content_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return JANELA_INICIO_MINUTOS <= minutes <= JANELA_FIM_MINUTOS


# ---------------------------------------------------------------------------
# Escolha do assunto principal - 100% logica pura, ZERO chamada de IA
# ---------------------------------------------------------------------------

def escolher_assunto_principal(clusters, market_insights, market_snapshot, events):
    """Escolhe o assunto principal do dia seguindo a ordem de
    prioridade definida:
      1. Mudanca de atencao identificada pelo market_intelligence
      2. Movimento relevante de mercado (market_snapshot)
      3. Cluster de noticias mais relevante
      4. Evento importante proximo

    Retorna um dict {"tipo", "titulo", "contexto"} ou None se
    absolutamente nenhum dado estiver disponivel em nenhuma das 4
    fontes."""

    # 1. Mudanca de atencao (rising/disappeared) - reconhecida pelo
    # padrao de texto que a camada de inteligencia do site ja produz.
    home_insights = (market_insights or {}).get("home", [])
    for frase in home_insights:
        if any(marcador in frase for marcador in MARCADORES_MUDANCA_ATENCAO):
            return {"tipo": "mudanca_atencao", "titulo": frase, "contexto": frase}

    # 2. Movimento relevante de mercado - maior variacao absoluta entre
    # os dados disponiveis no snapshot, acima do limiar minimo.
    candidatos_mercado = []
    if market_snapshot:
        quotes_by_symbol = market_snapshot.get("quotes_by_symbol", {}) or {}
        ibovespa = quotes_by_symbol.get("^BVSP")
        if ibovespa and ibovespa.get("change") is not None:
            candidatos_mercado.append(("Ibovespa", ibovespa["change"]))

        mapa_campos = [
            ("Dólar", "usd"),
            ("Bitcoin", "bitcoin"),
            ("Petróleo (WTI)", "wti"),
        ]
        for nome, campo in mapa_campos:
            dado = market_snapshot.get(campo)
            if dado and dado.get("change") is not None:
                candidatos_mercado.append((nome, dado["change"]))

        sp500 = market_snapshot.get("sp500")
        if sp500 and sp500.get("change") is not None:
            candidatos_mercado.append(("S&P 500", sp500["change"]))

    if candidatos_mercado:
        candidatos_mercado.sort(key=lambda par: abs(par[1]), reverse=True)
        nome, variacao = candidatos_mercado[0]
        if abs(variacao) >= LIMIAR_MOVIMENTO_RELEVANTE:
            sinal = "+" if variacao >= 0 else ""
            titulo = nome + " " + sinal + str(round(variacao, 2)) + "%"
            contexto = nome + " teve variação de " + sinal + str(round(variacao, 2)) + "% no dia."
            return {"tipo": "movimento_mercado", "titulo": titulo, "contexto": contexto}

    # 3. Cluster de noticias mais relevante
    if clusters:
        top = clusters[0]
        rep = top.get("representative", {})
        titulo = rep.get("title", "")
        corpo = rep.get("body", "")
        if titulo:
            contexto = titulo + (". " + corpo if corpo else "")
            return {"tipo": "cluster_noticia", "titulo": titulo, "contexto": contexto}

    # 4. Evento importante proximo (hoje ou nos proximos dias)
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


# ---------------------------------------------------------------------------
# Chamada a IA - UNICA por execucao, isolada (nao reaproveita main.py)
# ---------------------------------------------------------------------------

def ask_groq_isolado(prompt):
    """Copia pequena e independente da chamada a Groq - usa a mesma
    GROQ_API_KEY (variavel de ambiente ja configurada como secret),
    mas nao importa nem depende de nenhuma funcao do main.py."""
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
    """Extrai o primeiro objeto JSON valido de um texto que pode vir
    com prosa antes/depois. Retorna None se nao encontrar nada
    parseavel - nunca lanca excecao pro chamador."""
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


def montar_prompt_unico(assunto, entries_today):
    """Monta o prompt unico que gera Instagram + TikTok + X numa unica
    chamada - reduz custo e garante contexto editorial consistente
    entre as 3 plataformas."""
    manchetes_apoio = ""
    for e in (entries_today or [])[:8]:
        manchetes_apoio += "- " + e.get("title", "") + "\n"

    instrucao = (
        "Voce e o redator de conteudo do canal 'Antes do Sino', especializado em "
        "educacao financeira e contexto de mercado para redes sociais (Instagram, "
        "TikTok e X). Use SOMENTE os fatos e numeros fornecidos abaixo - nunca "
        "invente dado, numero ou informacao que nao esteja explicitamente aqui. "
        "Nunca de opiniao de investimento (nunca diga 'compre', 'venda', 'e um bom "
        "momento para investir'). Priorize educacao e contexto, nunca sensacionalismo.\n\n"
        "ASSUNTO PRINCIPAL DE HOJE:\n" + assunto["titulo"] + "\n\n"
        "CONTEXTO DISPONIVEL:\n" + assunto["contexto"] + "\n\n"
        "MANCHETES DE APOIO DO DIA (para contexto adicional, se util):\n" + manchetes_apoio + "\n\n"
        "Gere TRES conteudos, simultaneamente, mantendo o MESMO contexto editorial "
        "entre eles:\n\n"
        "1. INSTAGRAM (carrossel de exatamente 6 slides):\n"
        "   Slide 1: titulo com gancho forte (chama atencao, sem sensacionalismo)\n"
        "   Slide 2: o que aconteceu (fato, direto)\n"
        "   Slide 3: por que o mercado reagiu (contexto, causa)\n"
        "   Slide 4: quem e afetado (setores, investidores, consumidores)\n"
        "   Slide 5: resumo final (sintese em 1-2 frases)\n"
        "   Slide 6: CTA discreto para acompanhar o mercado no Antes do Sino "
        "(sem soar como propaganda agressiva)\n\n"
        "2. TIKTOK/REELS (roteiro falado de ate 45 segundos):\n"
        "   gancho: primeiros 3 segundos, frase de impacto\n"
        "   explicacao: o que aconteceu, em linguagem simples\n"
        "   contexto: por que isso importa\n"
        "   fechamento_cta: encerramento com convite discreto pra seguir o canal\n\n"
        "3. X/TWITTER (post unico, MAXIMO 280 caracteres, informativo, sem soar "
        "como propaganda):\n\n"
        "Responda APENAS em JSON plano, sem markdown, sem texto antes ou depois, "
        "no formato exato:\n"
        '{"instagram_carousel": {"slide_1": "...", "slide_2": "...", "slide_3": "...", '
        '"slide_4": "...", "slide_5": "...", "slide_6": "..."}, '
        '"tiktok_script": {"gancho": "...", "explicacao": "...", "contexto": "...", '
        '"fechamento_cta": "..."}, '
        '"x_post": "..."}'
    )
    return instrucao


def validar_conteudo_gerado(parsed):
    """Validacao defensiva do JSON retornado pela IA - qualquer campo
    ausente ou malformado usa fallback vazio, nunca quebra a
    montagem final."""
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
    x_post = str(x_post).strip() if isinstance(x_post, str) else ""
    x_post = x_post[:280]

    return {
        "instagram_carousel": instagram_carousel,
        "tiktok_script": tiktok_script,
        "x_post": x_post,
    }


# ---------------------------------------------------------------------------
# Orquestradora principal
# ---------------------------------------------------------------------------

def generate_social_content(entries_today, clusters, market_insights, market_snapshot, events):
    """Funcao principal do Social Content Engine.

    Recebe todos os dados ja calculados pelo main() (nenhum calculo
    proprio de noticia/mercado acontece aqui) e retorna:
        {"instagram_carousel": {...}, "tiktok_script": {...}, "x_post": "...",
         "topic": "..."}

    Retorna None se nao houver assunto disponivel (as 4 fontes de
    prioridade vazias) ou se a IA nao estiver configurada/falhar - a
    chamada e UNICA por execucao, nunca 3 chamadas separadas."""
    assunto = escolher_assunto_principal(clusters, market_insights, market_snapshot, events)
    if assunto is None:
        print("Social Content Engine: nenhum assunto disponivel hoje - nada gerado.")
        return None

    if not USE_AI:
        print("Social Content Engine: GROQ_API_KEY nao configurada - nada gerado.")
        return None

    try:
        prompt = montar_prompt_unico(assunto, entries_today)
        raw_response = ask_groq_isolado(prompt)
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_gerado(parsed)
        if conteudo is None:
            print("Social Content Engine: resposta da IA invalida - nada gerado.")
            return None

        conteudo["topic"] = assunto["titulo"]
        return conteudo
    except Exception as e:
        print("Erro no Social Content Engine (isolado): " + str(e))
        return None


# ---------------------------------------------------------------------------
# Persistencia - fila acumulativa, nunca sobrescreve
# ---------------------------------------------------------------------------

def load_social_queue():
    if os.path.exists(SOCIAL_QUEUE_FILE):
        try:
            with open(SOCIAL_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception:
            return []
    return []


def save_social_queue(conteudo_gerado):
    """Acumula historico - le a fila existente, adiciona o item novo
    no formato com 'metrics' preparado para integracao futura (ainda
    nao coletado), e regrava a lista inteira. Nunca sobrescreve o
    historico anterior."""
    if conteudo_gerado is None:
        return

    fila = load_social_queue()

    novo_item = {
        "date": datetime.now(BR_TZ).strftime("%Y-%m-%d"),
        "topic": conteudo_gerado.get("topic", ""),
        "instagram_carousel": conteudo_gerado.get("instagram_carousel", {}),
        "tiktok_script": conteudo_gerado.get("tiktok_script", {}),
        "x_post": conteudo_gerado.get("x_post", ""),
        "status": "pending",
        "metrics": {
            "views": None,
            "likes": None,
            "shares": None,
            "comments": None,
        },
    }

    fila.append(novo_item)

    os.makedirs(os.path.dirname(SOCIAL_QUEUE_FILE), exist_ok=True)
    with open(SOCIAL_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)

    print("Social Content Engine: item adicionado a docs/social_queue.json (assunto: " + novo_item["topic"] + ")")


def run_social_content_engine(entries_today, clusters, market_insights, market_snapshot, events):
    """Ponto de entrada UNICO do modulo - e a unica funcao que o
    main.py precisa chamar. Encapsula o gate de horario, a geracao e
    o registro de estado, mantendo essa orquestracao isolada aqui
    dentro (o main.py nao gerencia estado nem condicao de horario)."""
    if not should_generate_social_content():
        return

    conteudo = generate_social_content(entries_today, clusters, market_insights, market_snapshot, events)
    if conteudo is None:
        return

    save_social_queue(conteudo)

    state = load_social_content_state()
    state["last_social_content_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_social_content_state(state)
