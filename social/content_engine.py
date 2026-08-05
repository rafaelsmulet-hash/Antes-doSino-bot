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

# Checagem de dia util - duplicada de proposito (isolamento do
# main.py). Mesma fonte (Brasil API, gratuita, sem chave) e mesmo
# fallback fixo caso a API esteja fora do ar.
FERIADOS_STATE_FILE = "docs/feriados_cache.json"

FERIADOS_B3_FALLBACK_2026 = [
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21",
    "2026-05-01", "2026-06-04", "2026-09-07", "2026-10-12", "2026-11-02",
    "2026-11-15", "2026-11-20", "2026-12-25",
]


def _carregar_feriados_do_ano(ano):
    cache = {}
    if os.path.exists(FERIADOS_STATE_FILE):
        try:
            with open(FERIADOS_STATE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    chave_ano = str(ano)
    if chave_ano in cache:
        return cache[chave_ano]

    try:
        url = "https://brasilapi.com.br/api/feriados/v1/" + str(ano)
        response = requests.get(url, timeout=10)
        data = response.json()
        datas = [item["date"] for item in data if "date" in item]
        if not datas:
            raise ValueError("resposta vazia da Brasil API")
        cache[chave_ano] = datas
        os.makedirs(os.path.dirname(FERIADOS_STATE_FILE), exist_ok=True)
        with open(FERIADOS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return datas
    except Exception as e:
        print("Erro ao buscar feriados via Brasil API (usando lista fixa de reserva): " + str(e))
        if ano == 2026:
            return FERIADOS_B3_FALLBACK_2026
        return []


def eh_dia_util_b3():
    """Combina fim de semana + feriado nacional - usado como guarda
    dos modos editoriais obrigatorios (Opening, Closing, Midday). O
    Breaking (oportunista) NAO usa essa guarda - continua avaliado
    todo ciclo, mas naturalmente tende a nao ter sinal forte em dia
    sem pregao."""
    agora = datetime.now(BR_TZ)
    if agora.weekday() >= 5:
        return False
    feriados_do_ano = _carregar_feriados_do_ano(agora.year)
    hoje_str = agora.strftime("%Y-%m-%d")
    return hoje_str not in feriados_do_ano

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

OPENING_JANELA_INICIO_MINUTOS = 8 * 60 + 15
OPENING_JANELA_FIM_MINUTOS = 8 * 60 + 45

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

# Frases banidas em qualquer prompt de geracao - genericas, nao dizem
# nada de concreto. Se o assunto so puder ser descrito com frases
# desse tipo, a instrucao do prompt e OMITIR a secao, nunca preencher
# com uma dessas.
FRASES_PROIBIDAS = [
    "isso pode impactar",
    "vale acompanhar",
    "os investidores estarão atentos",
    "os investidores seguem atentos",
    "o mercado seguirá observando",
    "o mercado continua monitorando",
    "o mercado mudou o foco",
    "acompanhe as próximas notícias",
    "isso pode indicar",
]
TEXTO_FRASES_PROIBIDAS_PROMPT = (
    "PROIBIDO usar frases genericas e vazias, como: \"isso pode impactar o "
    "mercado\", \"vale acompanhar\", \"os investidores estarao atentos\", \"o "
    "mercado segue monitorando\", \"o mercado mudou o foco\", \"acompanhe as "
    "proximas noticias\", \"isso pode indicar\". Se voce nao tem um fato "
    "concreto para preencher uma secao, OMITA essa secao (deixe a string "
    "vazia) em vez de preencher com uma frase vaga."
)

# Camada de analise editorial - roda ANTES da redacao final, na MESMA
# chamada de IA (nao gasta chamada extra). Forca a IA a pensar como um
# editor de mercado antes de escrever: identificar tipo de noticia,
# a historia real por tras do numero, e quais blocos tem substancia
# real pra preencher - em vez de so parafrasear a manchete.
TEXTO_ANALISE_EDITORIAL_PROMPT = (
    "Antes de escrever o conteudo final, faca uma analise editorial mental "
    "(que tambem sera registrada no campo 'editorial' da resposta):\n"
    "1. tipo_noticia: classifique em um destes: Macro, Empresa, Commodities, "
    "Mercado, Internacional, Politica/economia, Setorial, Outro.\n"
    "2. historia_principal: identifique qual e a informacao real que um "
    "investidor precisa entender - NUNCA repita a manchete. Exemplo: se a "
    "entrada e 'Ibovespa fecha em queda de 1,5%', a manchete NAO e a "
    "historia - a historia e o motivo real por tras da queda (ex: 'mercado "
    "reduziu exposicao a risco apos alta dos juros americanos'). A queda e "
    "consequencia; a explicacao e o que importa.\n"
    "3. Decida quais blocos (context, why_it_matters, impact, watch_next) "
    "tem substancia real de acordo com o que foi fornecido. NUNCA force um "
    "bloco de 'quem ganha/quem perde' ou impacto se a informacao nao "
    "existir nos dados fornecidos - nesse caso, deixe o campo vazio.\n\n"
    "Regras invioláveis: nunca invente numero, nunca invente impacto, nunca "
    "invente ganhador/perdedor que nao esteja explicito nos dados fornecidos."
)


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
        "Voce e o editor de mercado do canal 'Antes do Sino', especializado em "
        "educacao financeira e contexto de mercado para redes sociais. Use SOMENTE "
        "os fatos e numeros fornecidos abaixo - nunca invente dado, numero ou "
        "informacao que nao esteja explicitamente aqui. Nunca de opiniao de "
        "investimento. Priorize educacao e contexto, nunca sensacionalismo.\n\n"
        + TEXTO_ANALISE_EDITORIAL_PROMPT + "\n\n"
        "ASSUNTO PRINCIPAL:\n" + assunto["titulo"] + "\n\n"
        "CONTEXTO DISPONIVEL:\n" + assunto["contexto"] + "\n\n"
        "MANCHETES DE APOIO:\n" + manchetes_apoio + "\n\n"
        "Gere PRIMEIRO a analise editorial, depois uma headline central baseada na "
        "HISTORIA REAL (nao na manchete), e depois os 3 formatos DERIVADOS dessa "
        "mesma ideia central:\n\n"
        "1. editorial: {tipo_noticia, historia_principal} conforme instruido acima.\n\n"
        "2. headline: frase unica e direta que comunica a HISTORIA PRINCIPAL "
        "identificada, nao apenas a manchete original.\n\n"
        "3. instagram (campos separados - preencha SOMENTE os que tiverem "
        "substancia real; deixe string vazia os que nao tiverem):\n"
        "   hook: gancho forte de abertura, baseado na historia principal\n"
        "   context: o que aconteceu, direto\n"
        "   why_it_matters: por que aconteceu de verdade (a explicacao, nao so o fato)\n"
        "   impact: como o mercado reagiu (indices/acoes/setores) - inclua "
        "quem ganha/quem perde SOMENTE se isso estiver claro nos dados fornecidos\n"
        "   watch_next: o que acompanhar agora (proximos eventos ou riscos concretos)\n"
        "   cta: encerramento discreto convidando a acompanhar o Antes do Sino\n\n"
        "4. instagram_caption: LEGENDA do post do Instagram - texto SEPARADO do "
        "que fica dentro da imagem (diferente dos campos do item 3 acima). E o "
        "texto que vai na descricao do post, curto (2-4 frases), retomando a "
        "historia principal e terminando com convite discreto pra acompanhar o "
        "Antes do Sino.\n\n"
        "5. x: post unico para X/Twitter, MAXIMO 280 caracteres, com angulo "
        "explicativo (nunca so a manchete pura).\n\n"
        "6. tiktok: roteiro falado de ate 45 segundos, em cenas:\n"
        "   scenes: lista de objetos {\"visual\": \"o que aparece na tela\", "
        "\"line\": \"fala do narrador\"}\n"
        "   cta: fechamento com convite discreto\n\n"
        + TEXTO_FRASES_PROIBIDAS_PROMPT + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"editorial": {"tipo_noticia": "...", "historia_principal": "..."}, '
        '"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "...", "cta": "..."}, '
        '"instagram_caption": "...", '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )


HASHTAGS_POR_TIPO = {
    "Macro": ["#Macroeconomia", "#Juros"],
    "Empresa": ["#Empresas", "#Resultados"],
    "Commodities": ["#Commodities", "#Petróleo"],
    "Mercado": ["#Mercado", "#Bolsa"],
    "Internacional": ["#MercadoInternacional", "#WallStreet"],
    "Politica/economia": ["#Economia", "#Política"],
    "Setorial": ["#Setores", "#Mercado"],
    "Outro": ["#Mercado", "#Investimentos"],
}


def _gerar_hashtags(tipo_noticia):
    """Gera hashtags de forma DETERMINISTICA (sem IA) a partir do tipo
    de noticia ja classificado - evita adicionar mais uma chamada de
    IA so pra isso, e garante que hashtag nunca fique ausente mesmo
    no fallback sem IA."""
    especificas = HASHTAGS_POR_TIPO.get(tipo_noticia, HASHTAGS_POR_TIPO["Outro"])
    return ["#AntesDoSino"] + especificas + ["#Investimentos"]


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

    # Legenda do Instagram - texto SEPARADO do que fica dentro da
    # imagem (campos de "instagram" acima). E o texto que vai na
    # descricao do post, nao renderizado no carrossel/card.
    legenda_raw = parsed.get("instagram_caption", "")
    instagram_caption = str(legenda_raw).strip() if isinstance(legenda_raw, str) else ""
    if not instagram_caption:
        # Fallback deterministico, sem IA - usa hook + cta ja
        # existentes, nunca fica vazio.
        instagram_caption = (instagram.get("hook", "") + " " + instagram.get("cta", "")).strip()

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

    # Bloco de analise editorial - PURAMENTE informativo (nunca bloqueia
    # a geracao se vier ausente ou malformado). Guardado no item so
    # para transparencia/auditoria futura, o design engine nunca
    # precisa dele.
    TIPOS_VALIDOS = ["Macro", "Empresa", "Commodities", "Mercado", "Internacional", "Politica/economia", "Setorial", "Outro"]
    editorial_raw = parsed.get("editorial", {})
    editorial = {"tipo_noticia": "Outro", "historia_principal": ""}
    if isinstance(editorial_raw, dict):
        tipo = editorial_raw.get("tipo_noticia", "")
        if isinstance(tipo, str) and tipo.strip() in TIPOS_VALIDOS:
            editorial["tipo_noticia"] = tipo.strip()
        historia = editorial_raw.get("historia_principal", "")
        if isinstance(historia, str):
            editorial["historia_principal"] = historia.strip()

    return {
        "headline": headline,
        "instagram": instagram,
        "instagram_caption": instagram_caption,
        "hashtags": _gerar_hashtags(editorial["tipo_noticia"]),
        "x": {"post": post},
        "tiktok": {"scenes": scenes, "cta": tiktok_cta},
        "editorial": editorial,
    }


def _truncar_limpo(texto, limite):
    """Corta o texto no limite de caracteres sem quebrar palavra no
    meio - usada pelos fallbacks pra caber no limite do X sem gerar
    corte feio. Reserva espaco pras reticencias, pra NUNCA ultrapassar
    o limite total (incluindo o '...')."""
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    limite_para_corte = limite - 3  # reserva espaco para "..."
    cortado = texto[:limite_para_corte].rsplit(" ", 1)[0]
    return cortado.rstrip(".,;:") + "..."


def _fallback_template_conteudo(assunto):
    """Fallback por template - usado quando a chamada a IA falha (ex:
    limite diario da Groq atingido). Garante que o Social Content
    Engine NUNCA deixe de gerar conteudo por indisponibilidade de IA.

    Usa o titulo E o contexto real ja disponiveis (nunca inventa nada
    novo) para dar mais substancia ao X/legenda do que so repetir a
    manchete - evita o problema de posts tipo 'Titulo: o que muda?'
    sem responder nada."""
    titulo = assunto["titulo"]
    contexto = assunto.get("contexto", titulo)
    contexto_ja_inclui_titulo = contexto.strip().lower().startswith(titulo.strip().lower())
    tem_contexto_real = contexto and contexto.strip() != titulo.strip()

    if tem_contexto_real:
        texto_combinado = contexto if contexto_ja_inclui_titulo else (titulo + ". " + contexto)
    else:
        texto_combinado = titulo

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
        "instagram_caption": _truncar_limpo(texto_combinado + " Acompanhe o mercado no Antes do Sino.", 500),
        "x": {"post": _truncar_limpo(texto_combinado, 280)},
        "tiktok": {"scenes": [], "cta": ""},
        "editorial": {"tipo_noticia": "Outro", "historia_principal": ""},
        "hashtags": _gerar_hashtags("Outro"),
    }


def _fallback_template_editorial(headline, corpo_disponivel, content_mode):
    """Fallback por template para conteudo EDITORIAL (Opening/Closing)
    - esses modos nao tem um 'assunto' unico, entao o fallback usa o
    que ja foi coletado deterministicamente (panorama/numeros), nunca
    inventando fato. Usado so quando a IA falha."""
    tem_corpo_real = bool(corpo_disponivel and corpo_disponivel.strip())
    texto_combinado = (headline + ". " + corpo_disponivel) if tem_corpo_real else headline

    return {
        "headline": headline,
        "instagram": {
            "hook": headline,
            "context": corpo_disponivel or "Sem dados suficientes no momento.",
            "why_it_matters": "",
            "impact": "",
            "watch_next": "",
            "cta": "Acompanhe o mercado no Antes do Sino.",
        },
        "instagram_caption": _truncar_limpo(texto_combinado + " Acompanhe o mercado no Antes do Sino.", 500),
        "x": {"post": _truncar_limpo(texto_combinado, 280)},
        "tiktok": {"scenes": [], "cta": ""},
        "editorial": {"tipo_noticia": "Outro", "historia_principal": ""},
        "hashtags": _gerar_hashtags("Outro"),
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


def montar_dados_closing(market_snapshot, clusters, events):
    """Coleta pura (sem IA) dos dados fixos do Closing - numeros do
    fechamento, fato principal (SE existir cluster forte de verdade -
    nao usa mais 'mudanca de atencao', que gera texto vago demais),
    maior alta/baixa entre os ativos ja cotados, e proximos eventos
    reais (nunca frase vaga tipo 'observar o mercado')."""
    linhas_resumo = []
    quotes_by_symbol = (market_snapshot or {}).get("quotes_by_symbol", {}) or {}

    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa and ibovespa.get("change") is not None:
        linhas_resumo.append("Ibovespa: " + _formata_variacao(ibovespa["change"]))
    sp500 = (market_snapshot or {}).get("sp500")
    if sp500 and sp500.get("change") is not None:
        linhas_resumo.append("S&P 500: " + _formata_variacao(sp500["change"]))
    usd = (market_snapshot or {}).get("usd")
    if usd and usd.get("change") is not None:
        linhas_resumo.append("Dólar: " + _formata_variacao(usd["change"]))
    wti = (market_snapshot or {}).get("wti")
    if wti and wti.get("change") is not None:
        linhas_resumo.append("Petróleo (WTI): " + _formata_variacao(wti["change"]))
    bitcoin = (market_snapshot or {}).get("bitcoin")
    if bitcoin and bitcoin.get("change") is not None:
        linhas_resumo.append("Bitcoin: " + _formata_variacao(bitcoin["change"]))

    # Fato principal: SOMENTE cluster de verdade (varias fontes) -
    # nunca "mudanca de atencao" isolada, que nao tem substancia
    # suficiente pra explicar "por que aconteceu" de forma concreta.
    fato_principal = None
    if clusters:
        top = clusters[0]
        if top.get("distinct_sources", 0) >= 2:
            rep = top.get("representative", {})
            titulo = rep.get("title", "")
            if titulo:
                fato_principal = titulo + (". " + rep.get("body", "") if rep.get("body") else "")

    # Maiores destaques positivos/negativos - direto da cotacao real,
    # nao inventado.
    ativos_com_variacao = [(q.get("symbol"), q.get("change")) for q in (market_snapshot or {}).get("quotes", []) if q.get("change") is not None]
    maior_alta = max(ativos_com_variacao, key=lambda par: par[1]) if ativos_com_variacao else None
    maior_baixa = min(ativos_com_variacao, key=lambda par: par[1]) if ativos_com_variacao else None

    # Proximos eventos reais (nao "observar o mercado") - so os que
    # realmente existem no calendario.
    hoje = datetime.now(BR_TZ).date()
    proximos_eventos = []
    for ev in events or []:
        try:
            data_evento = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if 0 <= (data_evento - hoje).days <= 5:
            proximos_eventos.append(ev.get("label", ""))

    return {
        "resumo_indices": linhas_resumo,
        "fato_principal": fato_principal,
        "maior_alta": maior_alta,
        "maior_baixa": maior_baixa,
        "proximos_eventos": proximos_eventos,
    }


def gerar_conteudo_closing(dados, entries_today):
    """Closing e um conteudo EDITORIAL OBRIGATORIO - sempre responde
    'como foi o pregao hoje?', mesmo sem fato de destaque. Quando nao
    ha fato principal real, instrui a IA a descrever o COMPORTAMENTO
    do mercado (ex: 'fechou estavel'), nunca uma frase vaga tipo
    'o mercado seguira monitorando'. Identifica a HISTORIA CENTRAL do
    dia e constroi a narrativa a partir dela - nao e um agrupamento de
    manchetes soltas."""
    resumo_texto = "\n".join(dados["resumo_indices"]) if dados["resumo_indices"] else "(nenhum dado de fechamento disponivel)"
    fato_texto = dados["fato_principal"] or "(nenhum fato de destaque com cobertura solida hoje - descreva o comportamento geral do mercado com base nos numeros do resumo)"
    destaques_texto = ""
    if dados["maior_alta"]:
        destaques_texto += "Maior alta entre os ativos acompanhados: " + dados["maior_alta"][0] + " " + _formata_variacao(dados["maior_alta"][1]) + "\n"
    if dados["maior_baixa"]:
        destaques_texto += "Maior baixa entre os ativos acompanhados: " + dados["maior_baixa"][0] + " " + _formata_variacao(dados["maior_baixa"][1]) + "\n"
    if not destaques_texto:
        destaques_texto = "(nenhum destaque de ativo individual disponivel)"
    eventos_texto = "\n".join(dados["proximos_eventos"]) if dados["proximos_eventos"] else "(nenhum evento concreto nos proximos dias)"

    prompt = (
        "Voce e o editor de mercado do canal 'Antes do Sino'. Use SOMENTE os dados "
        "abaixo - nunca invente numero, fato ou evento. Nunca de opiniao de "
        "investimento. Se nao houver um fato principal real, descreva o "
        "COMPORTAMENTO do mercado com base nos numeros (exemplo: 'o Ibovespa "
        "encerrou o dia praticamente estavel, refletindo um pregao de baixa "
        "volatilidade') - isso e sempre melhor que uma frase vaga.\n\n"
        + TEXTO_ANALISE_EDITORIAL_PROMPT + "\n\n"
        "IMPORTANTE: identifique qual foi A PRINCIPAL HISTORIA do mercado hoje - "
        "nao liste fatos soltos. Monte toda a narrativa do post em torno dessa "
        "unica historia central.\n\n"
        "RESUMO DOS INDICES:\n" + resumo_texto + "\n\n"
        "FATO PRINCIPAL DO DIA:\n" + fato_texto + "\n\n"
        "MAIORES DESTAQUES (alta/baixa):\n" + destaques_texto + "\n\n"
        "PROXIMOS EVENTOS CONCRETOS:\n" + eventos_texto + "\n\n"
        "Este e o conteudo de FECHAMENTO - responda 'como foi o pregao hoje?', "
        "com uma narrativa coerente (nao uma lista de manchetes). Gere a analise "
        "editorial, headline + instagram + x + tiktok, usando esta estrutura no "
        "campo instagram:\n"
        "   hook: resumo do dia em 1 frase\n"
        "   context: principais numeros do fechamento\n"
        "   why_it_matters: a HISTORIA CENTRAL identificada - o principal "
        "acontecimento que explicou o dia (ou o comportamento do mercado, se nao "
        "houver fato de destaque) - nunca especulacao\n"
        "   impact: destaques positivos e negativos (quando existirem) E o que "
        "isso significa para o investidor - combine os dois numa explicacao so; "
        "se nao houver destaque de ativo, deixe vazio\n"
        "   watch_next: o que observar no proximo pregao, SOMENTE com base nos "
        "eventos concretos fornecidos - se nao houver nenhum, deixe vazio\n"
        "   cta: encerramento discreto convidando a acompanhar o Antes do Sino\n\n"
        "instagram_caption: LEGENDA do post do Instagram - texto SEPARADO do que "
        "fica dentro da imagem. Curto (2-4 frases), retomando a historia principal "
        "e terminando com convite discreto pra acompanhar o Antes do Sino.\n\n"
        "x: post curto para X/Twitter, MAXIMO 280 caracteres.\n"
        "tiktok: roteiro falado de ate 45 segundos, em cenas.\n\n"
        + TEXTO_FRASES_PROIBIDAS_PROMPT + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"editorial": {"tipo_noticia": "...", "historia_principal": "..."}, '
        '"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "...", "cta": "..."}, '
        '"instagram_caption": "...", '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )

    try:
        raw_response = ask_groq_isolado(prompt, purpose="generation")
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_unificado(parsed)
        if conteudo is None:
            print("Closing: resposta da IA invalida - usando fallback por template.")
            return _fallback_template_editorial("Fechamento do pregão", resumo_texto, "closing")
        return conteudo
    except Exception as e:
        print("Erro ao gerar conteudo do Closing (usando fallback por template): " + str(e))
        return _fallback_template_editorial("Fechamento do pregão", resumo_texto, "closing")


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
        "instagram_caption": _truncar_limpo(headline + " Acompanhe o mercado em tempo real no Antes do Sino.", 500),
        "x": {"post": _truncar_limpo(headline, 280)},
        "tiktok": {"scenes": [], "cta": ""},
        "editorial": {"tipo_noticia": "Mercado", "historia_principal": ""},
        "hashtags": _gerar_hashtags("Mercado"),
    }


# ---------------------------------------------------------------------------
# Escolha de assunto - logica pura, sem IA (Opening e Closing usam a
# mesma; Breaking tem a sua propria com score)
# ---------------------------------------------------------------------------

def montar_dados_opening(market_snapshot, events):
    """Coleta pura (sem IA) dos dados fixos do Opening - panorama de
    mercado e agenda do dia. So inclui o que existe de verdade no
    snapshot - nunca inventa secao pra dado ausente (ex: Nasdaq,
    futuros e minerio de ferro ainda nao tem fonte no projeto, entao
    simplesmente nao aparecem, sem gerar erro)."""
    linhas_panorama = []
    quotes_by_symbol = (market_snapshot or {}).get("quotes_by_symbol", {}) or {}

    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa and ibovespa.get("change") is not None:
        linhas_panorama.append("Ibovespa: " + _formata_variacao(ibovespa["change"]))

    sp500 = (market_snapshot or {}).get("sp500")
    if sp500 and sp500.get("change") is not None:
        linhas_panorama.append("S&P 500 (ultimo fechamento): " + _formata_variacao(sp500["change"]))

    usd = (market_snapshot or {}).get("usd")
    if usd and usd.get("change") is not None:
        linhas_panorama.append("Dólar: " + _formata_variacao(usd["change"]))

    wti = (market_snapshot or {}).get("wti")
    if wti and wti.get("change") is not None:
        linhas_panorama.append("Petróleo (WTI): " + _formata_variacao(wti["change"]))

    bitcoin = (market_snapshot or {}).get("bitcoin")
    if bitcoin and bitcoin.get("change") is not None:
        linhas_panorama.append("Bitcoin: " + _formata_variacao(bitcoin["change"]))

    selic = (market_snapshot or {}).get("selic")
    if selic is not None:
        linhas_panorama.append("CDI/Selic: " + str(selic) + "% a.a.")

    hoje = datetime.now(BR_TZ).date()
    eventos_hoje = []
    for ev in events or []:
        try:
            data_evento = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if data_evento == hoje:
            eventos_hoje.append(ev.get("label", ""))

    return {"panorama": linhas_panorama, "agenda_hoje": eventos_hoje}


def gerar_conteudo_opening(dados, entries_today):
    """Opening ('Agenda do Dia') e um conteudo EDITORIAL OBRIGATORIO -
    nunca depende de 'ter uma boa noticia'. Sempre gera algo, com
    exatamente 4 pontos: o que observar hoje, agenda economica,
    empresas/eventos relevantes, o que merece atencao. NUNCA inclui
    horario exato de evento nem consenso de mercado - essas fontes
    nao existem no projeto hoje."""
    manchetes_apoio = ""
    for e in (entries_today or [])[:8]:
        manchetes_apoio += "- " + e.get("title", "") + "\n"

    panorama_texto = "\n".join(dados["panorama"]) if dados["panorama"] else "(nenhum dado de mercado disponivel no momento)"
    agenda_texto = "\n".join(dados["agenda_hoje"]) if dados["agenda_hoje"] else "(nenhum evento macro previsto para hoje)"

    prompt = (
        "Voce e o editor de mercado do canal 'Antes do Sino', especializado em "
        "preparar o investidor para o pregao do dia. Use SOMENTE os dados "
        "fornecidos abaixo - nunca invente numero, evento, horario ou consenso de "
        "mercado (essas informacoes nao estao disponiveis - se a agenda so tiver "
        "a DATA do evento, use so a data, nunca invente horario ou expectativa). "
        "Nunca de opiniao de investimento.\n\n"
        + TEXTO_ANALISE_EDITORIAL_PROMPT + "\n\n"
        "PANORAMA DE MERCADO DISPONIVEL (contexto de apoio):\n" + panorama_texto + "\n\n"
        "AGENDA ECONOMICA DE HOJE (so datas, sem horario/consenso):\n" + agenda_texto + "\n\n"
        "MANCHETES DE EMPRESAS/EVENTOS DE HOJE:\n" + (manchetes_apoio or "(nenhuma)") + "\n\n"
        "Este e o conteudo de ABERTURA do dia ('Agenda do Dia') - estrutura de "
        "EXATAMENTE 4 pontos. Gere a analise editorial, headline + instagram + x "
        "+ tiktok, usando esta estrutura no campo instagram:\n"
        "   hook: o que observar hoje - gancho curto resumindo a prioridade do dia\n"
        "   context: agenda economica de hoje (baseado SOMENTE na agenda "
        "fornecida - se nao houver evento, deixe vazio)\n"
        "   why_it_matters: empresas ou eventos relevantes de hoje (baseado "
        "SOMENTE nas manchetes fornecidas - se nao houver nada concreto, deixe "
        "vazio)\n"
        "   impact: o que merece atencao no mercado hoje (baseado no panorama e "
        "nas manchetes - se nao houver nada concreto, deixe vazio)\n"
        "   watch_next: deixe vazio (nao faz parte da estrutura da Agenda do Dia)\n"
        "   cta: encerramento discreto convidando a acompanhar o Antes do Sino\n\n"
        "instagram_caption: LEGENDA do post do Instagram - texto SEPARADO do que "
        "fica dentro da imagem. Curto (2-4 frases), retomando a historia principal "
        "e terminando com convite discreto pra acompanhar o Antes do Sino.\n\n"
        "x: post curto para X/Twitter, MAXIMO 280 caracteres.\n"
        "tiktok: roteiro falado de ate 45 segundos, em cenas.\n\n"
        + TEXTO_FRASES_PROIBIDAS_PROMPT + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"editorial": {"tipo_noticia": "...", "historia_principal": "..."}, '
        '"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "", "cta": "..."}, '
        '"instagram_caption": "...", '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )

    try:
        raw_response = ask_groq_isolado(prompt, purpose="generation")
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_unificado(parsed)
        if conteudo is None:
            print("Opening: resposta da IA invalida - usando fallback por template.")
            return _fallback_template_editorial("Agenda do Dia", panorama_texto, "opening")
        return conteudo
    except Exception as e:
        print("Erro ao gerar conteudo do Opening (usando fallback por template): " + str(e))
        return _fallback_template_editorial("Agenda do Dia", panorama_texto, "opening")


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

def calcular_score_conteudo(clusters, market_snapshot, events):
    """Score por CAMADA EXCLUSIVA (nao soma mais) - retorna o MAIOR
    nivel encontrado, de 0 a 10. Mede potencial de CONTEUDO, nao so
    relevancia de mercado.

    Niveis:
      10 - fato extremamente relevante (entidade de alto impacto + cluster muito forte)
       9 - movimento excepcional (>=4%)
       8 - evento macro muito importante hoje (Copom/Fed/Payroll/CPI)
       7 - cluster muito forte (3+ fontes distintas)
       6 - movimento relevante (>=2%) ou ativo ganhando atencao com cobertura consistente
       2 - conteudo fraco (sinal existe, mas sem substancia real - nao deve virar post)

    Retorna (nivel:int, motivo:str, assunto:dict|None)."""
    top_cluster = clusters[0] if clusters else None
    texto_cluster = ""
    distinct_sources = 0
    if top_cluster:
        rep = top_cluster.get("representative", {})
        texto_cluster = (rep.get("title", "") + " " + rep.get("body", "")).lower()
        distinct_sources = top_cluster.get("distinct_sources", 0)

    tem_entidade_alto_impacto = bool(texto_cluster) and any(ent in texto_cluster for ent in ENTIDADES_ALTO_IMPACTO)

    movimentos = _coletar_movimentos_mercado(market_snapshot)
    maior_movimento = None
    if movimentos:
        movimentos.sort(key=lambda par: abs(par[1]), reverse=True)
        maior_movimento = movimentos[0]

    evento_macro = _evento_macro_e_hoje(events)

    candidatos = []

    if tem_entidade_alto_impacto and distinct_sources >= 4:
        candidatos.append((10, "Fato extremamente relevante - entidade de alto impacto com ampla cobertura (" + str(distinct_sources) + " fontes)"))

    if maior_movimento and abs(maior_movimento[1]) >= 4.0:
        candidatos.append((9, "Movimento excepcional: " + maior_movimento[0] + " " + _formata_variacao(maior_movimento[1])))

    if evento_macro:
        candidatos.append((8, "Evento macro muito importante hoje: " + evento_macro.get("label", "")))

    if distinct_sources >= 3:
        candidatos.append((7, "Cluster muito forte - coberto por " + str(distinct_sources) + " fontes distintas"))

    if maior_movimento and abs(maior_movimento[1]) >= LIMIAR_MOVIMENTO_FORTE:
        candidatos.append((6, "Movimento relevante: " + maior_movimento[0] + " " + _formata_variacao(maior_movimento[1])))
    if tem_entidade_alto_impacto and distinct_sources >= 2:
        candidatos.append((6, "Ativo ganhando atenção, com cobertura consistente"))

    if not candidatos and top_cluster:
        candidatos.append((2, "Sinal fraco - sem substância suficiente para virar conteúdo"))

    if not candidatos:
        return 0, "", None

    candidatos.sort(key=lambda par: par[0], reverse=True)
    nivel, motivo = candidatos[0]

    assunto = None
    if top_cluster:
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
    if assunto is None and maior_movimento:
        nome, variacao = maior_movimento
        assunto = {
            "titulo": nome + " " + _formata_variacao(variacao),
            "contexto": nome + " teve variação de " + _formata_variacao(variacao) + " no dia.",
        }

    return nivel, motivo, assunto


def validar_potencial_conteudo_ia(assunto, motivo):
    """Segunda camada de validacao do Breaking - so roda quando o
    nivel ja passou do limiar. Pergunta pra IA se o assunto realmente
    gera conteudo educativo/interessante de verdade - nao so 'e
    relevante pro mercado'. Fallback seguro: em caso de falha da IA,
    permite a geracao (nao trava o fluxo por indisponibilidade da IA)."""
    if not USE_AI:
        return True
    try:
        prompt = (
            "Voce e o editor de conteudo do canal 'Antes do Sino'. Responda a "
            "pergunta: \"Isso realmente gera um conteudo educativo ou interessante "
            "para um investidor?\"\n\n"
            "Avalie especificamente:\n"
            "- Existe curiosidade real nesse assunto?\n"
            "- Existe aprendizado concreto para quem le?\n"
            "- Existe consequencia pratica para o investidor?\n"
            "- Existe contexto suficiente para explicar (nao so um fato solto)?\n"
            "- Existe potencial de engajamento (alguem salvaria ou compartilharia)?\n\n"
            "Se a resposta for negativa pra maioria desses pontos, responda false - "
            "prefira descartar a publicar algo fraco.\n\n"
            "ASSUNTO: " + assunto["titulo"] + "\n"
            "CONTEXTO: " + assunto["contexto"] + "\n"
            "SINAL QUE LEVOU A ESSA AVALIACAO: " + motivo + "\n\n"
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
        return False, "Nível abaixo do limiar (" + str(score) + "/" + str(LIMIAR_BREAKING) + ")"
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
    """Breaking continua OPORTUNISTA - so gera quando o nivel de
    conteudo (hierarquia exclusiva, nao soma) ultrapassa o limiar E
    passa pela segunda validacao da IA. Publicar menos e melhor que
    publicar conteudo generico."""
    nivel, motivo, assunto = calcular_score_conteudo(clusters, market_snapshot, events)
    breaking_state = _limpar_estado_breaking_se_novo_dia(load_breaking_state())

    deve_gerar, motivo_decisao = should_generate_breaking_content(nivel, assunto, breaking_state)
    if not deve_gerar:
        return None

    if not validar_potencial_conteudo_ia(assunto, motivo):
        print("Social Content Engine (Breaking): IA avaliou que o assunto não gera conteúdo educativo real - descartado mesmo com nível " + str(nivel) + ".")
        return None

    conteudo = gerar_conteudo_unificado(assunto, entries_today, "breaking")

    item = _montar_item(conteudo, "breaking", nivel, [motivo])

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
    """So dispara em dia util da B3 (nao fim de semana nem feriado)."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_opening_state()
    if state.get("last_opening_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return OPENING_JANELA_INICIO_MINUTOS <= minutes <= OPENING_JANELA_FIM_MINUTOS


def avaliar_opening_content(entries_today, clusters, market_insights, market_snapshot, events):
    """Opening e EDITORIAL OBRIGATORIO - nunca depende de 'ter uma boa
    noticia'. Nao usa mais escolher_assunto_principal - sempre gera,
    usando os dados reais de mercado/agenda disponiveis no momento."""
    if not should_generate_opening_content():
        return None

    dados = montar_dados_opening(market_snapshot, events)
    conteudo = gerar_conteudo_opening(dados, entries_today)

    reason = ["Conteúdo editorial obrigatório (Opening) - preparação para o pregão"]
    item = _montar_item(conteudo, "opening", None, reason)

    state = load_opening_state()
    state["last_opening_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_opening_state(state)

    return item


# ---------------------------------------------------------------------------
# MODO: MIDDAY (12h00-12h15) - mesma maquina de estados, sem IA
# ---------------------------------------------------------------------------

def should_generate_midday_content():
    """So dispara em dia util da B3 (nao fim de semana nem feriado)."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_midday_state()
    if state.get("last_midday_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return MIDDAY_JANELA_INICIO_MINUTOS <= minutes <= MIDDAY_JANELA_FIM_MINUTOS


def montar_dados_midday_editorial(market_snapshot, clusters, entries_today):
    """Coleta pura (sem IA) dos dados do Midday editorial - numeros ja
    coletados + ate 3 acontecimentos da manha, reaproveitando
    compute_news_clusters() ja calculado no main.py (zero chamada
    nova de processamento). Nao inventa acontecimento - se nao
    houver cluster, a lista fica vazia e o prompt trata isso."""
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

    acontecimentos = []
    for cluster in (clusters or [])[:3]:
        rep = cluster.get("representative", {})
        titulo = rep.get("title", "")
        if titulo:
            acontecimentos.append(titulo)

    return {"numeros": linhas, "acontecimentos": acontecimentos}


def gerar_conteudo_midday_editorial(dados, entries_today):
    """Midday passa a ter 1 chamada de IA por dia (unica excecao ao
    'sem IA' original) - sintetiza a manha como resumo editorial de
    verdade, nao so numero cru. Se a IA falhar, cai no fallback por
    template (gerar_conteudo_midday_unificado), que continua existindo
    intacto."""
    numeros_texto = "\n".join(dados["numeros"]) if dados["numeros"] else "(nenhum dado de mercado disponivel)"
    acontecimentos_texto = "\n".join(dados["acontecimentos"]) if dados["acontecimentos"] else "(nenhum acontecimento de destaque ate o momento)"

    prompt = (
        "Voce e o editor de mercado do canal 'Antes do Sino'. Use SOMENTE os "
        "dados abaixo - nunca invente numero ou fato. Nunca de opiniao de "
        "investimento.\n\n"
        + TEXTO_ANALISE_EDITORIAL_PROMPT + "\n\n"
        "NUMEROS DO MERCADO ATE O MEIO-DIA:\n" + numeros_texto + "\n\n"
        "PRINCIPAIS ACONTECIMENTOS DA MANHA (ate 3):\n" + acontecimentos_texto + "\n\n"
        "Este e o RESUMO DO MEIO-DIA - responda 'o que aconteceu ate agora?'. "
        "Gere a analise editorial, headline + instagram + x + tiktok, usando "
        "esta estrutura no campo instagram:\n"
        "   hook: o que aconteceu ate agora, resumo curto\n"
        "   context: os principais acontecimentos da manha (baseado SOMENTE na "
        "lista fornecida - se vazia, deixe vazio)\n"
        "   why_it_matters: como o mercado reagiu, com base nos numeros "
        "fornecidos\n"
        "   impact: deixe vazio, a menos que haja fato concreto de impacto em "
        "ativo especifico\n"
        "   watch_next: o que observar ate o fechamento (baseado em fato "
        "concreto - se nao houver, deixe vazio)\n"
        "   cta: encerramento discreto convidando a acompanhar o Antes do Sino\n\n"
        "instagram_caption: LEGENDA do post do Instagram - texto SEPARADO do que "
        "fica dentro da imagem. Curto (2-4 frases), retomando a historia principal "
        "e terminando com convite discreto pra acompanhar o Antes do Sino.\n\n"
        "x: post curto para X/Twitter, MAXIMO 280 caracteres.\n"
        "tiktok: roteiro falado de ate 45 segundos, em cenas.\n\n"
        + TEXTO_FRASES_PROIBIDAS_PROMPT + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"editorial": {"tipo_noticia": "...", "historia_principal": "..."}, '
        '"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "...", "cta": "..."}, '
        '"instagram_caption": "...", '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )

    try:
        raw_response = ask_groq_isolado(prompt, purpose="generation")
        parsed = extract_json_object_isolado(raw_response)
        conteudo = validar_conteudo_unificado(parsed)
        if conteudo is not None:
            return conteudo
        print("Midday: resposta da IA invalida - usando fallback por template (sem IA).")
    except Exception as e:
        print("Erro ao gerar conteudo editorial do Midday (usando fallback por template): " + str(e))

    return None  # sinaliza para avaliar_midday_snapshot cair no template determinístico


def avaliar_midday_snapshot(market_snapshot, clusters=None, entries_today=None):
    if not should_generate_midday_content():
        return None

    dados = montar_dados_midday_editorial(market_snapshot, clusters, entries_today)
    conteudo = gerar_conteudo_midday_editorial(dados, entries_today)

    reason = ["Resumo editorial de meio de pregão programado (12h00)"]
    usou_fallback_sem_ia = False
    if not conteudo:
        # Fallback determinístico - o Midday original, sem IA, nunca
        # deixa de gerar por falha da chamada nova.
        conteudo = gerar_conteudo_midday_unificado(market_snapshot)
        if conteudo is None:
            print("Social Content Engine (Midday): sem dados de mercado disponíveis - nada gerado.")
            return None
        reason = ["Snapshot de meio de pregão programado (12h00) - fallback sem IA"]
        usou_fallback_sem_ia = True

    item = _montar_item(conteudo, "midday", None, reason)
    if usou_fallback_sem_ia:
        item["prompt_version"] = "midday-template-" + PROMPT_VERSION

    state = load_midday_state()
    state["last_midday_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_midday_state(state)

    return item


# ---------------------------------------------------------------------------
# MODO: CLOSING (18h30-19h00)
# ---------------------------------------------------------------------------

def should_generate_closing_content():
    """So dispara em dia util da B3 (nao fim de semana nem feriado)."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_social_content_state()
    if state.get("last_social_content_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return CLOSING_JANELA_INICIO_MINUTOS <= minutes <= CLOSING_JANELA_FIM_MINUTOS


def avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events):
    """Closing e EDITORIAL OBRIGATORIO - responde 'como foi o pregao?'
    mesmo sem grande noticia. Nao usa mais escolher_assunto_principal."""
    if not should_generate_closing_content():
        return None

    dados = montar_dados_closing(market_snapshot, clusters, events)
    conteudo = gerar_conteudo_closing(dados, entries_today)

    reason = ["Conteúdo editorial obrigatório (Closing) - fechamento do pregão"]
    if dados["fato_principal"]:
        reason.append("Fato principal identificado por cluster de notícia")
    item = _montar_item(conteudo, "closing", None, reason)

    state = load_social_content_state()
    state["last_social_content_date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    save_social_content_state(state)

    return item


# ---------------------------------------------------------------------------
# Montagem do item - centraliza os campos comuns a QUALQUER modo
# ---------------------------------------------------------------------------

def _registrar_transicao(item, novo_status, detalhe=""):
    """Registra toda mudanca de estado no proprio item - historico
    completo, nunca perde rastro de por onde o conteudo passou."""
    item["status"] = novo_status
    historico = item.setdefault("history", [])
    historico.append({
        "status": novo_status,
        "at": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "detalhe": detalhe,
    })
    return item


def _montar_item(conteudo, content_mode, score, reason):
    item = {
        "id": gerar_id_unico(),
        "content_mode": content_mode,
        "content_template": TEMPLATE_MAP.get(content_mode, "quick_insight"),
        "headline": conteudo["headline"],
        "instagram": conteudo["instagram"],
        "instagram_caption": conteudo.get("instagram_caption", ""),
        "hashtags": conteudo.get("hashtags", _gerar_hashtags("Outro")),
        "x": conteudo["x"],
        "tiktok": conteudo["tiktok"],
        "editorial": conteudo.get("editorial", {"tipo_noticia": "Outro", "historia_principal": ""}),
        "score": score,
        "reason": reason,
        "priority": _prioridade_por_modo(content_mode),
        "expires_at": _calcular_expiracao(content_mode).strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_version": PROMPT_VERSION,
        "status": "draft",
        "expired_notice_sent": False,
        # Plataforma de destino - inicialmente so X esta implementado.
        # Fica pronto pra virar lista quando Instagram/TikTok existirem.
        "platform": "x",
        "publish_url": None,
        "publish_error": None,
        "history": [],
    }
    _registrar_transicao(item, "draft", "Conteúdo gerado")
    return item


# ---------------------------------------------------------------------------
# Persistencia - fila acumulativa, nunca sobrescreve
# ---------------------------------------------------------------------------

def load_social_queue():
    data = _load_json_seguro(SOCIAL_QUEUE_FILE, [])
    return data if isinstance(data, list) else []


def save_social_queue_full(fila):
    _save_json(SOCIAL_QUEUE_FILE, fila)


PUBLISHED_POSTS_FILE = "docs/published_posts.json"


def registrar_published_post(item, resultado):
    """Historico separado de tentativas de publicacao (sucesso ou
    falha) - independente da fila principal, preparado para migrar
    para banco no futuro sem afetar o social_queue.json."""
    historico = _load_json_seguro(PUBLISHED_POSTS_FILE, [])
    if not isinstance(historico, list):
        historico = []
    historico.append({
        "id": item.get("id"),
        "platform": item.get("platform", "x"),
        "at": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "status": item.get("status"),
        "url": resultado.get("url"),
        "error": resultado.get("error"),
    })
    _save_json(PUBLISHED_POSTS_FILE, historico)


def _find_item_index_by_id(fila, item_id):
    for i, item in enumerate(fila):
        if item.get("id") == item_id:
            return i
    return None


def enfileirar_item(item):
    """Acumula historico - nunca sobrescreve. Adiciona date/metrics e
    ja tenta gerar a arte IMEDIATAMENTE (antes da aprovacao) - assim a
    notificacao de draft ja chega com a imagem, e a aprovacao vira
    quase instantanea (nao precisa esperar o proximo ciclo desenhar).

    Se a geracao de arte falhar por qualquer motivo, cai com seguranca
    para o fluxo antigo (notificacao so com texto, arte gerada depois
    da aprovacao, via process_pending_designs) - nunca perde o
    conteudo por causa disso."""
    if item is None:
        return

    fila = load_social_queue()

    novo_item = dict(item)
    novo_item["date"] = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    novo_item["metrics"] = {"views": None, "likes": None, "shares": None, "comments": None}

    print(
        "Social Content Engine: item " + novo_item["id"] + " criado (modo=" + novo_item["content_mode"]
        + ", status=draft, template=" + novo_item["content_template"] + ")"
    )

    pasta_arte = None
    tipo_ativo = None
    quantidade_slides = None
    try:
        from social import design_engine
        pasta_arte, quantidade_slides, tipo_ativo = design_engine.gerar_ativo_visual(novo_item)
        novo_item["design_folder"] = pasta_arte
        novo_item["design_pregerado"] = True
        print("Social Content Engine: arte pre-gerada junto com o draft (" + tipo_ativo + ", " + str(quantidade_slides) + " imagem(ns)).")
    except Exception as e:
        print("Aviso: falha ao pre-gerar arte no momento do draft (cai no fluxo antigo, gera depois da aprovacao): " + str(e))

    fila.append(novo_item)
    save_social_queue_full(fila)

    if pasta_arte:
        notificar_draft_com_arte(novo_item, pasta_arte, quantidade_slides, tipo_ativo)
    else:
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


def _enviar_telegram_admin_com_botoes(texto, botoes):
    """Envia mensagem com teclado de RESPOSTA (reply keyboard, nao
    inline) - ao clicar, o Telegram manda o texto do botao como se
    voce tivesse digitado e enviado, aparecendo visivel na conversa.
    Reaproveita 100% a logica de texto que ja existe pro comando
    manual - nenhum parser novo necessario. 'botoes' e uma lista de
    rotulos (o rotulo JA E o comando completo, ex: 'Aprovar <ID>')."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Content Engine: TELEGRAM_ADMIN_CHAT_ID não configurado - aviso privado não enviado.")
        return
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        linhas_botoes = [botoes[i:i + 2] for i in range(0, len(botoes), 2)]
        teclado = {
            "keyboard": [[{"text": rotulo} for rotulo in linha] for linha in linhas_botoes],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
        payload = {
            "chat_id": TELEGRAM_ADMIN_CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "reply_markup": teclado,
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificação privada com botão (isolado, item já está salvo): " + str(e))


def _enviar_telegram_admin_foto(caminho_imagem, legenda):
    """Envia uma foto (ex: preview do carrossel/card) com legenda para
    o chat privado do admin. Se o arquivo nao existir ou o envio
    falhar, cai com seguranca para uma mensagem de texto simples -
    nunca perde o aviso so porque a imagem nao pode ser enviada."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Content Engine: TELEGRAM_ADMIN_CHAT_ID não configurado - aviso privado não enviado.")
        return
    try:
        if not caminho_imagem or not os.path.exists(caminho_imagem):
            print("Social Content Engine: imagem de preview não encontrada (" + str(caminho_imagem) + ") - enviando só texto.")
            _enviar_telegram_admin(legenda)
            return
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
        with open(caminho_imagem, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "caption": legenda, "parse_mode": "HTML"}
            requests.post(url, data=data, files=files, timeout=20)
    except Exception as e:
        print("Erro ao enviar foto de preview (caindo para texto simples): " + str(e))
        _enviar_telegram_admin(legenda)


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
    )

    botoes = [
        "Aprovar " + item["id"],
        "Editar " + item["id"],
        "Regenerar " + item["id"],
        "Rejeitar " + item["id"],
    ]
    _enviar_telegram_admin_com_botoes(texto, botoes)


def notificar_draft_com_arte(item, pasta, quantidade_slides, tipo_ativo):
    """Notificacao de draft FUNDIDA com a arte ja pre-gerada - voce ja
    ve a imagem antes de decidir aprovar/rejeitar. Limitacao real do
    Telegram: album (varias fotos) NAO aceita teclado anexado - nesse
    caso, manda as imagens e o teclado vem numa mensagem curta logo
    depois. Foto unica aceita teclado direto na mesma mensagem."""
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
        + "\n\nFormato: " + str(tipo_ativo) + " (" + str(quantidade_slides) + " imagem(ns))"
    )

    botoes = ["Aprovar " + item["id"], "Editar " + item["id"], "Regenerar " + item["id"], "Rejeitar " + item["id"]]

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Content Engine: TELEGRAM_ADMIN_CHAT_ID não configurado - aviso privado não enviado.")
        return

    caminhos_slides = sorted(
        os.path.join(pasta, f) for f in os.listdir(pasta)
        if f.startswith("slide_") and f.endswith(".png")
    ) if pasta and os.path.isdir(pasta) else []

    try:
        if len(caminhos_slides) == 1:
            # Foto unica aceita teclado direto na mesma mensagem.
            url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
            linhas_botoes = [botoes[i:i + 2] for i in range(0, len(botoes), 2)]
            teclado = {"keyboard": [[{"text": r} for r in linha] for linha in linhas_botoes], "resize_keyboard": True, "one_time_keyboard": True}
            with open(caminhos_slides[0], "rb") as f:
                files = {"photo": f}
                data = {
                    "chat_id": TELEGRAM_ADMIN_CHAT_ID,
                    "caption": texto,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(teclado),
                }
                requests.post(url, data=data, files=files, timeout=20)
        elif len(caminhos_slides) >= 2:
            # Album nao aceita teclado - manda as imagens, depois o
            # teclado numa mensagem curta separada.
            _enviar_album_telegram_content(caminhos_slides, texto)
            _enviar_telegram_admin_com_botoes("👆 O que fazer com o conteúdo acima?", botoes)
        else:
            # Sem imagem nenhuma (pasta vazia/erro) - cai no texto puro.
            notificar_draft(item)
    except Exception as e:
        print("Erro ao enviar draft com arte (caindo para notificação só de texto): " + str(e))
        notificar_draft(item)


def _enviar_album_telegram_content(caminhos_imagens, legenda):
    """Duplicada de proposito (isolamento do design_engine.py) - envia
    varias imagens juntas via sendMediaGroup, legenda na primeira."""
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMediaGroup"
    media = []
    files = {}
    for i, caminho in enumerate(caminhos_imagens[:10]):
        chave_arquivo = "foto" + str(i)
        item_media = {"type": "photo", "media": "attach://" + chave_arquivo}
        if i == 0:
            item_media["caption"] = legenda
            item_media["parse_mode"] = "HTML"
        media.append(item_media)
        files[chave_arquivo] = open(caminho, "rb")
    try:
        data = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "media": json.dumps(media)}
        requests.post(url, data=data, files=files, timeout=30)
    finally:
        for f in files.values():
            f.close()


def notificar_expirado(item):
    texto = (
        "⚠️ <b>Esse conteúdo perdeu o timing</b>\n\n"
        "Modo: " + item["content_mode"] + "\n"
        "Assunto: " + item["headline"] + "\n"
        "ID: <code>" + item["id"] + "</code>\n\n"
        "Ainda está como draft e já passou da validade esperada para esse tipo de conteúdo."
    )
    _enviar_telegram_admin(texto)


def _gerar_e_entregar_video_tiktok(item):
    """Gera o video vertical do TikTok a partir dos MESMOS slides ja
    desenhados, e entrega no Telegram (video + legenda+hashtags+CTA
    prontos pra copiar, em mensagens separadas). Isolado com try/except
    proprio - falha aqui NUNCA bloqueia a entrega do Instagram/X, que
    ja aconteceu antes."""
    pasta = item.get("design_folder")
    if not pasta or not os.path.isdir(pasta):
        return False

    try:
        from social import video_engine
        if not video_engine.ffmpeg_disponivel():
            print("TikTok Video Engine: FFmpeg indisponível no ambiente - vídeo não gerado.")
            return False

        caminhos_slides = sorted(
            os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.startswith("slide_") and f.endswith(".png")
        )
        if not caminhos_slides:
            return False

        tk = item.get("tiktok", {}) or {}
        cta = tk.get("cta", "")

        caminho_video = video_engine.gerar_video_tiktok(caminhos_slides, pasta, cta_texto=cta)

        valido, info = video_engine.validar_video(caminho_video)
        if not valido:
            raise RuntimeError("vídeo gerado, mas validação falhou: " + str(info))

        cenas = tk.get("scenes", [])
        legenda_partes = [cena["line"] for cena in cenas if cena.get("line")]
        legenda_completa = " ".join(legenda_partes) or item.get("headline", "")
        if cta:
            legenda_completa += "\n\n" + cta

        hashtags = item.get("hashtags", [])
        if hashtags:
            legenda_completa += "\n\n" + " ".join(hashtags)

        if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID:
            url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendVideo"
            with open(caminho_video, "rb") as f:
                files = {"video": f}
                data = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "caption": "🎥 Vídeo TikTok pronto"}
                requests.post(url, data=data, files=files, timeout=60)

            _enviar_telegram_admin("📝 <b>Legenda TikTok</b>\n\n" + legenda_completa)

        print("Social Content Engine: vídeo TikTok gerado e entregue para o item " + item.get("id", "") + " (duração: " + str(round(info, 1)) + "s).")
        return True
    except Exception as e:
        print("Erro ao gerar/entregar vídeo TikTok (isolado, não afeta Instagram/X): " + str(e))
        return False


def _entregar_pacote_completo_aprovacao(item):
    """Entrega TODOS os materiais no Telegram, na ordem exata:
    1) confirmacao, 2) Instagram (carrossel/card), 3) texto do X,
    4) imagem do X, 5) video TikTok, 6) legenda+hashtags+CTA.
    Cada etapa e isolada - falha em uma NUNCA impede as seguintes."""
    pasta = item.get("design_folder")
    item_id = item.get("id", "")

    # 1) Confirmacao
    try:
        _enviar_telegram_admin(
            "✅ <b>Conteúdo aprovado</b>\n\n"
            "Assunto: " + item.get("headline", "") + "\n"
            "ID: <code>" + item_id + "</code>"
        )
    except Exception as e:
        print("Erro ao enviar confirmação de aprovação (isolado): " + str(e))

    caminhos_slides = []
    if pasta and os.path.isdir(pasta):
        caminhos_slides = sorted(
            os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.startswith("slide_") and f.endswith(".png")
        )

    # 2) Instagram - carrossel completo ou card unico
    try:
        if len(caminhos_slides) >= 2:
            _enviar_album_telegram_content(caminhos_slides, "📸 <b>Instagram (carrossel)</b>")
        elif len(caminhos_slides) == 1:
            _enviar_telegram_admin_foto(caminhos_slides[0], "📸 <b>Instagram (card)</b>")
        else:
            print("Aviso: nenhum slide encontrado para entrega do Instagram (item " + item_id + ").")
    except Exception as e:
        print("Erro ao entregar Instagram (isolado, não afeta X/TikTok): " + str(e))

    # 3) Texto do X
    try:
        texto_x = (item.get("x") or {}).get("post", "")
        if texto_x:
            _enviar_telegram_admin("🐦 <b>Texto para o X</b>\n\n" + texto_x)
    except Exception as e:
        print("Erro ao entregar texto do X (isolado): " + str(e))

    # 4) Imagem correspondente do X (reaproveita a capa/card - X usa imagem unica)
    try:
        if caminhos_slides:
            _enviar_telegram_admin_foto(caminhos_slides[0], "🖼️ <b>Imagem para o X</b>")
    except Exception as e:
        print("Erro ao entregar imagem do X (isolado): " + str(e))

    # 5) e 6) Video do TikTok + legenda/hashtags/CTA (isolado, ja trata sua propria excecao)
    _gerar_e_entregar_video_tiktok(item)

    # Fecha o ciclo - botao pra confirmar publicacao manual
    try:
        _enviar_telegram_admin_com_botoes(
            "Depois de publicar manualmente, toque no botão\n"
            "(ou responda \"Publicado " + item_id + " <link>\" se quiser guardar o link do post).",
            ["Publicado " + item_id]
        )
    except Exception as e:
        print("Erro ao enviar botão de confirmação de publicação (isolado): " + str(e))


def notificar_publicado(item):
    texto = (
        "✅ <b>Publicado no " + (item.get("platform") or "x").upper() + "</b>\n"
        "Assunto: " + item["headline"] + "\n"
    )
    if item.get("publish_url"):
        texto += "Link:\n" + item["publish_url"]
    _enviar_telegram_admin(texto)


# ---------------------------------------------------------------------------
# Aprovacao por resposta de texto - consulta getUpdates, sem botao
# ---------------------------------------------------------------------------

def _reconstruir_assunto_do_item(item):
    """Reconstroi um 'assunto' (titulo+contexto) a partir do proprio
    conteudo ja gerado - usado por Regenerar/Editar, que nao tem mais
    acesso aos dados brutos originais (cluster/snapshot) usados na
    primeira geracao. E uma aproximacao deliberada: o resultado usa o
    conteudo atual como contexto, nao os dados crus originais - mantem
    o mesmo assunto geral, mas nao reproduz 100% fielmente a fonte
    primaria da geracao inicial."""
    ig = item.get("instagram", {}) or {}
    partes_contexto = [ig.get("context", ""), ig.get("why_it_matters", ""), ig.get("impact", "")]
    contexto = " ".join(p for p in partes_contexto if p).strip() or item.get("headline", "")
    return {"titulo": item.get("headline", ""), "contexto": contexto}


def regenerar_conteudo_item(item):
    """Gera uma NOVA abordagem para o mesmo assunto - substitui
    headline/instagram/instagram_caption/x/tiktok/editorial mantendo
    o mesmo ID, content_mode, score e reason originais."""
    assunto = _reconstruir_assunto_do_item(item)
    novo_conteudo = gerar_conteudo_unificado(assunto, [], item.get("content_mode", "breaking"))

    item["headline"] = novo_conteudo["headline"]
    item["instagram"] = novo_conteudo["instagram"]
    item["instagram_caption"] = novo_conteudo.get("instagram_caption", "")
    item["hashtags"] = novo_conteudo.get("hashtags", item.get("hashtags", []))
    item["x"] = novo_conteudo["x"]
    item["tiktok"] = novo_conteudo["tiktok"]
    item["editorial"] = novo_conteudo.get("editorial", item.get("editorial", {}))
    return item


def editar_conteudo_item(item, instrucao_usuario):
    """Aplica uma edicao pontual pedida em texto livre pelo usuario,
    mantendo o restante do conteudo o mais fiel possivel ao original."""
    prompt = (
        "Voce e o editor de mercado do canal 'Antes do Sino'. Este conteudo JA FOI "
        "GERADO e precisa de uma edicao pontual pedida pelo usuario. Aplique "
        "EXATAMENTE a edicao solicitada, mantendo o resto do conteudo o mais fiel "
        "possivel ao original - nao reescreva o que nao foi pedido para mudar. "
        "Nunca invente dado novo que nao esteja no conteudo atual ou na instrucao.\n\n"
        "CONTEUDO ATUAL:\n"
        "Headline: " + item.get("headline", "") + "\n"
        "Instagram hook: " + item.get("instagram", {}).get("hook", "") + "\n"
        "Instagram context: " + item.get("instagram", {}).get("context", "") + "\n"
        "Instagram why_it_matters: " + item.get("instagram", {}).get("why_it_matters", "") + "\n"
        "Instagram impact: " + item.get("instagram", {}).get("impact", "") + "\n"
        "Instagram watch_next: " + item.get("instagram", {}).get("watch_next", "") + "\n"
        "X post: " + item.get("x", {}).get("post", "") + "\n\n"
        "INSTRUCAO DE EDICAO DO USUARIO:\n\"" + instrucao_usuario + "\"\n\n"
        + TEXTO_FRASES_PROIBIDAS_PROMPT + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"editorial": {"tipo_noticia": "...", "historia_principal": "..."}, '
        '"headline": "...", '
        '"instagram": {"hook": "...", "context": "...", "why_it_matters": "...", '
        '"impact": "...", "watch_next": "...", "cta": "..."}, '
        '"instagram_caption": "...", '
        '"x": {"post": "..."}, '
        '"tiktok": {"scenes": [{"visual": "...", "line": "..."}], "cta": "..."}}'
    )

    try:
        raw_response = ask_groq_isolado(prompt, purpose="generation")
        parsed = extract_json_object_isolado(raw_response)
        novo_conteudo = validar_conteudo_unificado(parsed)
        if novo_conteudo is None:
            raise ValueError("resposta da IA invalida")
    except Exception as e:
        print("Erro ao editar conteudo (mantendo original sem alteracao): " + str(e))
        return item

    item["headline"] = novo_conteudo["headline"]
    item["instagram"] = novo_conteudo["instagram"]
    item["instagram_caption"] = novo_conteudo.get("instagram_caption", "")
    item["hashtags"] = novo_conteudo.get("hashtags", item.get("hashtags", []))
    item["x"] = novo_conteudo["x"]
    item["tiktok"] = novo_conteudo["tiktok"]
    item["editorial"] = novo_conteudo.get("editorial", item.get("editorial", {}))
    return item


# ---------------------------------------------------------------------------
# Estado de edicao pendente - "Editar <ID>" pede a instrucao, a
# PROXIMA mensagem de texto livre (sem comando reconhecido) e tratada
# como a instrucao de edicao daquele item especifico.
# ---------------------------------------------------------------------------

PENDING_EDIT_STATE_FILE = "docs/pending_edit_state.json"


def load_pending_edit_state():
    return _load_json_seguro(PENDING_EDIT_STATE_FILE, {"item_id": None})


def save_pending_edit_state(state):
    _save_json(PENDING_EDIT_STATE_FILE, state)


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

        # Comando de confirmacao MANUAL - usado quando a publicacao
        # automatica esta desligada (sem credencial paga configurada).
        # Fecha o ciclo de estado sem chamar nenhuma API externa.
        match_manual = re.match(r"(?i)^\s*publicado\s+(\S+)(?:\s+(\S+))?\s*$", texto)
        if match_manual:
            item_id = match_manual.group(1).strip()
            link_informado = (match_manual.group(2) or "").strip() or None

            indice = _find_item_index_by_id(fila, item_id)
            if indice is None:
                _enviar_telegram_admin("Não encontrei nenhum conteúdo com o ID <code>" + item_id + "</code>.")
                continue

            item = fila[indice]
            if item.get("status") not in ("designed", "failed"):
                _enviar_telegram_admin(
                    "O item <code>" + item_id + "</code> está com status \"" + str(item.get("status"))
                    + "\" - só é possível confirmar publicação de itens \"designed\" ou \"failed\"."
                )
                continue

            item["publish_url"] = link_informado
            item["publish_error"] = None
            _registrar_transicao(item, "published", "Publicado manualmente via Telegram")
            fila[indice] = item
            fila_alterada = True
            print("Social Content Engine: item " + item_id + " confirmado como publicado manualmente.")
            save_social_queue_full(fila)
            registrar_published_post(item, {"success": True, "url": link_informado, "error": None})
            notificar_publicado(item)
            continue

        match = re.match(r"(?i)^\s*(aprovar|rejeitar|editar|regenerar)\s+(\S+)\s*$", texto)
        if not match:
            # Nao bateu com nenhum comando reconhecido - se houver uma
            # edicao pendente, trata essa mensagem como a instrucao de
            # edicao daquele item. Caso contrario, ignora (nao e um
            # comando valido).
            pendente = load_pending_edit_state()
            item_id_pendente = pendente.get("item_id")
            if item_id_pendente and texto.strip():
                indice_pendente = _find_item_index_by_id(fila, item_id_pendente)
                if indice_pendente is not None:
                    item_pendente = fila[indice_pendente]
                    item_pendente = editar_conteudo_item(item_pendente, texto.strip())
                    fila[indice_pendente] = item_pendente
                    fila_alterada = True
                    save_social_queue_full(fila)
                    save_pending_edit_state({"item_id": None})
                    print("Social Content Engine: item " + item_id_pendente + " editado via instrução livre no Telegram.")

                    pasta_existente = item_pendente.get("design_folder")
                    if pasta_existente:
                        try:
                            from social import design_engine
                            nova_pasta, qtd, tipo = design_engine.gerar_ativo_visual(item_pendente)
                            item_pendente["design_folder"] = nova_pasta
                            fila[indice_pendente] = item_pendente
                            save_social_queue_full(fila)
                            notificar_draft_com_arte(item_pendente, nova_pasta, qtd, tipo)
                        except Exception as e:
                            print("Erro ao regenerar arte após edição (enviando só texto): " + str(e))
                            notificar_draft(item_pendente)
                    else:
                        notificar_draft(item_pendente)
            continue

        acao = match.group(1).lower()
        item_id = match.group(2).strip()

        indice = _find_item_index_by_id(fila, item_id)
        if indice is None:
            _enviar_telegram_admin("Não encontrei nenhum conteúdo com o ID <code>" + item_id + "</code>.")
            continue

        item = fila[indice]

        if acao == "editar":
            if item.get("status") not in ("draft",):
                _enviar_telegram_admin("Só é possível editar conteúdo em \"draft\". Status atual: " + str(item.get("status")))
                continue
            save_pending_edit_state({"item_id": item_id})
            _enviar_telegram_admin("✏️ Envie as alterações desejadas para o conteúdo <code>" + item_id + "</code>.")
            continue

        if acao == "regenerar":
            if item.get("status") not in ("draft",):
                _enviar_telegram_admin("Só é possível regenerar conteúdo em \"draft\". Status atual: " + str(item.get("status")))
                continue
            item = regenerar_conteudo_item(item)
            fila[indice] = item
            fila_alterada = True
            save_social_queue_full(fila)
            print("Social Content Engine: item " + item_id + " regenerado via Telegram.")

            pasta_existente = item.get("design_folder")
            try:
                from social import design_engine
                nova_pasta, qtd, tipo = design_engine.gerar_ativo_visual(item)
                item["design_folder"] = nova_pasta
                fila[indice] = item
                save_social_queue_full(fila)
                notificar_draft_com_arte(item, nova_pasta, qtd, tipo)
            except Exception as e:
                print("Erro ao gerar arte após regenerar (enviando só texto): " + str(e))
                notificar_draft(item)
            continue

        if item.get("status") != "draft":
            continue

        novo_status = "approved" if acao == "aprovar" else "rejected"
        _registrar_transicao(item, novo_status, "Via Telegram")

        if novo_status == "approved" and item.get("design_pregerado") and item.get("design_folder"):
            # Arte ja foi gerada junto com o draft - pula reto pra
            # 'designed', sem esperar o design engine rodar de novo.
            # Aprovacao vira instantanea dentro do mesmo ciclo.
            _registrar_transicao(item, "designed", "Arte pré-gerada no momento do draft - aprovação instantânea")
            fila[indice] = item
            fila_alterada = True
            save_social_queue_full(fila)
            print("Social Content Engine: item " + item_id + " aprovado com arte já pronta - pulou direto para designed.")

            _entregar_pacote_completo_aprovacao(item)
            continue

        fila[indice] = item
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
        avaliar_midday_snapshot(market_snapshot, clusters, entries_today),
        avaliar_closing_content(entries_today, clusters, market_insights, market_snapshot, events),
    ]:
        if item:
            enfileirar_item(item)
