import feedparser
import requests
import json
import os
import time
import hashlib
import re
import difflib
import html as html_module
import unicodedata
from datetime import datetime, timezone, timedelta

try:
    import editorial_foundation
except Exception as e:
    print("AVISO: editorial_foundation nao pode ser importado (" + str(e) + ") - modo sombra desativado neste ciclo, fluxo de publicacao real nao e afetado.")
    editorial_foundation = None

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")

COCKPIT_TICKERS = ["^BVSP", "PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "WEGE3", "B3SA3", "BBAS3", "MGLU3"]

TICKER_MENTION_LIST = [
    "petr4", "petr3", "vale3", "itub4", "bbdc4", "bbas3", "wege3",
    "mglu3", "abev3", "b3sa3", "azul4", "gol", "embr3", "hapv3",
    "petrobras", "vale", "itau", "bradesco", "banco do brasil",
    "weg", "magazine luiza", "ambev", "azul", "embraer", "hapvida",
]

USE_AI = bool(GROQ_API_KEY)
STATE_FILE = "sent_items.json"

BR_TZ = timezone(timedelta(hours=-3))

# Limiares de despacho REAL por score_materialidade (Fase 2 - graduacao
# do modo sombra de editorial_foundation.py, que so registrava o que
# faria de diferente sem nunca bloquear o envio). Mesmos valores de
# editorial_foundation.LIMIAR_BREAKING/LIMIAR_ROUND, duplicados aqui de
# proposito: a decisao de despacho e critica (evita o flood do grupo) e
# nao pode depender de editorial_foundation estar importavel.
MATERIALITY_BREAKING_THRESHOLD = 8
MATERIALITY_ROUND_THRESHOLD = 4

# Mapeia termos de TICKER_MENTION_LIST (empresa ou ticker) para a
# hashtag padrao usada nas mensagens (#PETR4 em vez de #petrobras).
TICKER_HASHTAG_MAP = {
    "petr4": "PETR4", "petr3": "PETR3", "vale3": "VALE3", "itub4": "ITUB4",
    "bbdc4": "BBDC4", "bbas3": "BBAS3", "wege3": "WEGE3", "mglu3": "MGLU3",
    "abev3": "ABEV3", "b3sa3": "B3SA3", "azul4": "AZUL4", "gol": "GOLL4",
    "embr3": "EMBR3", "hapv3": "HAPV3",
    "petrobras": "PETR4", "vale": "VALE3", "itau": "ITUB4", "bradesco": "BBDC4",
    "banco do brasil": "BBAS3", "weg": "WEGE3", "magazine luiza": "MGLU3",
    "ambev": "ABEV3", "azul": "AZUL4", "embraer": "EMBR3", "hapvida": "HAPV3",
}

# Termos curtos como "gol", "vale", "weg", "azul" batiam por substring
# simples ("in") dentro de palavras sem relacao nenhuma (ex: "Goldman"
# contem "gol", "Valens" contem "vale", "Norwegian" contem "weg") -
# gerava hashtag errada no Giro do Mercado e no Breaking (bug real
# reportado). Regex com fronteira de palavra (\b) so bate o termo
# inteiro, nao como pedaco de outra palavra. Pre-compilado 1x aqui -
# roda por noticia, nao vale recompilar a cada chamada.
_TICKER_TERM_REGEX = {
    term: re.compile(r"\b" + re.escape(term) + r"\b") for term in TICKER_MENTION_LIST
}


def extract_ticker_hashtags(text):
    """Extrai hashtags de ativos citados no texto (titulo+corpo), na
    ordem em que aparecem em TICKER_MENTION_LIST, sem repetir. Quando
    nenhum ticker especifico e encontrado, tenta um pequeno conjunto de
    hashtags macro (cambio/Ibovespa/juros) - nunca inventa ticker que
    nao esta no texto. Usa fronteira de palavra (\\b), nao substring
    simples - ver comentario de _TICKER_TERM_REGEX."""
    text_lower = text.lower()
    found = []
    for term in TICKER_MENTION_LIST:
        if _TICKER_TERM_REGEX[term].search(text_lower):
            hashtag = TICKER_HASHTAG_MAP.get(term)
            if hashtag and hashtag not in found:
                found.append(hashtag)
    if not found:
        if "dólar" in text_lower or "dolar" in text_lower or "câmbio" in text_lower or "cambio" in text_lower:
            found.append("USD/BRL")
        elif "ibovespa" in text_lower:
            found.append("IBOVESPA")
        elif "selic" in text_lower or "copom" in text_lower:
            found.append("SELIC")
    return found


# Termos que indicam noticia de resultado trimestral/balanco de uma
# empresa especifica - usados como filtro barato (regex) antes de
# gastar uma chamada de IA extra em extract_earnings_details.
EARNINGS_KEYWORDS = [
    "lucro liquido", "lucro líquido", "prejuizo liquido", "prejuízo líquido",
    "resultado trimestral", "resultado do trimestre", "balanco trimestral",
    "balanço trimestral", "divulga balanco", "divulga balanço",
    "divulgou balanco", "divulgou balanço", "receita liquida",
    "receita líquida", "ebitda ajustado", "lucro acima", "lucro abaixo",
    "quarterly earnings", "quarterly results", "earnings report",
    "reported earnings", "posts earnings", "earnings beat", "earnings miss",
    "q1 results", "q2 results", "q3 results", "q4 results",
    "full-year results", "annual results",
]


def is_earnings_news(text):
    """Deteccao barata (sem IA) de noticia de resultado trimestral -
    usada como filtro previo, so vale a pena chamar extract_earnings_details
    quando bate aqui."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in EARNINGS_KEYWORDS)


def decide_dispatch_tier(score):
    """Decide o destino REAL de uma noticia ja aprovada pelos filtros de
    relevancia, com base no score_materialidade (0-10) calculado pela
    IA. Graduacao do modo sombra (Fase 1, editorial_foundation.py) para
    decisao real (Fase 2) - a peca central da correcao de flood do
    grupo (~300 msgs em poucas horas antes desta mudanca).

    Diferente de editorial_foundation.compute_shadow_decision: aqui,
    score None (IA nao rodou ou a chamada falhou) cai em 'round', nao em
    'discard' - fallback seguro, mesmo espirito ja usado no resto do
    pipeline (nunca perder noticia real so por falha tecnica passageira
    da IA).

    'breaking' (score >= 8): mensagem individual, envio imediato.
    'round' (score 4-7, ou sem score): entra na fila do Giro do
    Mercado, consolidada em 1 mensagem por hora em vez de 1 por
    noticia.
    'discard' (score < 4): nao publica."""
    if score is not None and score >= MATERIALITY_BREAKING_THRESHOLD:
        return "breaking"
    if score is None or score >= MATERIALITY_ROUND_THRESHOLD:
        return "round"
    return "discard"


def build_earnings_lines(earnings):
    """Formata o bloco estruturado de resultado trimestral (numero
    reportado / comparacao com o esperado / destaque qualitativo), no
    lugar do resumo generico - so imprime as linhas que tem conteudo
    real, nunca um campo vazio."""
    linhas = []
    if earnings.get("reportado"):
        linhas.append("• 📊 Resultado: " + html_module.escape(earnings["reportado"], quote=False))
    if earnings.get("vs_esperado"):
        linhas.append("• 🎯 Vs. esperado: " + html_module.escape(earnings["vs_esperado"], quote=False))
    if earnings.get("destaque"):
        linhas.append("• 🔍 Destaque: " + html_module.escape(earnings["destaque"], quote=False))
    return linhas


def build_breaking_message(title, resumo, motivo, sentiment, source, hashtags, earnings=None):
    """Template A - Breaking News (score >= 8): mensagem individual,
    formato fixo com hashtag de ativo, destaques em bullet e fonte.
    Quando 'earnings' vem preenchido (noticia de resultado trimestral
    de uma empresa especifica, ver maybe_extract_earnings_details), o
    bloco estruturado de resultado substitui o resumo/motivo genericos."""
    hashtag_str = " ".join("#" + h for h in hashtags)
    header = "🚨 <b>BREAKING</b>" + (" | " + hashtag_str if hashtag_str else "")

    impacto_por_sentimento = {
        "BULLISH": "sinal de alta para o papel/ativo",
        "BEARISH": "sinal de baixa para o papel/ativo",
        "NEUTRAL": "impacto ainda neutro, sem direção clara",
    }
    impacto = impacto_por_sentimento.get(sentiment, impacto_por_sentimento["NEUTRAL"])

    bullets = build_earnings_lines(earnings) if earnings else []
    if not bullets:
        if resumo:
            bullets.append("• " + html_module.escape(sanitize_message_text(resumo), quote=False))
        if motivo:
            bullets.append("• " + html_module.escape(sanitize_message_text(motivo), quote=False))
    bullets.append("• Impacto: " + impacto)

    partes = [
        header,
        "",
        html_module.escape(sanitize_message_text(title), quote=False),
        "",
        "\n".join(bullets),
    ]

    if source:
        partes.append("")
        partes.append("🔗 Fonte: " + html_module.escape(sanitize_message_text(source), quote=False))

    partes.append("⚡ Antes do Sino VIP")

    result = "\n".join(partes)
    result = sanitize_message_text(result)
    if len(result) > 3900:
        result = smart_truncate(result, 3900)
    return result


GIRO_INTERVALO_MINUTOS = 60
# Reduzido de 20 para 8: cada item agora carrega o contexto completo da
# noticia (sem corte artificial - ver GIRO_ITEM_MAX_CHARS), entao um
# numero menor de itens por mensagem mantem o Giro dentro do limite
# real do Telegram. Itens que nao couberem ficam guardados na fila pro
# proximo Giro (ver clear_round_queue em editorial_foundation.py) -
# nunca sao descartados, so adiados.
GIRO_MAX_ITENS_POR_MENSAGEM = 8
# Teto generoso por item (nao um corte "normal") - so entra em acao no
# caso raro de uma noticia com corpo excepcionalmente longo, pra 1 item
# nao consumir sozinho o espaco de todos os outros na mesma mensagem.
GIRO_ITEM_MAX_CHARS = 600


def build_giro_headline(queue_items):
    """1 frase de leitura geral pro Giro do Mercado, sintetizando o
    lote de itens 'round' da hora - da uma leitura mais estruturada ao
    digest sem transformar cada item num bloco longo (o Giro existe
    justamente pra ser compacto e evitar flood - ver GIRO_INTERVALO_MINUTOS).
    Fallback seguro: fila pequena demais ou falha na IA retornam None,
    e o Giro sai so com os bullets, como sempre foi."""
    if not USE_AI or len(queue_items) < 2:
        return None
    headlines_text = ""
    for item in queue_items[:15]:
        headlines_text += "- " + (item.get("resumo") or item.get("title") or "") + "\n"

    instrucao = (
        "Voce e o editor de um digest horario de mercado financeiro. Com base nos "
        "itens abaixo, escreva 1 frase curta (estilo manchete de research, direta, "
        "sem floreio) que resuma o tom geral desta hora do mercado. Use SOMENTE o "
        "que esta nos itens - nunca invente fato nem conecte itens sem relacao "
        "explicita entre eles. Responda so a frase, sem aspas, sem markdown.\n\n"
        "Itens:\n" + headlines_text
    )
    try:
        resposta = ask_groq(instrucao, purpose="analysis")
        limpo = sanitize_message_text(resposta.strip().strip('"'))
        return limpo or None
    except Exception as e:
        print("Erro ao gerar leitura da hora do Giro do Mercado (fallback seguro): " + str(e))
        return None


def build_giro_item_line(item):
    """Formata 1 linha do Giro do Mercado. Quando o item tem detalhes
    de resultado trimestral extraidos (ver maybe_extract_earnings_details),
    usa o numero reportado + destaque no lugar do resumo generico -
    mantendo 1 linha por item, sem inflar o digest."""
    hashtags = item.get("hashtags") or []
    prefixo = " ".join("#" + h for h in hashtags) + ": " if hashtags else ""

    earnings = item.get("earnings")
    if earnings and earnings.get("reportado"):
        texto = earnings["reportado"]
        if earnings.get("destaque"):
            texto += " — " + earnings["destaque"]
    else:
        texto = item.get("resumo") or item.get("title") or ""

    return "• " + prefixo + html_module.escape(sanitize_message_text(texto), quote=False)


def build_giro_message(queue_items):
    """Template B - Giro do Mercado: consolida os itens 'round'
    acumulados na ultima hora numa unica mensagem, com o contexto
    completo de cada noticia (sem corte artificial por item - so o
    teto de seguranca GIRO_ITEM_MAX_CHARS), com uma leitura geral da
    hora no topo (build_giro_headline). Ordena por materialidade (mais
    importante primeiro) via editorial_foundation.prioritize_queue
    quando disponivel. Retorna (mensagem, itens_incluidos) - quem
    chama usa itens_incluidos pra so remover da fila o que realmente
    foi enviado, mantendo o resto pro proximo Giro (ver
    processar_giro_do_mercado)."""
    agora = datetime.now(BR_TZ)
    inicio = (agora - timedelta(minutes=GIRO_INTERVALO_MINUTOS)).strftime("%Hh%M")
    fim = agora.strftime("%Hh%M")

    if editorial_foundation is not None:
        try:
            ordenados = editorial_foundation.prioritize_queue(queue_items)
        except Exception:
            ordenados = queue_items
    else:
        ordenados = queue_items

    mostrados = ordenados[:GIRO_MAX_ITENS_POR_MENSAGEM]
    restantes = len(ordenados) - len(mostrados)

    linhas = [build_giro_item_line(item) for item in mostrados]
    corpo = "\n".join(linhas) if linhas else "Sem novidades relevantes nesta hora."

    rodape = "⚡ Antes do Sino — Curadoria em tempo real"
    if restantes > 0:
        rodape = "+" + str(restantes) + " atualizações adicionais nesta hora.\n\n" + rodape

    headline = build_giro_headline(mostrados)
    headline_bloco = ("💡 " + html_module.escape(headline, quote=False) + "\n\n") if headline else ""

    message = (
        "📊 <b>GIRO DO MERCADO (" + inicio + " - " + fim + ")</b>\n\n"
        + headline_bloco + corpo + "\n\n" + rodape
    )
    message = sanitize_message_text(message)
    if len(message) > 3900:
        message = smart_truncate(message, 3900)
    return message, mostrados


GIRO_STATE_FILE = "docs/giro_state.json"


def load_giro_state():
    if os.path.exists(GIRO_STATE_FILE):
        try:
            with open(GIRO_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_giro_sent": ""}
    return {"last_giro_sent": ""}


def save_giro_state(state):
    os.makedirs(os.path.dirname(GIRO_STATE_FILE), exist_ok=True)
    with open(GIRO_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_send_giro_do_mercado():
    state = load_giro_state()
    last = state.get("last_giro_sent")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return (datetime.now(BR_TZ) - last_dt) >= timedelta(minutes=GIRO_INTERVALO_MINUTOS)


def processar_giro_do_mercado(telegram_bot_token, telegram_chat_id):
    """Consolida os itens 'round' acumulados (score 4-7, ou sem score)
    numa unica mensagem por hora, no lugar de 1 mensagem por noticia -
    a peca central da correcao de flood do grupo. So dispara dentro da
    janela horaria (should_send_giro_do_mercado); sempre reseta o
    relogio de 1h mesmo com fila vazia, pra manter cadencia previsivel.
    Isolado - qualquer falha aqui nunca afeta o resto do pipeline."""
    if editorial_foundation is None:
        return
    if not should_send_giro_do_mercado():
        return

    fila = editorial_foundation.get_round_queue().get("queue", [])

    if not fila:
        save_giro_state({"last_giro_sent": datetime.now(BR_TZ).isoformat()})
        return

    message, itens_incluidos = build_giro_message(fila)
    if send_briefing_message(message, telegram_bot_token, telegram_chat_id):
        # So remove da fila o que realmente coube na mensagem - itens
        # que ficaram de fora (ver GIRO_MAX_ITENS_POR_MENSAGEM) ficam
        # guardados pro proximo Giro, em vez de serem descartados sem
        # nunca terem sido mostrados ao usuario.
        editorial_foundation.clear_round_queue(itens_incluidos)
        save_giro_state({"last_giro_sent": datetime.now(BR_TZ).isoformat()})
        print("Giro do Mercado enviado com " + str(len(itens_incluidos)) + " de " + str(len(fila)) + " item(ns) na fila.")
    else:
        print("Falha ao enviar Giro do Mercado - fila mantida, tentaremos novamente no proximo ciclo.")

FEEDS = {
    # --- Prioridade maxima (5) ---
    "Bloomberg Markets": {"url": "https://feeds.bloomberg.com/markets/news.rss", "priority": 5, "language": "en", "category": "Mercado financeiro"},
    "CNBC - Finance": {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "priority": 5, "language": "en", "category": "Mercado financeiro"},
    "CNBC - Economy": {"url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "priority": 5, "language": "en", "category": "Macroeconomia"},
    "WSJ Markets": {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "priority": 5, "language": "en", "category": "Mercado financeiro"},
    "InfoMoney": {"url": "https://www.infomoney.com.br/feed/", "priority": 5, "language": "pt", "category": "Mercado financeiro"},
    "IBGE": {"url": "https://agenciadenoticias.ibge.gov.br/agencia-rss", "priority": 5, "language": "pt", "category": "Indicadores economicos"},

    # --- Prioridade alta (4) ---
    "Money Times": {"url": "https://www.moneytimes.com.br/mercados/feed", "priority": 4, "language": "pt", "category": "Mercado financeiro"},
    "Investing.com Brasil": {"url": "https://br.investing.com/rss/news_25.rss", "priority": 4, "language": "pt", "category": "Mercado financeiro"},
    "Brazil Journal": {"url": "https://braziljournal.com/feed/", "priority": 4, "language": "pt", "category": "Empresas"},
    "Exame": {"url": "https://exame.com/feed/", "priority": 4, "language": "pt", "category": "Empresas"},
    "MarketWatch": {"url": "https://feeds.marketwatch.com/marketwatch/topstories/", "priority": 4, "language": "en", "category": "Mercado financeiro"},
    "Seeking Alpha": {"url": "https://seekingalpha.com/market_currents.xml", "priority": 4, "language": "en", "category": "Mercado financeiro"},
    "Poder360": {"url": "https://www.poder360.com.br/poder-economia/feed/", "priority": 4, "language": "pt", "category": "Governo"},
    "Nasdaq": {"url": "https://www.nasdaq.com/feed/rssoutbound?category=Markets", "priority": 4, "language": "en", "category": "Mercado financeiro"},

    # --- Prioridade media (3) ---
    "G1 Economia": {"url": "https://g1.globo.com/dynamo/economia/rss2.xml", "priority": 3, "language": "pt", "category": "Macroeconomia"},
    "UOL Economia": {"url": "https://rss.uol.com.br/feed/economia.xml", "priority": 3, "language": "pt", "category": "Macroeconomia"},
    "Seu Dinheiro": {"url": "https://www.seudinheiro.com/feed/", "priority": 3, "language": "pt", "category": "Mercado financeiro"},
    "Suno Noticias": {"url": "https://www.suno.com.br/noticias/feed/", "priority": 3, "language": "pt", "category": "Mercado financeiro"},
    "Neofeed": {"url": "https://neofeed.com.br/feed/", "priority": 3, "language": "pt", "category": "Empresas"},
    "TechCrunch": {"url": "https://techcrunch.com/feed/", "priority": 3, "language": "en", "category": "Tecnologia"},
    "Yahoo Finance": {"url": "https://finance.yahoo.com/news/rssindex", "priority": 3, "language": "en", "category": "Mercado financeiro"},
    "Business Insider": {"url": "https://www.businessinsider.com/rss", "priority": 3, "language": "en", "category": "Empresas"},
    "CNBC - US News": {"url": "https://www.cnbc.com/id/15837362/device/rss/rss.html", "priority": 3, "language": "en", "category": "Internacional"},

    # --- Prioridade baixa (2) ---
    "ZeroHedge": {"url": "https://feeds.feedburner.com/zerohedge/feed", "priority": 2, "language": "en", "category": "Macroeconomia"},

    # --- Fontes primarias novas (auditoria editorial - Etapa 1) ---
    "Federal Reserve": {"url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "priority": 5, "language": "en", "category": "Banco central"},
    "SEC": {"url": "https://www.sec.gov/news/pressreleases.rss", "priority": 4, "language": "en", "category": "Regulacao"},
    "BLS": {"url": "https://www.bls.gov/feed/bls_latest.rss", "priority": 4, "language": "en", "category": "Indicadores economicos"},
}

# PORTUGUESE_SOURCES e derivado do campo "language" de FEEDS - uma unica
# fonte de verdade, em vez de manter uma lista hardcoded separada que
# poderia divergir do que esta cadastrado em FEEDS.
PORTUGUESE_SOURCES = {name for name, info in FEEDS.items() if info["language"] == "pt"}

KEYWORDS = [
    "selic", "juros", "ibovespa", "dolar", "inflacao",
    "acoes", "acao", "bolsa", "b3", "cdi", "tesouro direto",
    "cambio", "pib", "copom", "banco central", "bc",
    "interest rate", "fed", "federal reserve", "stocks", "stock market",
    "nasdaq", "dow jones", "s&p 500", "s&p", "inflation", "gdp", "bonds",
    "treasury", "earnings", "ipo", "recession", "rate cut", "rate hike",
    "wall street", "market", "economy", "economic", "trading", "investors",
    "yield", "moody's", "fitch",
    "petr4", "petr3", "vale3", "itub4", "bbdc4", "bbdc3", "abev3", "bbas3",
    "wege3", "rent3", "suzb3", "jbss3", "b3sa3", "mglu3", "lren3", "ggbr4",
    "elet3", "elet6", "csna3", "usim5", "prio3", "rail3", "azul4", "cvcb3",
    "hapv3", "radl3", "vivt3", "sanb11", "brfs3", "embr3",
    "petrobras", "vale", "itau", "bradesco", "ambev", "banco do brasil",
    "weg", "localiza", "suzano", "jbs", "magazine luiza", "magalu",
    "lojas renner", "renner", "gerdau", "eletrobras", "csn", "usiminas",
    "azul", "gol", "cvc", "hapvida", "raia drogasil", "totvs", "vivo",
    "santander brasil", "brf", "embraer", "natura", "cosan",
    "apple", "microsoft", "google", "alphabet", "amazon", "tesla", "meta",
    "nvidia", "netflix", "jpmorgan", "jp morgan", "goldman sachs",
    "berkshire hathaway", "visa", "mastercard", "disney", "coca-cola",
    "boeing", "intel", "exxon", "chevron", "walmart", "pfizer",
]

NEGATIVE_KEYWORDS = [
    "gols", "haaland", "futebol", "campeonato", "libertadores", "neymar", "copa do mundo",
    "partida", "placar", "escalacao", "treinador", "venceu o jogo", "derrota", "tabela",
    "banco de reservas", "medalha de ouro", "podio", "olimpiadas", "olimpico", "grand slam",
    "ufc", "nba", "champions league", "premier league", "venda de jogador", "passe de",
    "football", "soccer", "match", "score", "coach", "world cup", "olympics", "gold medal",
    "stadium", "championship", "player transfer", "substitute bench",
    "estreia nos cinemas", "novela", "atriz", "ator", "bbb", "celebridade", "fofoca",
    "venda de ingressos", "show de", "rock in rio", "lollapalooza", "album", "musica",
    "clipe", "estreia no", "bilheteria", "oscar", "grammy", "hollywood",
    "box office", "movie premiere", "actor", "actress", "celebrity", "gossip", "tickets sold",
    "concert", "festival", "album launch", "music video", "pop star", "fashion week",
    "crime", "assassinato", "preso em flagrante", "acidente de carro", "tiroteio", "policia",
    "trafico", "homicidio", "roubo de bolsa", "furto", "assalto", "sequestro", "baleado",
    "murder", "shooting", "police raid", "car crash", "kidnapping", "homicide",
    "acoes judiciais", "acao judicial", "processo na justica", "processa", "processado por",
    "tribunal de justica", "liminar", "reclamacao trabalhista",
    "lawsuit", "lawsuits", "legal action", "suing", "sued by", "courthouse", "injunction",
    "judge rules", "labor lawsuit",
    "matsunaga", "assassino", "assassina", "homicidio", "homicídio", "preso", "presa",
    "cadeia", "penitenciaria", "penitenciária", "policia", "polícia", "crime", "criminoso",
    "violencia", "violência", "tribunal", "juri", "júri", "heranca", "herança",
    "ferias escolares", "férias escolares", "guarda do filho", "guarda da filha",
    "celebridade", "celebridades", "famosos", "famosa", "influencer", "reality show",
    "ex-marido", "ex-mulher", "affair", "traicao", "traição",
]

WORDPRESS_BOILERPLATE_PATTERNS = [
    r"The post .* appeared first on \w+\s*\.?",
    r"O post .* apareceu primeiro (n[oa]) \w+\s*\.?",
    r"Image source[,:]?\s*[^\n]*",
    r"Photo\s*(credit|source)[,:]?\s*[^\n]*",
    r"Cr[eé]dito\s*(da\s*)?(foto|imagem)[,:]?\s*[^\n]*",
    r"^\s*Getty Images\s*$",
    r"^\s*Reuters/[A-Za-z ]+$",
]


DEDUP_WINDOW_HOURS = 12


def load_state():
    """recent_titles e uma lista de dicts {"title", "sent_at"} - janela
    de tempo real (DEDUP_WINDOW_HOURS), nao mais um corte por
    quantidade fixa. Compartilhada entre o pipeline RSS e o
    encaminhador de canais, entao uma noticia ja publicada por um dos
    dois bloqueia o outro de publicar de novo.

    Compatibilidade: entradas antigas (string simples, sem timestamp -
    formato de antes desta mudanca) sao descartadas ao carregar, ja
    que nao da pra saber a idade real delas - a janela de 12h se
    autopreenche de novo em poucas horas, sem risco de duplicar nesse
    meio-tempo (o hash exato continua cobrindo o caso mais obvio)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                hashes = set(data.get("hashes", []))
                raw_titles = data.get("titles", [])
                titles = [t for t in raw_titles if isinstance(t, dict) and t.get("title") and t.get("sent_at")]
                return hashes, titles
        except Exception as e:
            print("AVISO: falha ao carregar estado (" + str(e) + "). Criando novo.")
    return set(), []


def save_state(hashes, titles):
    limite = datetime.now(BR_TZ) - timedelta(hours=DEDUP_WINDOW_HOURS)
    titles_na_janela = []
    for t in titles:
        try:
            if datetime.fromisoformat(t["sent_at"]) >= limite:
                titles_na_janela.append(t)
        except Exception:
            continue

    trimmed_hashes = list(hashes)[-3000:]
    # Trava de seguranca adicional (independente da janela de tempo) -
    # evita que um dia excepcionalmente movimentado deixe o arquivo
    # crescer sem limite.
    trimmed_titles = titles_na_janela[-1000:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"hashes": trimmed_hashes, "titles": trimmed_titles}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("ERRO ao salvar estado: " + str(e))


def add_to_recent_titles(recent_titles, title):
    recent_titles.append({"title": title, "sent_at": datetime.now(BR_TZ).isoformat()})


def normalize_url(url):
    return url.split("?")[0].split("#")[0]


def item_hash(entry):
    key = normalize_url(entry.get("link", "")) or entry.get("title", "")
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def get_entry_body(entry):
    for field in ["summary", "description", "subtitle"]:
        value = entry.get(field, "")
        if value and value.strip():
            return value
    return ""


def is_relevant(entry):
    text = (entry.get("title", "") + " " + get_entry_body(entry)).lower()
    if any(re.search(r"\b" + re.escape(nw) + r"\b", text) for nw in NEGATIVE_KEYWORDS):
        return False
    if not KEYWORDS:
        return True
    return any(kw.lower() in text for kw in KEYWORDS)


def is_duplicate_title(title, recent_titles):
    """Limiar afinado de 0.92 para 0.85 - com a integracao de fontes que
    cobrem os mesmos eventos com fraseado proprio (Poder360/TechCrunch/
    Yahoo AU podem repetir pauta ja coberta por Reuters/CNBC/InfoMoney),
    um limiar mais permissivo pega parafraseio que o anterior deixava
    passar. FEEDS esta ordenado por prioridade editorial, entao a
    fonte de maior prioridade e processada primeiro e "vence" o
    duplicado - mantemos so a melhor versao, como pedido.

    recent_titles ja vem filtrada pela janela de tempo (ver load_state/
    save_state) - aqui so compara o texto. Compartilhada entre o
    pipeline RSS e o encaminhador de canais, entao tambem pega o caso
    de uma noticia ja publicada via RSS ser reencontrada, com fraseado
    proprio, num canal encaminhado (ou vice-versa)."""
    for item in recent_titles:
        old_title = item["title"] if isinstance(item, dict) else item
        ratio = difflib.SequenceMatcher(None, title.lower(), old_title.lower()).ratio()
        if ratio > 0.85:
            return True
    return False


def passes_source_specific_filter(source, entry):
    """Filtro editorial especifico por fonte (Etapa 5) - aplicado
    ALEM do filtro generico de palavras-chave (is_relevant). Cada
    fonte nova tem um perfil de ruido diferente, entao usa um criterio
    proprio, mantendo a filosofia de maximo sinal, minimo ruido.
    Retorna (aprovado: bool, motivo_descarte: str)."""
    text = (entry.get("title", "") + " " + get_entry_body(entry)).lower()

    # Aviso de agenda de teleconferencia de resultados (ex: "News Corp.
    # Q4 26 Earnings Conference Call At 5:00 PM ET") - e um aviso de
    # HORARIO, nao noticia. Aplica-se independente da fonte, ja que
    # esse formato mecanico aparece em varios feeds de wire financeiro.
    if re.search(r"earnings conference call at \d{1,2}:\d{2}\s*(am|pm)\s*et", text):
        return False, "aviso de agenda de teleconferencia (nao e noticia)"

    if source == "Seeking Alpha":
        # Seeking Alpha publica um snippet mecanico de EPS/receita pra
        # praticamente toda empresa que reporta resultado, incluindo
        # small/mid caps americanas sem nenhuma relevancia pro publico
        # do canal. So deixa passar se mencionar um ativo que o
        # projeto de fato acompanha (ASSET_PROFILES) - senao e ruido.
        formato_mecanico_resultado = re.search(
            r"gaap eps of|beats top-line and bottom-line|misses top-line and bottom-line|"
            r"\bq\d\s*(?:'?\d{2})?\s*income (rises|declines)\b",
            text,
        )
        if formato_mecanico_resultado:
            termos_acompanhados = [t for perfil in ASSET_PROFILES for t in perfil["terms"]]
            if not any(re.search(r"\b" + re.escape(termo) + r"\b", text) for termo in termos_acompanhados):
                return False, "resultado trimestral de empresa fora do radar (Seeking Alpha)"

    if source not in ("TechCrunch", "Poder360", "IBGE"):
        return True, ""

    if source == "TechCrunch":
        prioridade = [
            "openai", "google", "microsoft", "nvidia", "meta", "amazon", "apple",
            "startup", "venture capital", "funding round", "series a", "series b",
            "semiconductor", "chip", "cloud computing", "artificial intelligence",
            "ai startup", "ai model", "ai chip", "generative ai", "large language model",
            "llm", "chatbot", "machine learning", "big tech", "ai agent", "ai lab",
        ]
        descartar = [
            "review:", "hands-on", "hands on", "best deals", "gift guide",
            "how to", "unboxing", "gadget review", "hidden gems", "app store",
            "apps you", "best apps", "must-have app", "apps to try", "app of the",
        ]
        if any(d in text for d in descartar):
            return False, "review/gadget/consumo/lista de apps"
        if not any(p in text for p in prioridade):
            return False, "fora do escopo IA/startups/Big Tech"
        return True, ""

    if source == "Poder360":
        prioridade = [
            "fazenda", "banco central", "congresso", "tributa", "fiscal",
            "reforma tributaria", "reforma administrativa", "imposto", "copom",
            "selic", "haddad", "orcamento", "divida publica", "arcabouco fiscal",
            "regulamentacao", "regulacao",
        ]
        if not any(p in text for p in prioridade):
            return False, "politica sem impacto economico direto"
        return True, ""

    if source == "IBGE":
        sempre_relevante = [
            "ipca", "ipca-15", "pib", "pnad", "pim", "pmc", "pms",
            "producao industrial", "varejo", "servicos", "mercado de trabalho",
            "desemprego", "desocupacao",
        ]
        institucional = [
            "seminario", "aniversario", "comemora", "celebra", "podcast",
            "audiencia publica", "banca examinadora", "processo seletivo",
            "edital", "reserva ecologica", "mapa-mundi",
        ]
        if any(s in text for s in sempre_relevante):
            return True, ""
        if any(i in text for i in institucional):
            return False, "noticia institucional sem indicador economico"
        return True, ""

    return True, ""


def strip_html_tags(text):
    if not text:
        return ""
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"@media[^{]*\{[^}]*\}", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\.[a-zA-Z0-9_-]+\s*\{[^}]*\}", "", text, flags=re.DOTALL)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()


def truncate_text_clean(text, max_length=160):
    """Corta o texto no ultimo espaco completo antes do limite, nunca
    no meio de uma palavra, e adiciona '...' no final quando houver
    corte. Usada em resumos de cards e meta description."""
    if not text:
        return text
    text = text.strip()
    if len(text) <= max_length:
        return text
    cut = text[:max_length]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    cut = cut.rstrip(" ,;:-")
    return cut + "..."


def smart_truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_sentence_end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if last_sentence_end > limit * 0.5:
        return cut[:last_sentence_end + 1]
    last_space = cut.rfind(" ")
    if last_space > 0:
        return cut[:last_space] + "..."
    return cut + "..."


def sanitize_message_text(text):
    """Ultima linha de defesa - roda em QUALQUER texto antes de virar
    parte da mensagem final do Telegram, nao importa se veio da IA, do
    RSS ou do encaminhador. Remove qualquer artefato tecnico que nao
    deveria chegar ao usuario final: chaves soltas, null/None
    literais, fragmentos de JSON, linhas vazias duplicadas, espacos
    extras - e qualquer resquicio de canal/grupo de origem (@usuario,
    link de convite, convite para entrar em grupo)."""
    if not text:
        return ""
    text = str(text)

    # Remove fragmentos de JSON/markdown que eventualmente escapem do parse
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = text.replace("```", "")

    # Remove chaves soltas (JSON quebrado nunca deve aparecer pro usuario)
    text = text.replace("{", "").replace("}", "")

    # Remove null/None/undefined literais (typico de parse malformado)
    text = re.sub(r"\b(null|none|undefined)\b", "", text, flags=re.IGNORECASE)

    # Remove aspas orfas de JSON quebrado (ex: '"summary":' sobrando)
    text = re.sub(r'"\s*[a-zA-Z_]+"\s*:\s*', "", text)

    # Remove @usuario, link de convite do Telegram e frases-convite -
    # nunca deve sobrar referencia ao grupo/canal de origem. As regras
    # de convite exigem sinal especifico (posse "nosso/nossa" ou
    # mencao explicita a Telegram/WhatsApp) para nao apagar palavra
    # legitima de noticia financeira (ex: "assine o contrato", "canal
    # de vendas", "siga a tendencia do mercado", "grupo economico").
    text = re.sub(r"@\w{3,}", "", text)
    text = re.sub(r"t\.me/\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)(entre|junte-se|inscreva-se|assine|siga)(-nos)?\s+(no|na|ao)?\s*(nosso|nossa)\s+(grupo|canal)(\s+d[oe]\s+telegram)?[^.\n]*\.?",
        "", text
    )
    text = re.sub(r"(?i)\b(grupo|canal)\s+d[oe]\s+telegram\b[^.\n]*\.?", "", text)
    text = re.sub(r"(?i)\bsiga(-nos)?\s+(no|pelo|via)\s+(telegram|whatsapp)\b[^.\n]*\.?", "", text)

    # Colapsa espacos e limita linha vazia dupla intencional (paragrafo)
    # sem destruir a separacao entre titulo e resumo.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_json_object(raw_text):
    """Extrai o primeiro objeto JSON valido de dentro de um texto que
    pode vir com prosa antes/depois (a Groq as vezes escreve 'Aqui
    esta o resultado: {...}' apesar da instrucao de responder so
    JSON). Reduz taxa de falha do parse sem afrouxar a seguranca -
    se nao encontrar nada parseavel, retorna None."""
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


def strip_boilerplate(text):
    for pattern in WORDPRESS_BOILERPLATE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    return text


def is_recent_enough(entry):
    date_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not date_struct:
        return True
    entry_date = datetime(*date_struct[:6], tzinfo=timezone.utc).astimezone(BR_TZ)
    now = datetime.now(BR_TZ)
    return entry_date.date() == now.date()


def fetch_feed(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        return feedparser.parse(response.content)
    except Exception as e:
        print("AVISO: falha ao buscar feed " + url + ": " + str(e))
        return feedparser.parse("")


GROQ_MODEL_LIGHT = "llama-3.1-8b-instant"
GROQ_MODEL_STRONG = "llama-3.3-70b-versatile"


def ask_groq(prompt, purpose="analysis"):
    """Camada CENTRALIZADA de chamada a Groq - toda chamada do projeto
    passa por aqui. 'purpose' escolhe o modelo automaticamente:

      purpose="analysis"   -> modelo LEVE (llama-3.1-8b-instant)
                               classificacao, sentimento, categorizacao,
                               qualquer tarefa de alto volume.
      purpose="generation" -> modelo FORTE (llama-3.3-70b-versatile)
                               Briefings, textos finais publicados.

    Mantem timeout, tratamento de erro e retorno seguro. Loga
    claramente quando o motivo da falha e limite de taxa (rate limit),
    para diagnostico rapido - nunca falha silenciosamente."""
    modelo = GROQ_MODEL_STRONG if purpose == "generation" else GROQ_MODEL_LIGHT

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": modelo,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=20,
        )
        data = response.json()
    except Exception as e:
        print("Erro de rede na chamada Groq (" + purpose + "/" + modelo + "): " + str(e))
        raise

    if "choices" not in data:
        erro = data.get("error", {}) if isinstance(data, dict) else {}
        codigo_erro = erro.get("code", "")
        mensagem_erro = erro.get("message", str(data))
        if codigo_erro == "rate_limit_exceeded":
            print("AVISO (rate limit Groq, " + purpose + "/" + modelo + "): " + mensagem_erro)
        else:
            print("Erro na resposta da Groq (" + purpose + "/" + modelo + "): " + mensagem_erro)
        raise ValueError("Resposta sem choices: " + str(data))

    return data["choices"][0]["message"]["content"].strip()


VALUE_PROP_BLOCK = (
    "<section style='background:rgba(255,255,255,0.02);border-top:1px solid var(--line);'>"
    "<div class='section-head'>"
    "<span class='kicker'>Antes do Sino</span>"
    "<h2>Isso é o Antes do Sino</h2>"
    "</div>"
    "<p style='color:var(--slate);max-width:640px;'>"
    "Notícias de mercado traduzidas, resumidas e classificadas por sentimento, reunidas "
    "num só lugar. Esta página é gratuita e sempre vai ser."
    "</p>"
    "<p style='margin-top:16px;'>"
    "<a href='https://t.me/+TobMzw-WnQhmZmIx' style='color:var(--gold);font-weight:600;'>"
    "Prefere receber isso direto no Telegram, sem precisar voltar aqui? Entrar no grupo grátis &rarr;"
    "</a></p>"
    "</section>"
)


def classify_news_ai(title, body, translate=False):
    """Chamada UNICA e combinada a Groq - relevancia + sentimento
    sempre; titulo e resumo traduzidos SOMENTE quando translate=True
    (fonte em ingles), tudo na mesma chamada, sem voltar a gastar 2
    chamadas por noticia.

    'relevante_mercado' e o filtro que bloqueia noticia de crime/
    celebridade (ex: caso Matsunaga). 'sentiment' e uma analise que a
    IA faz melhor que uma regra simples (ex: reconhecer que 'corte de
    custos' costuma ser BULLISH para a acao, mesmo soando negativo a
    primeira vista). A traducao usa o corpo real da noticia como base
    (nunca inventa fato), pedindo traducao fiel, nao parafraseie livre."""
    if not USE_AI:
        return None
    try:
        body_cleaned = strip_html_tags(body).strip()
        body_cleaned = strip_boilerplate(body_cleaned)

        if translate:
            instruction = (
                "Voce e o classificador e tradutor de um canal de Telegram de mercado "
                "financeiro para traders brasileiros. Analise a noticia abaixo (em ingles) "
                "e responda seis coisas:\n"
                "1. relevante_mercado: true SOMENTE se a noticia for genuinamente sobre "
                "mercado financeiro, economia ou negocios. false se for sobre crime, policia, "
                "justica criminal, celebridade, entretenimento, esporte, ou qualquer assunto "
                "fora desse escopo.\n"
                "2. sentiment: classifique o impacto da noticia para o mercado como BULLISH, "
                "BEARISH ou NEUTRAL - considere o contexto real (ex: corte de custos costuma "
                "ser BULLISH para a acao, mesmo soando negativo a primeira vista).\n"
                "3. translated_title: traduza o titulo para portugues do Brasil de forma "
                "fiel e direta, sem inventar informacao.\n"
                "4. translated_summary: traduza/resuma o texto original para portugues do "
                "Brasil em 1-2 frases fieis ao conteudo original, sem inventar fato novo. Se "
                "o texto original for vazio, deixe translated_summary como string vazia.\n"
                "5. score_materialidade: de 0 a 10, o quanto essa noticia especifica e "
                "materialmente relevante pro mercado AGORA (nao pro tema em geral) - 0-2 "
                "irrelevante/ruido, 3-5 relevante mas rotineiro, 6-8 relevante e com impacto "
                "concreto, 9-10 evento de mercado maior (decisao de juros, choque geopolitico, "
                "resultado muito acima/abaixo do esperado).\n"
                "6. motivo_materialidade: 1 frase curta explicando o score dado.\n\n"
                "Responda APENAS em JSON plano, sem markdown, sem texto antes ou depois, no "
                "formato exato:\n"
                '{"relevante_mercado": true, "sentiment": "BULLISH", '
                '"translated_title": "titulo em portugues", '
                '"translated_summary": "resumo em portugues", '
                '"score_materialidade": 5, "motivo_materialidade": "motivo curto"}\n\n'
                "Titulo: " + title + "\n"
                "Texto: " + body_cleaned
            )
        else:
            instruction = (
                "Voce e o classificador de um canal de Telegram de mercado financeiro para "
                "traders. Analise a noticia abaixo e responda quatro coisas:\n"
                "1. relevante_mercado: true SOMENTE se a noticia for genuinamente sobre mercado "
                "financeiro, economia ou negocios. false se for sobre crime, policia, justica "
                "criminal, celebridade, entretenimento, esporte, ou qualquer assunto fora desse "
                "escopo.\n"
                "2. sentiment: classifique o impacto da noticia para o mercado como BULLISH, "
                "BEARISH ou NEUTRAL - considere o contexto real (ex: corte de custos costuma ser "
                "BULLISH para a acao, mesmo soando negativo a primeira vista).\n"
                "3. score_materialidade: de 0 a 10, o quanto essa noticia especifica e "
                "materialmente relevante pro mercado AGORA (nao pro tema em geral) - 0-2 "
                "irrelevante/ruido, 3-5 relevante mas rotineiro, 6-8 relevante e com impacto "
                "concreto, 9-10 evento de mercado maior (decisao de juros, choque geopolitico, "
                "resultado muito acima/abaixo do esperado).\n"
                "4. motivo_materialidade: 1 frase curta explicando o score dado.\n\n"
                "Responda APENAS em JSON plano, sem markdown, sem texto antes ou depois, no "
                "formato exato:\n"
                '{"relevante_mercado": true, "sentiment": "BULLISH", '
                '"score_materialidade": 5, "motivo_materialidade": "motivo curto"}\n\n'
                "Titulo: " + title + "\n"
                "Texto: " + body_cleaned
            )

        raw_response = ask_groq(instruction, purpose="analysis")
        parsed = extract_json_object(raw_response)
        if parsed is None or not isinstance(parsed, dict):
            print("AVISO: resposta da IA nao contem JSON valido - fallback seguro aplicado.")
            return None

        raw_relevante = parsed.get("relevante_mercado")
        relevante_mercado = raw_relevante if isinstance(raw_relevante, bool) else True

        raw_sentiment = parsed.get("sentiment")
        if isinstance(raw_sentiment, str) and raw_sentiment.strip().upper() in ("BULLISH", "BEARISH", "NEUTRAL"):
            sentiment = raw_sentiment.strip().upper()
        else:
            sentiment = "NEUTRAL"

        result = {
            "sentiment": sentiment,
            "relevante_mercado": relevante_mercado,
        }

        # Campos de materialidade (Fase 1 - modo sombra). Parsing
        # totalmente defensivo: se vier ausente ou fora do formato
        # esperado, o campo fica None e o modo sombra simplesmente
        # nao pontua essa noticia - nunca quebra classify_news_ai por
        # causa disso, e o retorno continua 100% compativel com quem
        # ja consome so sentiment/relevante_mercado/traducao.
        raw_score = parsed.get("score_materialidade")
        score_materialidade = None
        if isinstance(raw_score, (int, float)) and 0 <= raw_score <= 10:
            score_materialidade = round(float(raw_score), 1)
        result["score_materialidade"] = score_materialidade

        raw_motivo = parsed.get("motivo_materialidade")
        result["motivo_materialidade"] = raw_motivo.strip() if isinstance(raw_motivo, str) else None

        if translate:
            # Validacao defensiva - se a traducao vier vazia/invalida,
            # nao preenche o campo, e format_message cai de volta no
            # texto original em ingles em vez de mostrar algo quebrado.
            raw_translated_title = parsed.get("translated_title")
            if isinstance(raw_translated_title, str):
                clean_title = sanitize_message_text(raw_translated_title)
                if clean_title:
                    result["translated_title"] = clean_title

            raw_translated_summary = parsed.get("translated_summary")
            if isinstance(raw_translated_summary, str):
                clean_summary = sanitize_message_text(raw_translated_summary)
                if clean_summary:
                    result["translated_summary"] = clean_summary

        return result
    except Exception as e:
        print("Erro IA (Groq, fallback seguro aplicado): " + str(e))
        return None


def extract_earnings_details(title, body):
    """So chamada quando is_earnings_news() bate para uma noticia com
    ticker identificado (ver maybe_extract_earnings_details) - extrai,
    usando SOMENTE o que esta explicito no texto (nunca completa com
    conhecimento externo nem inventa numero/consenso), o numero
    principal reportado, a comparacao com o esperado (quando o texto
    mencionar) e o destaque qualitativo do resultado."""
    if not USE_AI:
        return None
    try:
        body_cleaned = strip_boilerplate(strip_html_tags(body)).strip()
        instrucao = (
            "Voce esta lendo uma noticia de resultado trimestral/balanco de uma "
            "empresa. Extraia, USANDO SOMENTE o que esta explicito no texto abaixo "
            "(nunca complete com conhecimento externo, nunca invente numero ou "
            "consenso de mercado que o texto nao mencione):\n"
            "1. reportado: o numero principal reportado, com contexto curto (ex: "
            "'lucro liquido de R$ 7,05 bi, alta de 16% no ano'). Se o texto nao "
            "trouxer um numero claro, use string vazia.\n"
            "2. vs_esperado: comparacao com expectativa/consenso de mercado, SOMENTE "
            "se o texto mencionar isso explicitamente (ex: 'acima do esperado pelos "
            "analistas'). Se o texto nao mencionar expectativa, use string vazia.\n"
            "3. destaque: 1 frase curta com o principal destaque qualitativo do "
            "resultado (motivo do lucro/prejuizo, guidance, divisao que mais "
            "cresceu). Se nao houver nada alem do numero, use string vazia.\n\n"
            "Responda APENAS em JSON plano, sem markdown, sem texto antes ou "
            "depois, no formato exato:\n"
            '{"reportado": "...", "vs_esperado": "...", "destaque": "..."}\n\n'
            "Titulo: " + title + "\n"
            "Texto: " + body_cleaned
        )
        raw_response = ask_groq(instrucao, purpose="analysis")
        parsed = extract_json_object(raw_response)
        if not isinstance(parsed, dict):
            return None

        reportado = parsed.get("reportado")
        vs_esperado = parsed.get("vs_esperado")
        destaque = parsed.get("destaque")
        result = {
            "reportado": sanitize_message_text(reportado) if isinstance(reportado, str) else "",
            "vs_esperado": sanitize_message_text(vs_esperado) if isinstance(vs_esperado, str) else "",
            "destaque": sanitize_message_text(destaque) if isinstance(destaque, str) else "",
        }
        if not result["reportado"] and not result["destaque"]:
            return None
        return result
    except Exception as e:
        print("Erro ao extrair detalhes de resultado trimestral (fallback seguro): " + str(e))
        return None


def maybe_extract_earnings_details(dispatch_tier, hashtags, title, body, final_title, final_body):
    """So dispara a extracao estruturada de resultado trimestral
    (1 chamada de IA extra) quando a noticia realmente vai ser
    publicada (breaking ou round), cita um ativo especifico
    (hashtags) e bate no detector de palavras-chave de resultado -
    evita gastar chamada de IA em toda noticia que passa pelo pipeline."""
    if dispatch_tier not in ("breaking", "round"):
        return None
    if not hashtags:
        return None
    if not is_earnings_news(title + " " + body):
        return None
    earnings = extract_earnings_details(final_title, final_body)
    if earnings:
        time.sleep(2.5)
    return earnings


def send_telegram_message(text):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            print("Rate limit, aguardando " + str(retry_after) + "s")
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Erro Telegram (status " + str(r.status_code) + "): " + r.text)
        return r.status_code == 200
    except Exception as e:
        print("Erro Telegram: " + str(e))
        return False


def format_message(source, entry, ai_result):
    """Monta a mensagem final do Telegram no formato:
    Titulo em negrito
    (linha em branco)
    Resumo em paragrafo unico, corpo completo da noticia (sem corte
    artificial - so o limite real do Telegram, ver smart_truncate)
    (linha em branco, se houver fonte)
    Fonte - Nome da fonte

    Sem emoji, sem URL, sem convite para grupo/canal, sem mencionar
    Telegram/WhatsApp. O sentimento (BULLISH/BEARISH/NEUTRAL) ainda e
    calculado e retornado para uso interno do site (paginas de ativo/
    tema/Sinais do Dia), so nao aparece mais na mensagem em si.

    Titulo e resumo vem da traducao da IA quando a fonte e em ingles e
    a traducao funcionou (ai_result traz translated_title/
    translated_summary); caso contrario, usa o titulo e o corpo reais
    da noticia sem alteracao - nunca texto inventado, nunca
    reformatado em lista com marcador. Toda peca de texto passa por
    sanitize_message_text antes de entrar na mensagem final, entao
    mesmo que algo escape upstream (IA, RSS, encaminhador), a mensagem
    publicada nunca deve conter chave solta, null, boilerplate de
    imagem, @usuario ou referencia ao grupo/canal de origem."""
    title = entry.get("title", "Sem titulo")
    sentiment = "NEUTRAL"
    translated_summary = ""

    if ai_result:
        sentiment = ai_result.get("sentiment", "NEUTRAL")
        translated_title = ai_result.get("translated_title")
        if translated_title:
            title = translated_title
        translated_summary = ai_result.get("translated_summary") or ""

    if translated_summary:
        summary_text = translated_summary
    else:
        # Sem traducao (fonte em portugues) ou traducao falhou: usa o
        # corpo real da noticia como texto corrido - sem inventar
        # nada, sem reformatar em bullet. Se nao houver corpo
        # utilizavel, fica so o titulo.
        raw_body = get_entry_body(entry)
        raw_body = strip_html_tags(raw_body)
        raw_body = strip_boilerplate(raw_body)
        raw_body = re.sub(r"https?://\S+", "", raw_body)
        raw_body = re.sub(r"www\.\S+", "", raw_body)
        raw_body = re.sub(r"\s+", " ", raw_body).strip()

        summary_text = ""
        if raw_body and raw_body.lower() != title.lower():
            # Sem limite artificial aqui - o corpo real da noticia vai
            # inteiro pra mensagem. O unico corte que pode acontecer e
            # o do limite de 4096 caracteres do Telegram em si (ver
            # smart_truncate no final desta funcao), que corta no fim
            # de uma frase, nao no meio dela.
            summary_text = raw_body

    title = sanitize_message_text(title)
    summary_text = sanitize_message_text(summary_text)

    if not title:
        title = "Atualizacao de mercado"

    title_esc = html_module.escape(title, quote=False)

    summary_block = ""
    if summary_text:
        summary_block = "\n\n" + html_module.escape(summary_text, quote=False)

    # So mostra fonte se for uma fonte jornalistica identificavel -
    # nunca o nome do canal/grupo de origem (ja garantido rio acima:
    # o encaminhador so preenche 'source' quando detecta uma agencia
    # real, senao manda string vazia). Nunca inventa fonte.
    source_clean = sanitize_message_text(source or "")
    source_line = ""
    if source_clean:
        source_esc = html_module.escape(source_clean, quote=False)
        source_line = "\n\nFonte • " + source_esc

    result = (
        "<b>" + title_esc + "</b>"
        + summary_block
        + source_line
    )

    # Ultima linha de defesa: sanitiza a mensagem inteira ja montada,
    # remove qualquer chave/null/linha vazia duplicada/@usuario/
    # convite que tenha escapado dos passos anteriores.
    result = sanitize_message_text(result)

    if len(result) > 3900:
        result = smart_truncate(result, 3900)

    final_body = summary_text if summary_text else title
    return result, title, final_body, sentiment


def fetch_brapi_results(ticker):
    """Chamada crua a brapi.dev para 1 ticker - retorna a lista
    'results' do payload (pode ter 0, 1 ou mais itens), ou lista vazia
    em caso de token ausente/falha de rede."""
    if not BRAPI_TOKEN:
        return []
    try:
        url = "https://brapi.dev/api/quote/" + ticker + "?token=" + BRAPI_TOKEN
        response = requests.get(url, timeout=15)
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        print("Erro ao buscar cotacao " + ticker + " (brapi): " + str(e))
        return []


def fetch_cockpit_quotes():
    quotes = []
    for ticker in COCKPIT_TICKERS:
        for r in fetch_brapi_results(ticker):
            quotes.append({
                "symbol": r.get("symbol", ""),
                "price": r.get("regularMarketPrice", 0),
                "change": r.get("regularMarketChangePercent", 0),
            })
    return quotes


TWELVEDATA_CACHE_FILE = "docs/twelvedata_cache.json"
TWELVEDATA_CACHE_TTL_MINUTOS = 15

# So busca de verdade na Twelve Data dentro das janelas onde os dados
# realmente sao usados em alguma mensagem - fora disso, reaproveita o
# ultimo valor salvo (mesmo que antigo), sem gastar credito a toa.
TWELVEDATA_JANELAS_PERMITIDAS = [
    (8 * 60 + 15, 8 * 60 + 45),   # Opening / Agenda do Dia
    (12 * 60, 12 * 60 + 15),       # Snapshot 12h00 / Midday
    (18 * 60 + 30, 19 * 60),       # Closing
    (22 * 60, 22 * 60 + 30),       # Night Wrap
]


def _dentro_de_janela_twelvedata():
    agora = datetime.now(BR_TZ)
    minutos = agora.hour * 60 + agora.minute
    return any(inicio <= minutos <= fim for inicio, fim in TWELVEDATA_JANELAS_PERMITIDAS)


def _load_twelvedata_cache():
    if os.path.exists(TWELVEDATA_CACHE_FILE):
        try:
            with open(TWELVEDATA_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_twelvedata_cache(cache):
    os.makedirs(os.path.dirname(TWELVEDATA_CACHE_FILE), exist_ok=True)
    with open(TWELVEDATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def _fetch_twelvedata_quote_raw(symbol):
    """Camada UNICA de cotacao via Twelve Data - cobre forex, indices,
    commodities e cripto com a mesma chave e o mesmo formato de
    resposta. Retorna {"price": ..., "change": ...} ou None em
    qualquer falha - nunca quebra o snapshot.

    NOTA: o simbolo exato de commodities (ex: WTI) pode variar - se
    retornar None de forma consistente pra um simbolo especifico,
    vale conferir o simbolo certo no painel da Twelve Data e ajustar
    aqui."""
    if not TWELVEDATA_API_KEY:
        return None
    try:
        url = "https://api.twelvedata.com/quote"
        params = {"symbol": symbol, "apikey": TWELVEDATA_API_KEY}
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get("status") == "error" or "close" not in data:
            print("Twelve Data nao retornou dado valido para " + symbol + ": " + str(data))
            return None
        preco = float(data["close"])
        variacao_raw = data.get("percent_change")
        variacao = float(variacao_raw) if variacao_raw is not None else None
        return {"price": preco, "change": variacao}
    except Exception as e:
        print("Erro ao buscar cotacao Twelve Data (" + symbol + "): " + str(e))
        return None


def fetch_twelvedata_quote(symbol):
    """So chama a API de verdade DENTRO das janelas de mensagem
    (Opening, Snapshot/Midday, Closing, Night Wrap) - fora delas,
    reaproveita o ultimo valor salvo em cache, mesmo que antigo, sem
    gastar credito. Dentro da janela, ainda usa um TTL de 15 min pra
    nao chamar 3-6x seguidas dentro da mesma janela.

    Efeito esperado: consumo cai de ~750 para menos de 30
    creditos/dia. Trade-off aceito: fora dessas janelas, o Breaking
    News nao detecta movimento novo de USD/Bitcoin/WTI/S&P500 (o
    Ibovespa e acoes BR continuam em tempo real via brapi.dev,
    sem essa restricao)."""
    cache = _load_twelvedata_cache()
    entrada = cache.get(symbol)

    if not _dentro_de_janela_twelvedata():
        if entrada:
            return {"price": entrada["price"], "change": entrada["change"]}
        return None

    if entrada:
        try:
            buscado_em = datetime.strptime(entrada["fetched_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BR_TZ)
            minutos_desde_busca = (datetime.now(BR_TZ) - buscado_em).total_seconds() / 60
            if minutos_desde_busca < TWELVEDATA_CACHE_TTL_MINUTOS:
                return {"price": entrada["price"], "change": entrada["change"]}
        except Exception:
            pass  # cache corrompido/malformado - busca de novo com seguranca

    resultado = _fetch_twelvedata_quote_raw(symbol)
    if resultado is not None:
        cache[symbol] = {
            "price": resultado["price"],
            "change": resultado["change"],
            "fetched_at": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_twelvedata_cache(cache)
    return resultado


def fetch_usd_brl():
    """USD/BRL via Twelve Data - substitui a AwesomeAPI, consolidando
    numa unica fonte junto com S&P 500, WTI e Bitcoin."""
    return fetch_twelvedata_quote("USD/BRL")


def compute_sentiment_thermometer(entries):
    total = len(entries)
    if total == 0:
        return {"alta": 0, "baixa": 0, "info": 0, "total": 0}

    alta = sum(1 for e in entries if e["sentiment"] == "BULLISH")
    baixa = sum(1 for e in entries if e["sentiment"] == "BEARISH")
    info = total - alta - baixa

    return {
        "alta": round(alta / total * 100),
        "baixa": round(baixa / total * 100),
        "info": round(info / total * 100),
        "total": total,
    }


def market_status():
    now = datetime.now(BR_TZ)
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    is_weekday = weekday < 5
    current_minutes = hour * 60 + minute
    open_minutes = 10 * 60
    close_minutes = 17 * 60

    is_open = is_weekday and open_minutes <= current_minutes < close_minutes

    if is_open:
        return {"open": True, "label": "Mercado aberto"}
    else:
        return {"open": False, "label": "Mercado fechado"}


def fetch_selic():
    """Busca a taxa Selic atual via brapi.dev (gratuito)."""
    if not BRAPI_TOKEN:
        return None
    try:
        url = "https://brapi.dev/api/v2/prime-rate?country=brazil&token=" + BRAPI_TOKEN
        response = requests.get(url, timeout=15)
        data = response.json()
        rates = data.get("prime-rate", [])
        if rates:
            return rates[0].get("value", None)
        return None
    except Exception as e:
        print("Erro ao buscar Selic (brapi): " + str(e))
        return None


def fetch_bitcoin():
    """Bitcoin via Twelve Data - substitui a CoinGecko, consolidando
    numa unica fonte junto com USD/BRL, S&P 500 e WTI."""
    return fetch_twelvedata_quote("BTC/USD")


def fetch_fred_series(series_id):
    """Busca o valor mais recente e a variacao percentual de uma serie
    do FRED (Federal Reserve Economic Data) - fonte oficial, gratuita,
    exige chave (cadastro simples, sem cartao). Usada para Petroleo
    WTI (DCOILWTICO), Treasury 10Y (DGS10) e S&P 500 (SP500 - representa
    o ultimo fechamento disponivel, nao intraday).

    Busca ate 10 observacoes recentes (nao so 2) porque series do FRED
    tem lacunas em fins de semana/feriados - garante achar 2 valores
    validos mesmo com alguma lacuna no meio. Retorna None em qualquer
    falha - nunca quebra o snapshot."""
    if not FRED_API_KEY:
        return None
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            "?series_id=" + series_id
            + "&api_key=" + FRED_API_KEY
            + "&file_type=json&sort_order=desc&limit=10"
        )
        response = requests.get(url, timeout=15)
        data = response.json()
        observations = data.get("observations", [])

        valid = [o for o in observations if o.get("value") not in (None, ".", "")]
        if not valid:
            return None

        latest = float(valid[0]["value"])
        change = None
        if len(valid) >= 2:
            previous = float(valid[1]["value"])
            if previous:
                change = ((latest - previous) / previous) * 100

        return {"value": latest, "change": change}
    except Exception as e:
        print("Erro ao buscar serie FRED " + series_id + ": " + str(e))
        return None


def compute_market_snapshot():
    """Camada de dados de mercado, independente de noticia - apenas
    numeros organizados. Sem IA, sem HTML, sem texto, sem mensagem.

    Calculada UMA UNICA VEZ por execucao do bot (no main()) e
    reaproveitada por build_cockpit_html (Home) e pelos Briefings/
    Snapshot 12h00/Night Wrap - nenhuma chamada de API duplicada.

    Fontes: brapi.dev (Ibovespa/acoes BR, mantido - ja funciona bem de
    graca), Twelve Data (USD/BRL, Bitcoin, WTI, S&P 500 - consolidado
    numa unica chave, substituindo AwesomeAPI + CoinGecko + FRED pra
    esses 4), FRED (so Treasury 10Y, fora do escopo desta migracao)."""
    quotes = fetch_cockpit_quotes()
    usd = fetch_usd_brl()
    selic = fetch_selic()
    bitcoin = fetch_bitcoin()
    wti_raw = fetch_twelvedata_quote("WTI/USD")
    wti = {"value": wti_raw["price"], "change": wti_raw["change"]} if wti_raw else None
    treasury_10y = fetch_fred_series("DGS10")
    sp500_raw = fetch_twelvedata_quote("SPX")
    sp500 = {"value": sp500_raw["price"], "change": sp500_raw["change"]} if sp500_raw else None

    quotes_by_symbol = {}
    for q in quotes:
        symbol = q.get("symbol", "")
        if symbol:
            quotes_by_symbol[symbol] = q

    return {
        "quotes": quotes,
        "quotes_by_symbol": quotes_by_symbol,
        "usd": usd,
        "selic": selic,
        "bitcoin": bitcoin,
        "wti": wti,
        "treasury_10y": treasury_10y,
        "sp500": sp500,
        "fetched_at": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M"),
    }


def build_cockpit_html(portal_entries, entries_today=None, market_snapshot=None):
    if entries_today is None:
        entries_today = portal_entries

    # Reaproveita o snapshot ja calculado no main() quando disponivel -
    # so busca de novo se for chamado isoladamente (compatibilidade).
    if market_snapshot is None:
        market_snapshot = compute_market_snapshot()

    quotes = market_snapshot["quotes"]
    usd = market_snapshot["usd"]
    selic = market_snapshot["selic"]
    today_thermo = compute_sentiment_thermometer(entries_today)
    status = market_status()

    quotes_html = ""
    for q in quotes:
        change = q["change"]
        cls = "up" if change >= 0 else "down"
        sign = "+" if change >= 0 else ""
        quotes_html += (
            '<div class="quote-item">'
            '<span class="quote-symbol">' + html_module.escape(q["symbol"]) + "</span>"
            '<span class="quote-price">' + str(round(q["price"], 2)) + "</span>"
            '<span class="quote-change ' + cls + '">' + sign + str(round(change, 2)) + "%</span>"
            "</div>"
        )

    if usd:
        change = usd["change"]
        cls = "up" if change >= 0 else "down"
        sign = "+" if change >= 0 else ""
        quotes_html += (
            '<div class="quote-item">'
            '<span class="quote-symbol">USD/BRL</span>'
            '<span class="quote-price">R$ ' + str(round(usd["price"], 2)) + "</span>"
            '<span class="quote-change ' + cls + '">' + sign + str(round(change, 2)) + "%</span>"
            "</div>"
        )

    if selic is not None:
        quotes_html += (
            '<div class="quote-item">'
            '<span class="quote-symbol">SELIC</span>'
            '<span class="quote-price">' + str(selic) + "% a.a.</span>"
            '<span class="quote-change info">ref.</span>'
            "</div>"
        )

    if not quotes_html:
        quotes_html = '<div class="quote-empty">Cotações indisponíveis no momento.</div>'

    if today_thermo["total"] == 0:
        thermo_phrase = "Ainda não há notícias suficientes hoje para avaliar o humor do mercado."
    elif today_thermo["alta"] > today_thermo["baixa"]:
        thermo_phrase = "Hoje o mercado teve mais notícias positivas que negativas."
    elif today_thermo["baixa"] > today_thermo["alta"]:
        thermo_phrase = "Hoje o mercado teve mais notícias negativas que positivas."
    else:
        thermo_phrase = "Hoje o mercado está equilibrado entre notícias positivas e negativas."

    status_class = "open" if status["open"] else "closed"

    cockpit_html = (
        '<div class="cockpit-grid">'

        '<div class="cockpit-card">'
        '<span class="cockpit-label">Status do pregão</span>'
        '<div class="market-status ' + status_class + '">'
        '<span class="status-dot"></span>' + status["label"] +
        "</div>"
        "</div>"

        '<div class="cockpit-card quotes-card">'
        '<span class="cockpit-label">Cotações e Selic</span>'
        '<div class="quotes-list">' + quotes_html + "</div>"
        "</div>"

        '<div class="cockpit-card">'
        '<span class="cockpit-label">Termômetro do mercado</span>'
        '<p class="thermo-phrase">' + thermo_phrase + "</p>"
        "</div>"

        "</div>"
    )

    return cockpit_html


DAILY_ARCHIVE_FILE = "daily_archive.json"


def load_daily_archive():
    if os.path.exists(DAILY_ARCHIVE_FILE):
        try:
            with open(DAILY_ARCHIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_daily_archive(archive):
    trimmed = archive[-60:]
    with open(DAILY_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


RESUMO_HISTORICO_FILE = "docs/resumo_historico.json"


def export_resumo_historico(archive):
    """Publica o arquivo diario completo (ate 60 dias, ja trimado por
    save_daily_archive) como JSON publico - docs/resumo_historico.json.
    E o que alimenta o navegador de "edicoes anteriores" na pagina de
    resumo semanal (ver build_weekly_summary_html). daily_archive.json
    (raiz do repo) continua sendo o estado de trabalho interno; este
    arquivo em docs/ e so a versao exposta pro site estatico."""
    os.makedirs("docs", exist_ok=True)
    with open(RESUMO_HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False)


STATUS_FILE = "docs/status.json"


def export_status_json():
    """Publica docs/status.json - pagina de transparencia de frescor
    dos dados (docs/status.html), inspirada na pagina /status do OBM
    (obm.com.br), mas adaptada a nossa arquitetura real: la, cada
    classe de ativo tem uma defasagem propria (D-1, D-2...) porque vem
    de fontes upstream distintas; aqui o pipeline principal (noticias +
    cotacoes Brapi + insights de IA) roda tudo junto a cada ciclo, entao
    o unico numero que importa pra ele e "ultimo ciclo"."""
    status = {
        "ultimo_ciclo": datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M"),
    }
    os.makedirs("docs", exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def build_weekly_summary_html(archive):
    """Gera a pagina de resumo semanal (docs/resumo-semanal.html) com
    os ultimos 7 dias do arquivo diario acumulado. O restante do
    historico (ate 60 dias) fica disponivel via resumo_historico.json
    e e navegado client-side (agrupado em semanas) - ver o script no
    fim da pagina."""
    last_7 = archive[-7:]

    rows_html = ""
    for day in reversed(last_7):
        rows_html += (
            '<div class="resumo-card">'
            '<span class="resumo-date">' + day["date"] + "</span>"
            '<span class="resumo-total">' + str(day["total"]) + " notícias</span>"
            '<div class="resumo-bar">'
            '<span class="resumo-bar-alta" style="width:' + str(day["alta"]) + '%"></span>'
            '<span class="resumo-bar-baixa" style="width:' + str(day["baixa"]) + '%"></span>'
            "</div>"
            '<span class="resumo-legend">'
            + str(day["alta"]) + "% alta · " + str(day["baixa"]) + "% baixa · " + str(day["info"]) + "% neutro"
            "</span>"
            "</div>"
        )

    if not rows_html:
        rows_html = '<p class="resumo-empty">Ainda não há dias suficientes registrados.</p>'

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<script src='analytics.js'></script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Resumo Semanal — Antes do Sino</title>"
        "<meta name='description' content='Como o mercado se moveu nos últimos dias e semanas: volume de notícias e proporção de alta, baixa e neutro.'>"
        "<script>"
        "(function(){try{var t=localStorage.getItem('antes-do-sino-tema');if(t==='light')document.documentElement.setAttribute('data-theme','light');}catch(e){}})();"
        "</script>"
        "<link rel='stylesheet' href='design-system.css'>"
        "<style>"
        ".resumo-section{max-width:760px;}"
        ".resumo-list{display:flex;flex-direction:column;gap:var(--sp-2);}"
        ".resumo-card{"
        "display:grid;grid-template-columns:110px 1fr auto;align-items:center;gap:var(--sp-4);"
        "background:var(--surface-1);border:1px solid var(--line);border-radius:var(--r-md);"
        "padding:var(--sp-4) var(--sp-5);"
        "}"
        ".resumo-date{font-family:var(--font-mono);font-size:0.82rem;color:var(--cream);font-weight:600;}"
        ".resumo-total{font-size:0.85rem;color:var(--slate);}"
        ".resumo-bar{grid-column:1/-1;display:flex;height:6px;border-radius:100px;overflow:hidden;background:var(--surface-2);}"
        ".resumo-bar-alta{background:var(--up);height:100%;}"
        ".resumo-bar-baixa{background:var(--down);height:100%;}"
        ".resumo-legend{grid-column:1/-1;font-family:var(--font-mono);font-size:0.72rem;color:var(--slate-dim);}"
        ".resumo-empty{color:var(--slate-dim);font-size:0.9rem;}"
        ".resumo-week-card{"
        "display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--sp-3);"
        "background:var(--surface-1);border:1px solid var(--line);border-radius:var(--r-md);"
        "padding:var(--sp-4) var(--sp-5);"
        "}"
        ".resumo-week-range{font-family:var(--font-mono);font-size:0.8rem;color:var(--cream);font-weight:600;}"
        ".resumo-week-legend{font-size:0.82rem;color:var(--slate);}"
        "</style>"
        "</head><body>"
        "<nav>"
        "<div class='brand'>"
        "<svg viewBox='0 0 24 24' fill='none'><path d='M12 2v2M8.5 20a3.5 3.5 0 0 0 7 0M5 17h14l-1.4-2.1A7 7 0 0 1 16.5 11V9a4.5 4.5 0 0 0-9 0v2a7 7 0 0 1-1.1 3.9L5 17Z' stroke='currentColor' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/></svg>"
        "Antes do Sino"
        "</div>"
        "<div class='nav-right'>"
        "<button class='theme-toggle' id='theme-toggle' type='button' title='Alternar tema claro/escuro' aria-label='Alternar tema claro/escuro'>"
        "<svg class='icon-moon' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><path d='M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z'/></svg>"
        "<svg class='icon-sun' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41'/></svg>"
        "</button>"
        "<a href='https://t.me/+TobMzw-WnQhmZmIx' class='nav-cta'>Entrar no grupo grátis</a>"
        "</div>"
        "</nav>"
        "<div class='sub-nav'>"
        "<a href='index.html' class='nav-links'>"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='4' width='18' height='16' rx='2'/><path d='M3 9h18M9 9v11'/></svg>"
        "Terminal</a>"
        "<a href='calendario.html' class='nav-links'>"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='5' width='18' height='16' rx='2'/><path d='M3 10h18M8 3v4M16 3v4'/></svg>"
        "Calendário</a>"
        "<a href='mapa.html' class='nav-links'>"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='3' width='7' height='7' rx='1'/><rect x='14' y='3' width='7' height='7' rx='1'/><rect x='3' y='14' width='7' height='7' rx='1'/><rect x='14' y='14' width='7' height='7' rx='1'/></svg>"
        "Mapa de Calor</a>"
        "<a href='quant.html' class='nav-links'>"
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><path d='M3 3v18h18'/><path d='M7 15l4-5 3 3 5-7'/></svg>"
        "Quant</a>"
        "</div>"
        "<div class='hero reveal'>"
        "<span class='kicker'>Resumo semanal</span>"
        "<h1>Como o mercado<br>se moveu.</h1>"
        "<p>Volume de notícias e proporção de alta, baixa e neutro nos últimos dias — atualizado automaticamente a cada ciclo.</p>"
        "</div>"
        "<section class='resumo-section'>"
        "<div class='page-head reveal'><span class='kicker'>Esta semana</span><h2>Últimos 7 dias</h2></div>"
        "<div class='resumo-list reveal'>" + rows_html + "</div>"
        "</section>"
        "<section class='resumo-section' id='historico-section' style='display:none;'>"
        "<div class='page-head reveal'><span class='kicker'>Histórico</span><h2>Edições anteriores</h2></div>"
        "<div class='resumo-list reveal' id='historico-list'></div>"
        "</section>"
        "<footer>"
        "<span>&copy; Antes do Sino — dados públicos, não é recomendação de investimento.</span>"
        "<div style='display:flex;gap:16px;'>"
        "<a href='calendario.html'>Calendário</a>"
        "<a href='mapa.html'>Mapa de Calor</a>"
        "<a href='quant.html'>Quant</a>"
        "<a href='status.html'>Status</a>"
        "<a href='sobre.html'>Sobre</a>"
        "</div>"
        "</footer>"
        "<script>"
        "if ('IntersectionObserver' in window) {"
        "var observer = new IntersectionObserver(function (entries) {"
        "entries.forEach(function (entry) { if (entry.isIntersecting) { entry.target.classList.add('in-view'); observer.unobserve(entry.target); } });"
        "}, { threshold: 0.15 });"
        "document.querySelectorAll('.reveal').forEach(function (el) { observer.observe(el); });"
        "} else {"
        "document.querySelectorAll('.reveal').forEach(function (el) { el.classList.add('in-view'); });"
        "}"
        ""
        "fetch('resumo_historico.json').then(function(r){ return r.ok ? r.json() : []; }).then(function(historico){"
        "if (!historico || historico.length <= 7) return;"
        "var restante = historico.slice(0, historico.length - 7).reverse();"
        "var semanas = [];"
        "for (var i = 0; i < restante.length; i += 7) { semanas.push(restante.slice(i, i + 7)); }"
        "var lista = document.getElementById('historico-list');"
        "var html = '';"
        "semanas.forEach(function(dias){"
        "var totalNoticias = dias.reduce(function(s,d){ return s + d.total; }, 0);"
        "var somaPeso = function(campo){ return dias.reduce(function(s,d){ return s + (d[campo] * d.total); }, 0); };"
        "var media = function(campo){ return totalNoticias > 0 ? Math.round(somaPeso(campo) / totalNoticias) : 0; };"
        "var inicio = dias[dias.length - 1].date;"
        "var fim = dias[0].date;"
        "html += '<div class=\"resumo-week-card\">'"
        "+ '<span class=\"resumo-week-range\">' + inicio + ' a ' + fim + '</span>'"
        "+ '<span class=\"resumo-week-legend\">' + totalNoticias + ' notícias · ' + media('alta') + '% alta · ' + media('baixa') + '% baixa · ' + media('info') + '% neutro</span>'"
        "+ '</div>';"
        "});"
        "lista.innerHTML = html;"
        "document.getElementById('historico-section').style.display = '';"
        "}).catch(function(){});"
        "</script>"
        "<script src='theme.js'></script>"
        "</body></html>"
    )

    os.makedirs("docs", exist_ok=True)
    with open("docs/resumo-semanal.html", "w", encoding="utf-8") as f:
        f.write(page)


def compute_news_clusters(entries):
    """Agrupa noticias por ativo/tema em comum, e pontua cada cluster
    internamente por numero de fontes distintas, forca de sentimento e
    recorrencia - sem expor nenhum numero de indice ao usuario, so o
    resultado ja ordenado."""
    clusters = {}
    for e in entries:
        text = (e["title"] + " " + e["body"]).lower()
        for term in TICKER_MENTION_LIST:
            if _TICKER_TERM_REGEX[term].search(text):
                clusters.setdefault(term, []).append(e)

    scored = []
    for term, items in clusters.items():
        distinct_sources = len(set(i["source"] for i in items))
        non_neutral = sum(1 for i in items if i["sentiment"] != "NEUTRAL")
        recurrence = len(items)
        score = distinct_sources * 2 + non_neutral * 1.5 + recurrence
        items_sorted = sorted(items, key=lambda i: i.get("time", ""), reverse=True)
        scored.append({
            "term": term,
            "items": items_sorted,
            "distinct_sources": distinct_sources,
            "score": score,
            "representative": items_sorted[0],
        })

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


def build_signals_html(clusters, limit=5):
    """Monta os cards de 'Sinais do Dia' - as noticias que realmente
    movimentaram o mercado, rankeadas por relevancia, nao por horario."""
    if not clusters:
        return '<p style="color:var(--slate);">Ainda sem sinais suficientes hoje. Volte mais tarde.</p>'

    cards_html = ""
    for c in clusters[:limit]:
        rep = c["representative"]
        if rep["sentiment"] == "BULLISH":
            badge = '<span class="badge alta">ALTA</span>'
        elif rep["sentiment"] == "BEARISH":
            badge = '<span class="badge baixa">BAIXA</span>'
        else:
            badge = '<span class="badge info">INFO</span>'

        if c["distinct_sources"] >= 2:
            reason = "Mencionado por " + str(c["distinct_sources"]) + " fontes diferentes hoje"
        else:
            reason = "Notícia em destaque"

        link = rep.get("link", "#") or "#"

        cards_html += (
            '<div class="signal-card">'
            '<div class="card-meta">' + badge +
            '<span class="src">' + html_module.escape(rep["source"]) + "</span>"
            '<span class="time">' + rep["time"] + "</span></div>"
            "<h3>" + html_module.escape(rep["title"]) + "</h3>"
            "<p>" + html_module.escape(rep["body"]) + "</p>"
            '<span class="signal-reason">🔎 ' + reason + "</span>"
            '<div><a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a></div>'
            "</div>\n"
        )
    return cards_html


EVENTS_STATE_FILE = "events_detected.json"

SEED_EVENTS = [
    {"date": "2026-08-04", "label": "Reunião do Copom (decisão da Selic)",
     "keywords": ["copom", "selic", "juros"], "organizer": "Banco Central do Brasil",
     "why": "Define a taxa básica de juros do Brasil - afeta diretamente crédito, câmbio e a atratividade da bolsa frente à renda fixa."},
    {"date": "2026-07-29", "label": "Decisão de juros do Fed (FOMC)",
     "keywords": ["fed", "fomc", "powell", "juros americanos"], "organizer": "Federal Reserve",
     "why": "Decisão de juros nos EUA move o dólar, os yields dos Treasuries e o apetite por risco em todas as bolsas globais."},
    {"date": "2026-09-11", "label": "CPI dos EUA (inflação ao consumidor)",
     "keywords": ["cpi", "inflação americana", "consumer price index"], "organizer": "Bureau of Labor Statistics",
     "why": "Principal termômetro de inflação dos EUA - influencia diretamente as próximas decisões de juros do Fed."},
    {"date": "2026-09-15", "label": "Reunião do Copom (decisão da Selic)",
     "keywords": ["copom", "selic", "juros"], "organizer": "Banco Central do Brasil",
     "why": "Define a taxa básica de juros do Brasil - afeta diretamente crédito, câmbio e a atratividade da bolsa frente à renda fixa."},
    {"date": "2026-09-16", "label": "Decisão de juros do Fed (FOMC)",
     "keywords": ["fed", "fomc", "powell", "juros americanos"], "organizer": "Federal Reserve",
     "why": "Decisão de juros nos EUA move o dólar, os yields dos Treasuries e o apetite por risco em todas as bolsas globais."},
    {"date": "2026-10-28", "label": "Decisão de juros do Fed (FOMC)",
     "keywords": ["fed", "fomc", "powell", "juros americanos"], "organizer": "Federal Reserve",
     "why": "Decisão de juros nos EUA move o dólar, os yields dos Treasuries e o apetite por risco em todas as bolsas globais."},
    {"date": "2026-11-03", "label": "Reunião do Copom (decisão da Selic)",
     "keywords": ["copom", "selic", "juros"], "organizer": "Banco Central do Brasil",
     "why": "Define a taxa básica de juros do Brasil - afeta diretamente crédito, câmbio e a atratividade da bolsa frente à renda fixa."},
    {"date": "2026-12-08", "label": "Reunião do Copom (decisão da Selic)",
     "keywords": ["copom", "selic", "juros"], "organizer": "Banco Central do Brasil",
     "why": "Define a taxa básica de juros do Brasil - afeta diretamente crédito, câmbio e a atratividade da bolsa frente à renda fixa."},
    {"date": "2026-12-09", "label": "Decisão de juros do Fed (FOMC)",
     "keywords": ["fed", "fomc", "powell", "juros americanos"], "organizer": "Federal Reserve",
     "why": "Decisão de juros nos EUA move o dólar, os yields dos Treasuries e o apetite por risco em todas as bolsas globais."},
]


def compute_next_payroll_dates(count=3):
    """O Payroll dos EUA (Employment Situation) e publicado sempre na
    primeira sexta-feira de cada mes - regra fixa que permite calcular
    as proximas datas sem depender de atualizacao manual, diferente de
    Copom/Fed (definidos por comite, exigem consulta ao calendario
    oficial de tempos em tempos)."""
    results = []
    today = datetime.now(BR_TZ).date()
    year, month = today.year, today.month

    for _ in range(count + 2):
        first_day = datetime(year, month, 1).date()
        weekday = first_day.weekday()
        days_until_friday = (4 - weekday) % 7
        first_friday = first_day + timedelta(days=days_until_friday)

        if first_friday >= today:
            results.append(first_friday)

        month += 1
        if month > 12:
            month = 1
            year += 1

        if len(results) >= count:
            break

    events = []
    for d in results[:count]:
        events.append({
            "date": d.strftime("%Y-%m-%d"),
            "label": "Payroll dos EUA (Employment Situation)",
            "keywords": ["payroll", "empregos nos eua", "employment situation"],
            "organizer": "Bureau of Labor Statistics",
            "why": "O relatório de emprego mais observado dos EUA - surpresas aqui costumam mover fortemente o dólar e as expectativas de juros do Fed.",
        })
    return events


def load_events_state():
    if os.path.exists(EVENTS_STATE_FILE):
        try:
            with open(EVENTS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_extraction_date": "", "events": []}
    return {"last_extraction_date": "", "events": []}


def save_events_state(state):
    with open(EVENTS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def guess_event_organizer(label, keywords):
    """Heuristica simples para o campo organizer do schema.org Event -
    reconhece organizadores conhecidos de eventos recorrentes; para
    eventos genericos extraidos automaticamente, usa o proprio site
    como fonte de cobertura (nao como organizador do evento real)."""
    text = (label + " " + " ".join(keywords)).lower()
    if "copom" in text or "selic" in text:
        return "Banco Central do Brasil"
    if "fed" in text or "fomc" in text:
        return "Federal Reserve"
    return "Antes do Sino (cobertura)"


def extract_events_from_news(entries_today):
    """Usa a Groq para ler as manchetes do dia e identificar mencoes a
    eventos futuros especificos (reunioes, decisoes, divulgacoes) com
    data conhecida - permitindo que a secao de eventos se atualize
    sozinha, sem precisar de aviso manual. Tambem extrai palavras-chave
    associadas, necessarias para depois vincular noticias ao evento."""
    if not USE_AI or not entries_today:
        return []

    headlines_text = ""
    for e in entries_today[:20]:
        headlines_text += "- " + e["title"] + "\n"

    prompt = (
        "Leia as manchetes de noticias de mercado financeiro abaixo e identifique "
        "SOMENTE eventos futuros especificos e com data conhecida (reunioes de bancos "
        "centrais, decisoes de juros, divulgacao de resultados, eleicoes, feriados de "
        "mercado, etc). Ignore qualquer noticia que nao mencione uma data futura clara.\n\n"
        "Manchetes:\n" + headlines_text + "\n\n"
        "Responda APENAS em JSON plano, uma lista, sem markdown. Formato exato:\n"
        '[{"date": "AAAA-MM-DD", "label": "Descricao curta do evento", '
        '"keywords": ["palavra1", "palavra2"], "why": "Frase curta explicando por que '
        'esse evento merece atencao do mercado"}]\n\n'
        "O campo keywords deve conter 2 a 4 termos curtos (em portugues, minusculas) "
        "que apareceriam em noticias relacionadas a esse evento, para permitir "
        "encontrar essas noticias depois. O campo why deve ter no maximo 140 caracteres, "
        "em portugues, explicando o impacto esperado no mercado. Se nao houver nenhum "
        "evento futuro claro e com data especifica mencionada, responda apenas: []"
    )

    try:
        raw_response = ask_groq(prompt, purpose="analysis")
        raw_response = re.sub(r"```json|```", "", raw_response).strip()
        parsed = json.loads(raw_response)
        if not isinstance(parsed, list):
            return []
        valid = []
        for item in parsed:
            try:
                datetime.strptime(item["date"], "%Y-%m-%d")
                keywords = item.get("keywords", [])
                if not isinstance(keywords, list):
                    keywords = []
                why_text = item.get("why", "")
                if not isinstance(why_text, str):
                    why_text = ""
                valid.append({
                    "date": item["date"],
                    "label": item["label"],
                    "keywords": [str(k).lower() for k in keywords][:4],
                    "why": truncate_text_clean(why_text, 140),
                })
            except Exception:
                continue
        return valid
    except Exception as e:
        print("Erro ao extrair eventos (Groq): " + str(e))
        return []


def update_events_registry(entries_today):
    """Roda a extracao de eventos uma vez por dia, mescla com o que ja
    esta registrado, e descarta eventos cuja data ja passou - mantendo
    a secao sempre atualizada sozinha."""
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    state = load_events_state()

    if state.get("last_extraction_date") != today_str:
        new_events = extract_events_from_news(entries_today)
        existing = state.get("events", [])

        existing_labels = set(e["label"].lower().strip() for e in existing)
        for ev in new_events:
            if ev["label"].lower().strip() not in existing_labels:
                existing.append(ev)
                existing_labels.add(ev["label"].lower().strip())

        today_date = datetime.now(BR_TZ).date()
        retention_cutoff = today_date - timedelta(days=2)
        existing = [
            e for e in existing
            if datetime.strptime(e["date"], "%Y-%m-%d").date() >= retention_cutoff
        ]

        state["events"] = existing
        state["last_extraction_date"] = today_str
        save_events_state(state)

    return state.get("events", [])


def build_events_html(entries_today, all_history=None):
    """Mostra eventos vindos do registro automatico (extraido das
    proprias noticias) combinado com a lista minima de referencia -
    nunca forca conteudo vazio. Quando o evento ja tem volume
    suficiente para ter pagina propria gerada, o rotulo vira um link
    direto para ela."""
    if all_history is None:
        all_history = entries_today

    today = datetime.now(BR_TZ).date()

    registry = update_events_registry(entries_today)

    all_events = list(SEED_EVENTS) + compute_next_payroll_dates(3)
    seed_labels = set(e["label"].lower().strip() + e["date"] for e in all_events)
    for ev in registry:
        key = ev["label"].lower().strip() + ev.get("date", "")
        if key not in seed_labels:
            all_events.append(ev)

    relevant_events = []
    for ev in all_events:
        try:
            event_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            days_away = (event_date - today).days
        except Exception:
            continue
        if 0 <= days_away <= 14:
            relevant_events.append((ev, days_away))

    relevant_events.sort(key=lambda pair: pair[1])

    if not relevant_events:
        return ""

    events_html = ""
    for ev, days_away in relevant_events:
        if days_away == 0:
            countdown = "É hoje"
        elif days_away == 1:
            countdown = "Amanhã"
        else:
            countdown = "Em " + str(days_away) + " dias"
        display_date = datetime.strptime(ev["date"], "%Y-%m-%d").strftime("%d/%m/%Y")

        label_html = html_module.escape(ev["label"])

        why_text = ev.get("why", "")
        why_html = ""
        if why_text:
            why_html = "<p style='color:var(--slate);font-size:0.82rem;margin-top:4px;'>" + html_module.escape(why_text) + "</p>"

        events_html += (
            '<div class="event-item" style="flex-wrap:wrap;align-items:flex-start;">'
            '<span class="event-countdown">' + countdown + "</span>"
            "<div style='flex-grow:1;'>"
            '<span class="event-label">' + label_html + "</span>"
            + why_html +
            "</div>"
            '<span class="event-date">' + display_date + "</span>"
            "</div>"
        )

    return (
        '<section class="events-section"><div class="section-head">'
        '<span class="kicker">No radar</span>'
        "<h2>Eventos chegando</h2>"
        "</div>"
        '<div class="events-list">' + events_html + "</div>"
        "</section>"
    )


CATALYST_RADAR_JSON_PATH = "docs/eventos_radar.json"


def build_catalyst_radar_json(combined_events):
    """Serializa os proximos 14 dias de eventos conhecidos (SEED_EVENTS
    + registro extraido automaticamente das manchetes via
    update_events_registry/extract_events_from_news, ja calculado por
    quem chama) em docs/eventos_radar.json - lido pelo card
    'Catalisadores no radar' do /calendario.html via fetch no
    navegador. Complementa o widget generico do TradingView com
    eventos especificos (ex: resultado de uma empresa) que a IA
    identificou nas proprias noticias que cobrimos."""
    today = datetime.now(BR_TZ).date()
    all_events = list(combined_events) + compute_next_payroll_dates(3)

    seen = set()
    relevantes = []
    for ev in all_events:
        try:
            event_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        days_away = (event_date - today).days
        if not (0 <= days_away <= 14):
            continue
        key = ev["label"].strip().lower() + ev["date"]
        if key in seen:
            continue
        seen.add(key)
        relevantes.append({
            "date": ev["date"],
            "label": ev["label"],
            "why": ev.get("why", ""),
            "days_away": days_away,
        })

    relevantes.sort(key=lambda e: e["days_away"])

    os.makedirs("docs", exist_ok=True)
    with open(CATALYST_RADAR_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(relevantes, f, ensure_ascii=False)
    return relevantes


def build_since_visit_data_json(entries_today):
    """Monta um JSON leve com as noticias de hoje (titulo, hora, sentimento)
    para o JavaScript no navegador comparar com o localStorage do
    visitante e calcular 'o que mudou desde sua ultima visita' - sem
    nenhum backend, so client-side."""
    data = []
    for e in entries_today:
        try:
            iso_dt = e["date"] + "T" + e["time"] + ":00-03:00"
        except Exception:
            continue
        data.append({
            "title": e["title"],
            "sentiment": e["sentiment"],
            "datetime": iso_dt,
        })
    return json.dumps(data, ensure_ascii=False)


ASSET_PROFILES = [
    {"slug": "petr4", "label": "Petrobras (PETR4)", "terms": ["petr4", "petr3", "petrobras"],
     "group": "commodities_br", "quote_ticker": "PETR4",
     "why": "Petrobras é uma das maiores participações do Ibovespa - seus movimentos costumam influenciar o índice como um todo."},
    {"slug": "vale3", "label": "Vale (VALE3)", "terms": ["vale3", "vale"],
     "group": "commodities_br", "quote_ticker": "VALE3",
     "why": "Vale é a maior mineradora do Ibovespa e altamente sensível ao preço do minério de ferro na China."},
    {"slug": "itub4", "label": "Itaú (ITUB4)", "terms": ["itub4", "itau", "itaú"],
     "group": "financeiro_br", "quote_ticker": "ITUB4",
     "why": "Itaú é o maior banco privado do país - seus resultados refletem o apetite de crédito da economia brasileira."},
    {"slug": "b3sa3", "label": "B3 (B3SA3)", "terms": ["b3sa3"],
     "group": "financeiro_br", "quote_ticker": "B3SA3",
     "why": "A própria bolsa brasileira - seu desempenho reflete o volume de negociação do mercado como um todo."},
    {"slug": "bbas3", "label": "Banco do Brasil (BBAS3)", "terms": ["bbas3", "banco do brasil"],
     "group": "financeiro_br", "quote_ticker": "BBAS3",
     "why": "Maior banco público do país, com forte exposição ao crédito agrícola e à política de juros."},
    {"slug": "wege3", "label": "WEG (WEGE3)", "terms": ["wege3", "weg"],
     "group": "industrial_br", "quote_ticker": "WEGE3",
     "why": "Uma das poucas industrias brasileiras com relevância global - termômetro do setor de bens de capital."},
    {"slug": "aapl", "label": "Apple (AAPL)", "terms": ["aapl", "apple"],
     "group": "tech_us", "quote_ticker": "AAPL",
     "why": "Uma das empresas mais valiosas do mundo - seus resultados costumam mover o sentimento de toda a bolsa americana."},
    {"slug": "tsla", "label": "Tesla (TSLA)", "terms": ["tsla", "tesla"],
     "group": "tech_us", "quote_ticker": "TSLA",
     "why": "Referência do setor de veículos elétricos, com volatilidade acima da média entre as big techs."},
    {"slug": "nvda", "label": "Nvidia (NVDA)", "terms": ["nvda", "nvidia"],
     "group": "tech_us", "quote_ticker": "NVDA",
     "why": "Líder em chips de inteligência artificial - hoje uma das ações mais influentes do mercado americano."},
    {"slug": "msft", "label": "Microsoft (MSFT)", "terms": ["msft", "microsoft"],
     "group": "tech_us", "quote_ticker": "MSFT",
     "why": "Gigante de tecnologia com forte exposição a nuvem e IA - peso relevante nos índices americanos."},
]

ASSET_ARCHIVE_FILE = "asset_archive.json"


def load_asset_archive():
    if os.path.exists(ASSET_ARCHIVE_FILE):
        try:
            with open(ASSET_ARCHIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_asset_archive(archive):
    with open(ASSET_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False)


def match_asset_terms(entry, terms):
    text = (entry["title"] + " " + entry["body"]).lower()
    for term in terms:
        if re.search(r"\b" + re.escape(term) + r"\b", text):
            return True
    return False


ASSET_RECENT_WINDOW_HOURS = 48


def get_asset_entries(all_history, terms):
    return [e for e in all_history if match_asset_terms(e, terms)]


def get_asset_entries_recent(all_history, terms, hours=ASSET_RECENT_WINDOW_HOURS):
    """Filtra noticias de um ativo dentro de uma janela de horas (usada
    para o criterio de volume minimo de qualidade)."""
    cutoff = datetime.now(BR_TZ) - timedelta(hours=hours)
    recent = []
    for e in get_asset_entries(all_history, terms):
        try:
            dt = datetime.strptime(e["date"] + " " + e["time"], "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=BR_TZ)
        except Exception:
            continue
        if dt >= cutoff:
            recent.append(e)
    return recent


def update_asset_archive_entry(slug, today_entries):
    """Guarda, uma vez por dia, a contagem de mencoes e sentimento do
    ativo - constrói historico proprio ao longo do tempo, sem backend."""
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    archive = load_asset_archive()
    asset_history = archive.get(slug, [])

    asset_history = [d for d in asset_history if d["date"] != today_str]
    alta = sum(1 for e in today_entries if e["sentiment"] == "BULLISH")
    baixa = sum(1 for e in today_entries if e["sentiment"] == "BEARISH")
    asset_history.append({
        "date": today_str,
        "count": len(today_entries),
        "alta": alta,
        "baixa": baixa,
    })
    asset_history = asset_history[-30:]

    archive[slug] = asset_history
    save_asset_archive(archive)
    return asset_history


MIN_ARCHIVE_DAYS_FOR_COMPARISON = 3


def update_all_archives(entries_today):
    """Atualiza o arquivo de TODOS os ativos e temas de uma vez, antes
    de qualquer calculo de inteligencia - desacoplado da geracao de
    paginas (que so roda para quem atinge o threshold de exibicao).
    A inteligencia precisa do quadro completo, mesmo de ativos/temas
    que ainda nao tem pagina propria."""
    asset_archive = {}
    for profile in ASSET_PROFILES:
        asset_today = get_asset_entries(entries_today, profile["terms"])
        asset_archive[profile["slug"]] = update_asset_archive_entry(profile["slug"], asset_today)

    theme_archive = {}
    for theme in THEME_PROFILES:
        theme_today = get_theme_entries(entries_today, theme)
        theme_archive[theme["slug"]] = update_theme_archive_entry(theme["slug"], theme_today)

    return asset_archive, theme_archive


def build_day_leader_map(archive):
    """Para cada data presente no arquivo, descobre qual slug teve a
    maior contagem naquele dia - base para calcular streaks de
    dominancia sem precisar guardar isso separadamente."""
    all_dates = set()
    for history in archive.values():
        for d in history:
            all_dates.add(d["date"])

    leader_by_date = {}
    for date_str in all_dates:
        best_slug = None
        best_count = 0
        for slug, history in archive.items():
            day_entry = next((d for d in history if d["date"] == date_str), None)
            count = day_entry["count"] if day_entry else 0
            if count > best_count:
                best_count = count
                best_slug = slug
        if best_count > 0:
            leader_by_date[date_str] = best_slug
    return leader_by_date


def compute_streak(leader_by_date, slug, today_str):
    """Quantos dias consecutivos, terminando hoje, esse slug foi o
    mais comentado. Retorna 0 se hoje ele nao lidera."""
    if leader_by_date.get(today_str) != slug:
        return 0
    streak = 0
    current_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    while leader_by_date.get(current_date.strftime("%Y-%m-%d")) == slug:
        streak += 1
        current_date -= timedelta(days=1)
    return streak


def compute_weekly_total(archive, slug, days=7):
    history = archive.get(slug, [])
    return sum(d["count"] for d in history[-days:])


def compute_weekly_avg_excluding_today(archive, slug, today_str, days=7):
    """Media diaria dos ultimos N dias, SEM contar hoje - usada para
    comparar o dia de hoje contra o padrao recente, evitando comparar
    um numero com ele mesmo."""
    history = [d for d in archive.get(slug, []) if d["date"] != today_str]
    recent = history[-days:]
    if not recent:
        return 0.0
    return sum(d["count"] for d in recent) / len(recent)


def compute_sentiment_pct(count, alta, baixa):
    if count == 0:
        return None
    return {
        "alta_pct": round((alta / count) * 100),
        "baixa_pct": round((baixa / count) * 100),
    }


def compute_weekly_sentiment_avg(archive, slug, today_str, days=7):
    """Media de % de alta nos ultimos N dias (excluindo hoje) - usada
    para comparar o sentimento de hoje contra o padrao recente."""
    history = [d for d in archive.get(slug, []) if d["date"] != today_str]
    recent = history[-days:]
    total_count = sum(d["count"] for d in recent)
    if total_count == 0:
        return None
    total_alta = sum(d["alta"] for d in recent)
    return (total_alta / total_count) * 100


def compute_market_intelligence(entries_today, asset_archive, theme_archive):
    """Camada matematica pura - so numeros e estruturas, nenhuma frase.
    Calculada uma unica vez por execucao e reaproveitada por Home,
    Ativos, Temas e Eventos."""
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    total_relevant_today = len(entries_today)

    archive_days_available = max(
        (len(h) for h in asset_archive.values()), default=0
    )
    has_enough_history = archive_days_available >= MIN_ARCHIVE_DAYS_FOR_COMPARISON

    asset_leader_map = build_day_leader_map(asset_archive)
    theme_leader_map = build_day_leader_map(theme_archive)

    def analyze_group(profiles, archive, leader_map, get_entries_fn, get_key_fn):
        results = {}
        for profile in profiles:
            slug = get_key_fn(profile)
            today_entries = get_entries_fn(entries_today, profile)
            count_today = len(today_entries)
            alta_today = sum(1 for e in today_entries if e["sentiment"] == "BULLISH")
            baixa_today = sum(1 for e in today_entries if e["sentiment"] == "BEARISH")

            weekly_avg = compute_weekly_avg_excluding_today(archive, slug, today_str, 7)
            weekly_total = compute_weekly_total(archive, slug, 7)
            streak = compute_streak(leader_map, slug, today_str)
            sentiment_today = compute_sentiment_pct(count_today, alta_today, baixa_today)
            sentiment_week_avg = compute_weekly_sentiment_avg(archive, slug, today_str, 7)

            is_rising = (
                weekly_avg >= 0.5 and count_today >= weekly_avg * 2 and count_today >= 2
            )
            is_disappeared = weekly_avg >= 1.0 and count_today == 0

            results[slug] = {
                "profile": profile,
                "count_today": count_today,
                "share_today": (count_today / total_relevant_today) if total_relevant_today > 0 else 0,
                "weekly_avg": weekly_avg,
                "weekly_total": weekly_total,
                "streak": streak,
                "sentiment_today": sentiment_today,
                "sentiment_week_avg": sentiment_week_avg,
                "is_rising": is_rising,
                "is_disappeared": is_disappeared,
            }
        return results

    asset_stats = analyze_group(
        ASSET_PROFILES, asset_archive, asset_leader_map,
        lambda entries, profile: get_asset_entries(entries, profile["terms"]),
        lambda profile: profile["slug"],
    )
    theme_stats = analyze_group(
        THEME_PROFILES, theme_archive, theme_leader_map,
        lambda entries, theme: get_theme_entries(entries, theme),
        lambda theme: theme["slug"],
    )

    def top_by_count_today(stats):
        candidates = [(slug, s) for slug, s in stats.items() if s["count_today"] > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda pair: pair[1]["count_today"])[0]

    def top_by_weekly_total(stats):
        candidates = [(slug, s) for slug, s in stats.items() if s["weekly_total"] > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda pair: pair[1]["weekly_total"])[0]

    return {
        "has_enough_history": has_enough_history,
        "total_relevant_today": total_relevant_today,
        "assets": asset_stats,
        "themes": theme_stats,
        "dominant_asset_today": top_by_count_today(asset_stats),
        "dominant_theme_today": top_by_count_today(theme_stats),
        "dominant_asset_week": top_by_weekly_total(asset_stats),
        "dominant_theme_week": top_by_weekly_total(theme_stats),
    }


THEME_ARCHIVE_FILE = "theme_archive.json"


def load_theme_archive():
    if os.path.exists(THEME_ARCHIVE_FILE):
        try:
            with open(THEME_ARCHIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_theme_archive(archive):
    with open(THEME_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False)


def update_theme_archive_entry(slug, today_entries):
    """Espelha update_asset_archive_entry, mas para temas - mesma
    estrutura de arquivo, mesma janela de retencao."""
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    archive = load_theme_archive()
    theme_history = archive.get(slug, [])

    theme_history = [d for d in theme_history if d["date"] != today_str]
    alta = sum(1 for e in today_entries if e["sentiment"] == "BULLISH")
    baixa = sum(1 for e in today_entries if e["sentiment"] == "BEARISH")
    theme_history.append({
        "date": today_str,
        "count": len(today_entries),
        "alta": alta,
        "baixa": baixa,
    })
    theme_history = theme_history[-30:]

    archive[slug] = theme_history
    save_theme_archive(archive)
    return theme_history


SHARE_STRONG_THRESHOLD = 0.30
SHARE_MODERATE_THRESHOLD = 0.15
STREAK_MIN_TO_MENTION = 2
SENTIMENT_SHIFT_MIN_POINTS = 15


def ordinal_pt(n):
    mapa = {1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto",
            6: "sexto", 7: "sétimo", 8: "oitavo", 9: "nono", 10: "décimo"}
    return mapa.get(n, str(n) + "º")


def narrative_name(label):
    """Remove o ticker entre parenteses (ex: '(PETR4)') do rotulo -
    usado so na camada narrativa, para o texto ler como comentario de
    analista, nao como rotulo de pagina/menu."""
    if " (" in label:
        return label.split(" (")[0]
    return label


def describe_share(label, stat, kind_word):
    """Sem numero de percentual - so a qualificacao editorial de
    quanto aquilo dominou o noticiario do dia."""
    if stat["count_today"] == 0:
        return None
    share = stat["share_today"]
    name = narrative_name(label)
    if share >= SHARE_STRONG_THRESHOLD:
        return name + " dominou o noticiário do dia."
    if share >= SHARE_MODERATE_THRESHOLD:
        return name + " teve presença relevante nas notícias de hoje."
    return None


def describe_streak(label, stat, kind_label):
    """Sempre nomeia a entidade explicitamente - nunca fica generico
    tipo 'entre os temas mais comentados' sem dizer qual."""
    streak = stat["streak"]
    name = narrative_name(label)
    if streak < STREAK_MIN_TO_MENTION:
        return None
    if streak == STREAK_MIN_TO_MENTION:
        return name + " lidera o noticiário pelo segundo dia seguido."
    return name + " lidera o noticiário pelo " + ordinal_pt(streak) + " dia seguido."


def describe_rising(label, stat):
    """Sem numero de razao (Nx) - so a qualificacao de que a atencao
    saiu do padrao normal."""
    if not stat["is_rising"]:
        return None
    name = narrative_name(label)
    return name + " voltou a ganhar atenção do mercado, bem acima do que vinha sendo comum nos últimos dias."


def describe_disappeared(label, stat):
    if not stat["is_disappeared"]:
        return None
    name = narrative_name(label)
    return name + " praticamente saiu do radar hoje, depois de aparecer com frequência nos últimos dias."


def describe_sentiment_shift(label, stat):
    """Descreve a mudanca de tom sem atribuir causa - o dado mostra
    apenas a variacao na proporcao de noticias positivas/negativas,
    nao o motivo por tras dela."""
    today = stat["sentiment_today"]
    week_avg = stat["sentiment_week_avg"]
    if today is None or week_avg is None:
        return None
    diff = today["alta_pct"] - week_avg
    name = narrative_name(label)
    if abs(diff) < SENTIMENT_SHIFT_MIN_POINTS:
        return None
    if diff > 0:
        return "O noticiário sobre " + name + " ficou mais positivo do que o normal nos últimos dias."
    return "O noticiário sobre " + name + " ficou mais negativo do que o normal nos últimos dias."


def build_market_insights(intelligence):
    """Camada narrativa - unico lugar do sistema que transforma numero
    em frase. Aplica o filtro editorial: so mantem o que ajuda o
    investidor a responder 'o que isso significa para mim'."""
    if not intelligence["has_enough_history"]:
        fallback = "Estamos acumulando histórico para gerar comparações mais confiáveis."
        return {"home": [fallback]}

    asset_stats = intelligence["assets"]
    theme_stats = intelligence["themes"]

    PRIORITY_P1 = 3
    PRIORITY_P2 = 2

    home_candidates = []

    dom_theme_slug = intelligence["dominant_theme_today"]
    if dom_theme_slug:
        theme_label = next(t["label"] for t in THEME_PROFILES if t["slug"] == dom_theme_slug)
        stat = theme_stats[dom_theme_slug]
        sentence = describe_share(theme_label, stat, "")
        if sentence:
            home_candidates.append((PRIORITY_P1, sentence))

    dom_asset_slug = intelligence["dominant_asset_today"]
    if dom_asset_slug:
        asset_label = next(p["label"] for p in ASSET_PROFILES if p["slug"] == dom_asset_slug)
        stat = asset_stats[dom_asset_slug]
        sentence = describe_share(asset_label, stat, "")
        if sentence:
            home_candidates.append((PRIORITY_P1, sentence))
        streak_sentence = describe_streak(asset_label, stat, "os ativos")
        if streak_sentence:
            home_candidates.append((PRIORITY_P2, streak_sentence))

    if dom_theme_slug:
        theme_label = next(t["label"] for t in THEME_PROFILES if t["slug"] == dom_theme_slug)
        streak_sentence = describe_streak(theme_label, theme_stats[dom_theme_slug], "os temas")
        if streak_sentence:
            home_candidates.append((PRIORITY_P2, streak_sentence))

    for profile in ASSET_PROFILES:
        stat = asset_stats[profile["slug"]]
        sentence = describe_rising(profile["label"], stat) or describe_disappeared(profile["label"], stat)
        if sentence:
            home_candidates.append((PRIORITY_P1, sentence))

    for theme in THEME_PROFILES:
        stat = theme_stats[theme["slug"]]
        sentence = describe_rising(theme["label"], stat) or describe_disappeared(theme["label"], stat)
        if sentence:
            home_candidates.append((PRIORITY_P1, sentence))

    if dom_theme_slug:
        theme_label = next(t["label"] for t in THEME_PROFILES if t["slug"] == dom_theme_slug)
        sentiment_sentence = describe_sentiment_shift(theme_label, theme_stats[dom_theme_slug])
        if sentiment_sentence:
            home_candidates.append((PRIORITY_P2, sentiment_sentence))

    home_candidates.sort(key=lambda pair: pair[0], reverse=True)
    seen = set()
    home_insights = []
    for _, sentence in home_candidates:
        if sentence not in seen:
            seen.add(sentence)
            home_insights.append(sentence)
        if len(home_insights) >= 4:
            break

    if not home_insights:
        home_insights = ["O mercado está com poucos sinais de destaque no momento - nenhum ativo ou tema se sobressaiu hoje."]

    return {"home": home_insights}


def gerar_sitemap_completo(diretorio_docs="docs"):
    """Gera/atualiza o sitemap.xml com as rotas estaticas do site -
    Terminal (home), Calendario, Mapa de Calor e Quant."""
    now_iso = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    base_url = "https://antesdosino.com.br"

    urls_xml = (
        "  <url><loc>" + base_url + "/</loc><lastmod>" + now_iso + "</lastmod></url>\n"
        "  <url><loc>" + base_url + "/calendario.html</loc><lastmod>" + now_iso + "</lastmod></url>\n"
        "  <url><loc>" + base_url + "/mapa.html</loc><lastmod>" + now_iso + "</lastmod></url>\n"
        "  <url><loc>" + base_url + "/quant.html</loc><lastmod>" + now_iso + "</lastmod></url>\n"
    )

    sitemap_xml = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n"
        + urls_xml +
        "</urlset>\n"
    )

    with open(diretorio_docs + "/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print("sitemap.xml atualizado (escaneado a partir de " + diretorio_docs + ").")


THEME_PROFILES = [
    {"slug": "copom-juros", "label": "Juros & Copom",
     "strong": ["copom", "selic", "fomc", "roberto campos neto", "jerome powell", "fed"],
     "weak": ["taxa de juros", "monetária"],
     "why": "Decisões de juros no Brasil e nos EUA afetam diretamente o custo do crédito, o câmbio e a atratividade da bolsa frente à renda fixa."},
    {"slug": "petroleo-commodities", "label": "Petróleo & Commodities",
     "strong": ["petróleo", "brent", "wti", "opep", "petrobras", "minério de ferro"],
     "weak": ["commodities"],
     "why": "Commodities pesam fortemente no Ibovespa e influenciam a inflação global - movimentos aqui se propagam para câmbio e juros."},
    {"slug": "inflacao-fiscal", "label": "Inflação & Meta Fiscal",
     "strong": ["ipca", "igp-m", "inflação", "arcabouço fiscal", "haddad"],
     "weak": ["déficit", "superávit", "meta fiscal"],
     "why": "A trajetória fiscal e a inflação são os principais termômetros da confiança dos investidores na economia brasileira."},
    {"slug": "balancos-resultados", "label": "Temporada de Balanços",
     "strong": ["balanço", "lucro líquido", "ebitda", "dividendo", "jcp", "proventos", "trimestre"],
     "weak": ["receita líquida", "receita bruta", "1tri", "2tri", "3tri", "4tri"],
     "why": "A temporada de resultados revela a saúde financeira real das empresas, movendo preços de ações de forma direta."},
    {"slug": "cambio-dolar", "label": "Câmbio & Dólar",
     "strong": ["dólar", "câmbio", "ptax", "moeda americana"],
     "weak": ["valorização", "desvalorização", "real"],
     "why": "O dólar impacta importações, inflação e o custo de dívida em moeda estrangeira das empresas brasileiras."},
]


def theme_matches(entry, theme):
    """Classificacao em 2 niveis: palavras 'strong' sao especificas o
    suficiente para classificar sozinhas. Palavras 'weak' sao termos
    genericos (ex: 'real', 'vale', 'receita') que sozinhas geram falso
    positivo (ex: 'impacto real', 'vale a pena') - so contam se houver
    2 ou mais sinais fracos no mesmo texto, reduzindo drasticamente
    ruido sem depender de lista maior de palavras-chave."""
    text = (entry["title"] + " " + entry["body"]).lower()

    for kw in theme["strong"]:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
            return True

    weak_hits = 0
    for kw in theme.get("weak", []):
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
            weak_hits += 1
    return weak_hits >= 2


def get_theme_entries(all_history, theme):
    return [e for e in all_history if theme_matches(e, theme)]


BRIEFINGS_STATE_FILE = "docs/briefings_state.json"

BR_ASSET_GROUPS = {"commodities_br", "financeiro_br", "industrial_br"}

BR_RELEVANT_KEYWORDS = [
    "ibovespa", "selic", "copom", "dolar", "cambio", "petroleo", "petrobras",
    "vale", "minerio de ferro", "juros", "b3", "real",
]


def load_briefings_state():
    if os.path.exists(BRIEFINGS_STATE_FILE):
        try:
            with open(BRIEFINGS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_evening_date": ""}
    return {"last_evening_date": ""}


def save_briefings_state(state):
    os.makedirs(os.path.dirname(BRIEFINGS_STATE_FILE), exist_ok=True)
    with open(BRIEFINGS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_send_evening_briefing():
    """Janela de 18h15 as 18h45, uma vez por dia. So dispara em dia
    util da B3 (nao fim de semana nem feriado nacional)."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_briefings_state()
    if state.get("last_evening_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (18 * 60 + 15) <= minutes <= (18 * 60 + 45)


SNAPSHOT_STATE_FILE = "docs/snapshot_state.json"


def load_snapshot_state():
    """Estado ISOLADO do Snapshot 12h00 - arquivo proprio, nunca
    compartilha ou interfere com docs/briefings_state.json."""
    if os.path.exists(SNAPSHOT_STATE_FILE):
        try:
            with open(SNAPSHOT_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_snapshot_date": ""}
    return {"last_snapshot_date": ""}


def save_snapshot_state(state):
    os.makedirs(os.path.dirname(SNAPSHOT_STATE_FILE), exist_ok=True)
    with open(SNAPSHOT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_send_market_snapshot():
    """Janela de 12h00 as 12h15, uma vez por dia. So dispara em dia
    util da B3 (nao fim de semana nem feriado nacional)."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_snapshot_state()
    if state.get("last_snapshot_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (12 * 60) <= minutes <= (12 * 60 + 15)


def build_market_snapshot_message(market_snapshot):
    """Monta a mensagem 'Snapshot 12h00' - fotografia simples do
    mercado, sem depender de noticia nenhuma. Le diretamente do
    market_snapshot ja calculado (nenhuma chamada de API aqui).

    Cada linha so aparece se o dado existir de verdade no snapshot -
    nunca inventa valor. Se uma secao inteira ficar sem nenhuma linha
    disponivel, a secao inteira e omitida (nao aparece titulo vazio)."""
    quotes_by_symbol = (market_snapshot or {}).get("quotes_by_symbol", {})
    selic = (market_snapshot or {}).get("selic")
    usd = (market_snapshot or {}).get("usd")
    bitcoin = (market_snapshot or {}).get("bitcoin")
    wti = (market_snapshot or {}).get("wti")
    treasury_10y = (market_snapshot or {}).get("treasury_10y")
    sp500 = (market_snapshot or {}).get("sp500")

    def formata_variacao(change):
        sign = "+" if change >= 0 else ""
        return sign + str(round(change, 2)) + "%"

    mercados_linhas = []
    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa is not None and ibovespa.get("change") is not None:
        mercados_linhas.append("Ibovespa: " + formata_variacao(ibovespa["change"]))
    if sp500 is not None and sp500.get("change") is not None:
        mercados_linhas.append("S&P 500: " + formata_variacao(sp500["change"]))

    cambio_linhas = []
    if usd is not None and usd.get("change") is not None:
        cambio_linhas.append("Dólar: " + formata_variacao(usd["change"]))
    if wti is not None and wti.get("change") is not None:
        cambio_linhas.append("WTI: " + formata_variacao(wti["change"]))
    if bitcoin is not None and bitcoin.get("change") is not None:
        cambio_linhas.append("Bitcoin: " + formata_variacao(bitcoin["change"]))

    juros_linhas = []
    if selic is not None:
        juros_linhas.append("CDI: " + str(selic) + "% a.a.")
    if treasury_10y is not None and treasury_10y.get("value") is not None:
        juros_linhas.append("Treasury 10Y: " + str(round(treasury_10y["value"], 2)) + "%")

    partes = ["🔔 <b>Antes do Sino | Snapshot 12h00</b>\n"]

    if mercados_linhas:
        partes.append("📈 <b>Mercados</b>\n" + "\n".join(mercados_linhas) + "\n")

    if cambio_linhas:
        partes.append("💵 <b>Câmbio e Commodities</b>\n" + "\n".join(cambio_linhas) + "\n")

    if juros_linhas:
        partes.append("🏦 <b>Juros</b>\n" + "\n".join(juros_linhas) + "\n")

    partes.append("🕛 Atualizado às 12h00")

    return "\n".join(partes)


def processar_market_snapshot_telegram(market_snapshot, telegram_bot_token, telegram_chat_id):
    """Orquestrador ISOLADO do Snapshot 12h00 - nao toca em
    Morning/Evening Briefing nem no fluxo normal de noticias.

    Parametros:
        market_snapshot: dados ja calculados no main() (compute_market_snapshot)
                 - reaproveitado aqui, zero chamada de API nova.
        telegram_bot_token / telegram_chat_id: credenciais do canal VIP.

    Comportamento:
        - So dispara na janela 12h00-12h15.
        - Enviado no maximo 1 vez por dia (controle via
          docs/snapshot_state.json, arquivo proprio e isolado).
        - Sem comentario de IA nesta primeira fase - so os dados do
          snapshot, formatados.
    """
    if not should_send_market_snapshot():
        return

    # Checkpoint engine em modo sombra (Fase 2) - roda no MESMO
    # momento do checkpoint real, mas so gera rascunho de comparacao.
    # Isolado - falha aqui nunca impede o envio real logo abaixo.
    if editorial_foundation is not None:
        try:
            editorial_foundation.run_shadow_checkpoint("snapshot")
        except Exception as e:
            print("Aviso (checkpoint sombra, isolado, nao afeta envio real): " + str(e))

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    message = build_market_snapshot_message(market_snapshot)

    if send_briefing_message(message, telegram_bot_token, telegram_chat_id):
        state = load_snapshot_state()
        state["last_snapshot_date"] = today_str
        save_snapshot_state(state)
        print("Snapshot 12h00 enviado com sucesso.")
    else:
        print("Falha ao enviar Snapshot 12h00 - sera tentado novamente no proximo ciclo dentro da janela.")


# =============================================================================
# NIGHT WRAP - fechamento do dia as 22h30, encerra a janela de operacao
# =============================================================================

NIGHT_WRAP_STATE_FILE = "docs/night_wrap_state.json"

NIGHT_WRAP_JANELA_INICIO_MINUTOS = 22 * 60 + 20
NIGHT_WRAP_JANELA_FIM_MINUTOS = 22 * 60 + 30


def load_night_wrap_state():
    """Estado ISOLADO do Night Wrap - arquivo proprio, nao interfere
    com briefings_state.json nem snapshot_state.json."""
    if os.path.exists(NIGHT_WRAP_STATE_FILE):
        try:
            with open(NIGHT_WRAP_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_night_wrap_date": ""}
    return {"last_night_wrap_date": ""}


def save_night_wrap_state(state):
    os.makedirs(os.path.dirname(NIGHT_WRAP_STATE_FILE), exist_ok=True)
    with open(NIGHT_WRAP_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_send_night_wrap():
    """Janela estrita de 22h20 as 22h30 (fecha exatamente junto com a
    janela de operacao do bot, 06h50-22h30) - o Night Wrap deve ser
    sempre a ULTIMA mensagem do dia, entao a janela e propositalmente
    curta e termina no mesmo minuto em que o bot para de operar. So
    dispara em dia util da B3 (nao fim de semana nem feriado
    nacional). Ver tambem a trava em main() que impede qualquer outro
    envio depois que o Night Wrap ja saiu hoje."""
    if not eh_dia_util_b3():
        return False
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_night_wrap_state()
    if state.get("last_night_wrap_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return NIGHT_WRAP_JANELA_INICIO_MINUTOS <= minutes <= NIGHT_WRAP_JANELA_FIM_MINUTOS


def _formata_numero_br(valor, casas=2):
    """Formata numero no padrao brasileiro: milhar com ponto, decimal
    com virgula (ex: 176939.62 -> '176.939,62')."""
    texto = "{:,.{casas}f}".format(valor, casas=casas)
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def build_night_wrap_message(market_snapshot):
    """Monta a mensagem de fechamento da noite (22h30) - mesma logica
    de 'so mostra o que existe de verdade' do Snapshot 12h00. Le
    diretamente do market_snapshot ja calculado, zero chamada de API
    nova. Usa <pre> para garantir alinhamento monoespacado no Telegram."""
    quotes_by_symbol = (market_snapshot or {}).get("quotes_by_symbol", {}) or {}
    usd = (market_snapshot or {}).get("usd")
    wti = (market_snapshot or {}).get("wti")
    sp500 = (market_snapshot or {}).get("sp500")

    def formata_variacao(change):
        seta = "▲" if change >= 0 else "▼"
        sinal = "+" if change >= 0 else ""
        return seta + " " + sinal + str(round(change, 2)).replace(".", ",") + "%"

    linhas = []

    ibovespa = quotes_by_symbol.get("^BVSP")
    if ibovespa and ibovespa.get("price") is not None and ibovespa.get("change") is not None:
        linhas.append(("IBOV", _formata_numero_br(ibovespa["price"]), formata_variacao(ibovespa["change"])))

    if sp500 and sp500.get("value") is not None and sp500.get("change") is not None:
        linhas.append(("S&P 500", _formata_numero_br(sp500["value"]), formata_variacao(sp500["change"])))

    if usd and usd.get("price") is not None and usd.get("change") is not None:
        linhas.append(("USD/BRL", _formata_numero_br(usd["price"]), formata_variacao(usd["change"])))

    if wti and wti.get("value") is not None and wti.get("change") is not None:
        linhas.append(("WTI", _formata_numero_br(wti["value"]), formata_variacao(wti["change"])))

    agora = datetime.now(BR_TZ)
    data_str = agora.strftime("%d/%m")

    partes = ["🌙 <b>Antes do Sino | Fechamento da Noite — " + data_str + " 22h30</b>"]

    if linhas:
        maior_label = max(len(l[0]) for l in linhas)
        tabela = "<b>Fechamento do dia</b>\n<pre>"
        for label, valor, variacao in linhas:
            tabela += label.ljust(maior_label + 2) + valor.rjust(12) + "   " + variacao + "\n"
        tabela += "</pre>"
        partes.append(tabela)
    else:
        partes.append("Dados de fechamento indisponíveis no momento.")

    partes.append("<i>Boa noite e até amanhã. 06h50 BRT.</i>")
    partes.append("📰 Antes do Sino")

    return "\n\n".join(partes)


def processar_night_wrap_telegram(market_snapshot, telegram_bot_token, telegram_chat_id):
    """Orquestrador ISOLADO do Night Wrap - nao toca em nenhum outro
    fluxo. So dispara na janela 22h00-22h30, 1x por dia."""
    if not should_send_night_wrap():
        return

    if editorial_foundation is not None:
        try:
            editorial_foundation.run_shadow_checkpoint("night_wrap")
        except Exception as e:
            print("Aviso (checkpoint sombra, isolado, nao afeta envio real): " + str(e))

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    message = build_night_wrap_message(market_snapshot)

    if send_briefing_message(message, telegram_bot_token, telegram_chat_id):
        state = load_night_wrap_state()
        state["last_night_wrap_date"] = today_str
        save_night_wrap_state(state)
        print("Night Wrap (22h30) enviado com sucesso.")
    else:
        print("Falha ao enviar Night Wrap - sera tentado novamente no proximo ciclo dentro da janela.")


def get_brazil_relevant_entries(entries):
    """Filtra apenas noticias com foco no mercado brasileiro: fontes ja
    nacionais (PORTUGUESE_SOURCES), OU qualquer fonte que mencione um
    vetor que impacta diretamente o Ibovespa/Real (petroleo, dolar,
    Vale, Petrobras, juros, etc), conforme a diretriz editorial."""
    relevant = []
    for e in entries:
        if e.get("source") in PORTUGUESE_SOURCES:
            relevant.append(e)
            continue
        text = (e["title"] + " " + e["body"]).lower()
        if any(kw in text for kw in BR_RELEVANT_KEYWORDS):
            relevant.append(e)
    return relevant


def is_event_brazil_focused(event):
    """Heuristica simples para excluir eventos claramente internacionais
    (Fed/FOMC) da secao de eventos do Brasil dos briefings."""
    text = (event.get("label", "") + " " + " ".join(event.get("keywords", []))).lower()
    if "fed" in text or "fomc" in text or "federal reserve" in text:
        return False
    return True


def build_ibovespa_dolar_lines(market_snapshot):
    """Linhas 'Ibovespa: [pts] ([var%])' e 'Dólar Comercial: R$ [valor]
    ([var%])' do Fechamento B3, com dado real do snapshot ja calculado.
    Omite a linha inteira quando o dado nao esta disponivel - nunca
    inventa numero (nao ha fonte gratuita de volume negociado da B3
    hoje, entao esse campo simplesmente nao aparece)."""
    if not market_snapshot:
        return []
    lines = []
    quotes_by_symbol = market_snapshot.get("quotes_by_symbol", {})
    ibov = quotes_by_symbol.get("^BVSP")
    if ibov and ibov.get("price") is not None and ibov.get("change") is not None:
        sinal = "+" if ibov["change"] >= 0 else ""
        lines.append("• Ibovespa: " + str(round(ibov["price"])) + " pts (" + sinal + str(round(ibov["change"], 2)) + "%)")
    usd = market_snapshot.get("usd")
    if usd and usd.get("price") is not None and usd.get("change") is not None:
        sinal = "+" if usd["change"] >= 0 else ""
        lines.append("• Dólar Comercial: R$ " + str(round(usd["price"], 2)) + " (" + sinal + str(round(usd["change"], 2)) + "%)")
    return lines


def build_market_movers_br(market_snapshot, limit=2):
    """Maiores altas/baixas REAIS entre as ações brasileiras
    acompanhadas (COCKPIT_TICKERS, exclui o próprio índice ^BVSP). Não
    é o mercado inteiro - é o conjunto que o bot já monitora de graça -
    mas é dado 100% real, nunca estimado."""
    if not market_snapshot:
        return [], []
    quotes_by_symbol = market_snapshot.get("quotes_by_symbol", {})
    movidas = []
    for symbol, q in quotes_by_symbol.items():
        if symbol == "^BVSP":
            continue
        change = q.get("change")
        if change is None:
            continue
        movidas.append((symbol, change))
    altas = sorted([par for par in movidas if par[1] > 0], key=lambda par: par[1], reverse=True)[:limit]
    baixas = sorted([par for par in movidas if par[1] < 0], key=lambda par: par[1])[:limit]
    return altas, baixas


def get_br_asset_radar(entries, market_snapshot=None, limit=3):
    """Retorna os papeis da B3 (excluindo big techs americanas) em
    destaque, com DUAS fontes possiveis, nessa ordem de preferencia:

    1. Destaque por NOTICIA - densidade de mencoes recentes (fonte
       original, mais editorial, preferida quando disponivel).
    2. Destaque por PRECO - maior variacao percentual do dia, usando o
       snapshot de mercado (fetch_cockpit_quotes) - fallback usado
       SOMENTE quando nao ha mencao suficiente em noticia, para o
       radar nunca ficar vazio so por falta de cobertura editorial.

    Cada item retornado indica explicitamente qual fonte foi usada,
    no campo 'source' ('noticia' ou 'preco')."""
    counts = []
    for profile in ASSET_PROFILES:
        if profile["group"] not in BR_ASSET_GROUPS:
            continue
        count = len(get_asset_entries(entries, profile["terms"]))
        if count > 0:
            counts.append((profile, count))
    counts.sort(key=lambda pair: pair[1], reverse=True)

    if counts:
        return [{"profile": pair[0], "source": "noticia"} for pair in counts[:limit]]

    # Fallback: sem destaque editorial suficiente - usa movimento de
    # preco real do snapshot de mercado, se disponivel.
    if not market_snapshot:
        return []

    quotes_by_symbol = market_snapshot.get("quotes_by_symbol", {})
    price_moves = []
    for profile in ASSET_PROFILES:
        if profile["group"] not in BR_ASSET_GROUPS:
            continue
        ticker = profile.get("quote_ticker", "")
        q = quotes_by_symbol.get(ticker)
        if q is None or q.get("change") is None:
            continue
        price_moves.append((profile, q["change"]))

    price_moves.sort(key=lambda pair: abs(pair[1]), reverse=True)
    return [{"profile": pair[0], "source": "preco", "change": pair[1]} for pair in price_moves[:limit]]


def summarize_briefing_with_ai(entries, tipo):
    """Uma unica chamada a Groq para gerar a sintese executiva do
    briefing (1 a 2 frases), focada no mercado brasileiro. 'tipo' e
    'abertura' ou 'fechamento'."""
    if not USE_AI or not entries:
        return "Sem dados suficientes para uma sintese hoje."

    headlines_text = ""
    for e in entries[:15]:
        headlines_text += "- " + e["title"] + "\n"

    trava_anti_alucinacao = (
        "Use SOMENTE as manchetes fornecidas abaixo - nunca invente fato, numero ou "
        "evento que nao esteja nelas. Nunca invente relacao causal entre manchetes "
        "que nao tem conexao explicita, e nunca conecte 2 manchetes so porque estao "
        "na mesma lista - elas podem ser sobre empresas, paises ou temas totalmente "
        "independentes. So afirme que um acontecimento influenciou o outro se as "
        "proprias manchetes realmente sustentarem essa leitura. Prefira uma resposta "
        "mais generica e honesta a forcar uma narrativa conectada que os dados nao "
        "sustentam."
    )

    if tipo == "abertura":
        instrucao = (
            "Escreva uma sintese de 1 a 2 frases sobre o principal vetor esperado para "
            "o pregao de hoje na B3 (Ibovespa), com base nas manchetes abaixo. Foque "
            "em commodities, dolar, noticiario politico/fiscal ou balancos locais. "
            "Responda em portugues do Brasil, texto simples, sem markdown, sem aspas.\n\n"
            + trava_anti_alucinacao
        )
    else:
        instrucao = (
            "Escreva uma sintese de 1 a 2 frases sobre o que moveu o pregao de hoje na "
            "B3 (Ibovespa), com base nas manchetes abaixo. Responda em portugues do "
            "Brasil, texto simples, sem markdown, sem aspas.\n\n"
            + trava_anti_alucinacao
        )

    prompt = instrucao + "\n\nManchetes:\n" + headlines_text

    try:
        response = ask_groq(prompt, purpose="generation")
        return response.strip().strip('"')
    except Exception as e:
        print("Erro ao gerar sintese do briefing (Groq): " + str(e))
        return "Sintese indisponivel no momento - confira as noticias completas no site."


def build_sellside_synopsis(entries):
    """Sintese do Fechamento B3 em formato estilo research (tese +
    catalisadores + riscos) no lugar do paragrafo solto de
    summarize_briefing_with_ai. Mesma trava anti-alucinacao: usa
    SOMENTE as manchetes fornecidas, nunca inventa numero ou conexao
    causal entre noticias sem relacao explicita. Retorna None se a IA
    falhar ou a resposta vier fora do formato esperado - quem chama
    cai de volta no paragrafo simples (fallback seguro, nunca deixa a
    secao vazia)."""
    if not USE_AI or not entries:
        return None

    headlines_text = ""
    for e in entries[:15]:
        headlines_text += "- " + e["title"] + "\n"

    trava_anti_alucinacao = (
        "Use SOMENTE as manchetes fornecidas abaixo - nunca invente fato, numero ou "
        "evento que nao esteja nelas. Nunca invente relacao causal entre manchetes "
        "que nao tem conexao explicita, e nunca conecte 2 manchetes so porque estao "
        "na mesma lista - elas podem ser sobre empresas, paises ou temas totalmente "
        "independentes. So afirme que um acontecimento influenciou o outro se as "
        "proprias manchetes realmente sustentarem essa leitura. Prefira uma resposta "
        "mais generica e honesta a forcar uma narrativa conectada que os dados nao "
        "sustentam."
    )

    instrucao = (
        "Escreva uma leitura estruturada do pregao de hoje na B3 (Ibovespa), com base "
        "nas manchetes abaixo, em 3 partes:\n"
        "1. tese: 1 frase com a leitura principal do dia.\n"
        "2. catalisadores: ate 2 fatores especificos que moveram o mercado hoje, cada "
        "um em 1 frase curta. Lista vazia se as manchetes nao sustentarem nenhum.\n"
        "3. riscos: ate 2 riscos ou pontos de atencao para os proximos dias, cada um "
        "em 1 frase curta - so inclua se as manchetes realmente sustentarem isso, "
        "senao deixe a lista vazia.\n\n"
        + trava_anti_alucinacao + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, sem texto antes ou depois, no "
        "formato exato:\n"
        '{"tese": "...", "catalisadores": ["...", "..."], "riscos": ["...", "..."]}\n\n'
        "Manchetes:\n" + headlines_text
    )

    try:
        raw_response = ask_groq(instrucao, purpose="generation")
        parsed = extract_json_object(raw_response)
        if not isinstance(parsed, dict):
            return None

        tese = parsed.get("tese")
        catalisadores_raw = parsed.get("catalisadores")
        riscos_raw = parsed.get("riscos")

        result = {
            "tese": sanitize_message_text(tese) if isinstance(tese, str) else "",
            "catalisadores": [
                sanitize_message_text(c) for c in catalisadores_raw
                if isinstance(c, str) and c.strip()
            ] if isinstance(catalisadores_raw, list) else [],
            "riscos": [
                sanitize_message_text(r) for r in riscos_raw
                if isinstance(r, str) and r.strip()
            ] if isinstance(riscos_raw, list) else [],
        }
        if not result["tese"]:
            return None
        return result
    except Exception as e:
        print("Erro ao gerar sintese sell-side do Fechamento B3 (Groq, fallback seguro): " + str(e))
        return None


def build_evening_briefing_message(entries_today, eventos, market_snapshot=None):
    """Monta o texto do Fechamento B3 (Evening Briefing). Ibovespa/Dólar
    e as maiores altas/baixas usam SOMENTE dado real do snapshot -
    nunca inventa numero; volume negociado da B3 nao tem fonte gratuita
    hoje, entao simplesmente nao aparece."""
    tomorrow_iso = (datetime.now(BR_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

    br_entries = get_brazil_relevant_entries(entries_today)
    # Resiliencia: mesma logica do Morning - amplia a rede em dia fraco
    # em vez de deixar sintese/pautas caírem direto no fallback generico.
    if len(br_entries) < 3 and entries_today:
        br_entries = entries_today

    sellside = build_sellside_synopsis(br_entries)

    clusters = compute_news_clusters(br_entries)
    top_pautas = ""
    if clusters:
        for c in clusters[:3]:
            top_pautas += "• " + c["representative"]["title"] + "\n"
    else:
        top_pautas = "Sem pautas de grande destaque hoje.\n"

    eventos_amanha = [
        ev for ev in eventos
        if ev.get("date") == tomorrow_iso and is_event_brazil_focused(ev)
    ][:3]

    eventos_texto = ""
    if eventos_amanha:
        for ev in eventos_amanha:
            eventos_texto += "• " + ev["label"] + "\n"
    else:
        eventos_texto = "Sem eventos de grande destaque previstos para amanha.\n"

    partes = ["🌆 <b>FECHAMENTO B3</b>", ""]

    resumo_linhas = build_ibovespa_dolar_lines(market_snapshot)
    if resumo_linhas:
        partes.append("\n".join(resumo_linhas))
        partes.append("")

    altas, baixas = build_market_movers_br(market_snapshot)
    if altas:
        partes.append("🟢 <b>Maiores Altas</b>")
        partes.append("\n".join("• #" + s + ": +" + str(round(c, 2)) + "%" for s, c in altas))
        partes.append("")
    if baixas:
        partes.append("🔴 <b>Maiores Baixas</b>")
        partes.append("\n".join("• #" + s + ": " + str(round(c, 2)) + "%" for s, c in baixas))
        partes.append("")

    partes.append("📊 <b>O dia em resumo</b>")
    if sellside:
        partes.append("💡 <i>" + html_module.escape(sellside["tese"], quote=False) + "</i>")
        if sellside["catalisadores"]:
            partes.append("")
            partes.append("🎯 <b>Catalisadores</b>")
            partes.append("\n".join("• " + html_module.escape(c, quote=False) for c in sellside["catalisadores"]))
        if sellside["riscos"]:
            partes.append("")
            partes.append("⚠️ <b>Riscos</b>")
            partes.append("\n".join("• " + html_module.escape(r, quote=False) for r in sellside["riscos"]))
    else:
        # Fallback seguro: sintese sell-side falhou (IA fora do ar, JSON
        # invalido) - volta pro paragrafo simples de sempre, pra nunca
        # deixar essa secao vazia.
        partes.append(html_module.escape(summarize_briefing_with_ai(br_entries, "fechamento"), quote=False))
    partes.append("")
    partes.append("🔥 <b>O que movimentou o mercado</b>")
    partes.append(html_module.escape(top_pautas, quote=False))
    partes.append("📅 <b>Amanhã no radar</b>")
    partes.append(html_module.escape(eventos_texto, quote=False))
    partes.append("⚡ Antes do Sino")

    return "\n".join(partes)


def send_briefing_message(text, telegram_bot_token, telegram_chat_id):
    """Envio de mensagem parametrizado (token/chat id explicitos),
    independente das variaveis globais do bot principal."""
    url = "https://api.telegram.org/bot" + telegram_bot_token + "/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Erro Telegram (briefing, status " + str(r.status_code) + "): " + r.text)
        return r.status_code == 200
    except Exception as e:
        print("Erro Telegram (briefing): " + str(e))
        return False


def processar_briefings_telegram(noticias, eventos, telegram_bot_token, telegram_chat_id, market_snapshot=None):
    """Funcao principal e modular dos briefings automaticos.

    Parametros:
        noticias: lista completa de noticias ja processadas pelo bot.
        eventos: lista combinada de eventos (SEED_EVENTS + registro
                 automatico extraido de events_detected.json).
        telegram_bot_token / telegram_chat_id: credenciais do canal VIP.
        market_snapshot: dados de mercado ja calculados no main()
                 (compute_market_snapshot) - reaproveitado aqui, nao
                 gera nenhuma chamada de API adicional.

    Comportamento:
        - So dispara dentro da janela de horario correspondente
          (18h15-18h45).
        - Enviado no maximo 1 vez por dia (controle via
          docs/briefings_state.json).
        - Foco editorial 100% Brasil, conforme diretriz do projeto.
    """
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in noticias if e.get("date") == today_str]
    state = load_briefings_state()

    if should_send_evening_briefing():
        if editorial_foundation is not None:
            try:
                editorial_foundation.run_shadow_checkpoint("evening_briefing")
            except Exception as e:
                print("Aviso (checkpoint sombra, isolado, nao afeta envio real): " + str(e))

        message = build_evening_briefing_message(entries_today, eventos, market_snapshot)
        if send_briefing_message(message, telegram_bot_token, telegram_chat_id):
            state["last_evening_date"] = today_str
            save_briefings_state(state)
            print("Evening Briefing enviado com sucesso.")
        else:
            print("Falha ao enviar Evening Briefing - sera tentado novamente no proximo ciclo dentro da janela.")


FORWARDED_CHANNELS = [
    "panoramajonasesteves",
    "grupobovespanews",
]

CHANNEL_DISPLAY_NAMES = {
    "panoramajonasesteves": "Panorama Jonas Esteves",
    "grupobovespanews": "Grupo Bovespa News",
}

KNOWN_AGENCIES = ["Reuters", "Bloomberg", "CNBC", "WSJ", "AFP", "Bovespa News"]

CHANNEL_STATE_FILE = "channel_state.json"


def load_channel_state():
    if os.path.exists(CHANNEL_STATE_FILE):
        try:
            with open(CHANNEL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_channel_state(state):
    with open(CHANNEL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def fetch_channel_posts(channel_username):
    """Le a versao publica web de um canal do Telegram (t.me/s/canal),
    sem precisar de login/sessao - o mesmo metodo usado no encaminhador
    original, agora integrado direto ao bot principal."""
    channel_username = channel_username.lstrip("@")
    url = "https://t.me/s/" + channel_username
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        html_content = response.text
    except Exception as e:
        print("Erro ao buscar canal " + channel_username + ": " + str(e))
        return []

    pattern = re.compile(
        r'data-post="' + re.escape(channel_username) + r'/(\d+)"(.*?)(?=data-post="' + re.escape(channel_username) + r'/\d+"|$)',
        re.DOTALL | re.IGNORECASE,
    )

    posts = []
    for match in pattern.finditer(html_content):
        post_id = int(match.group(1))
        block = match.group(2)

        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if not text_match:
            continue

        raw_text = text_match.group(1)
        raw_text = re.sub(r"<br\s*/?>", "\n", raw_text)
        clean_text = re.sub(r"<[^>]+>", "", raw_text)
        clean_text = html_module.unescape(clean_text).strip()

        if clean_text:
            posts.append({"id": post_id, "text": clean_text})

    posts.sort(key=lambda p: p["id"])
    return posts


def clean_channel_post_text(text):
    """Remove assinatura de canal e links soltos, mas preserva quebras
    de paragrafo duplas (\\n\\n) - elas sao o sinal usado para separar
    manchetes distintas dentro do mesmo post, em split_channel_post_into_items."""
    text = re.sub(r"\n*Grupo Bovespa News\s*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^\s*t\.me/\S+\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    return text


def is_agenda_bulletin(text):
    """Detecta se o post e um boletim de agenda/calendario (varios
    horarios e marcadores de secao), em vez de uma ou mais manchetes
    de noticia de verdade. Esses posts nao devem ser fatiados por
    cabecalho isolado - viram um unico envio estruturado."""
    horarios_encontrados = len(re.findall(r"\b\d{1,2}h\d{2}\b", text))
    marcador_encontrado = bool(re.search(r"🗓️|📊|📅|📌", text))
    return horarios_encontrados >= 2 or (marcador_encontrado and horarios_encontrados >= 1)


def has_minimum_content(titulo, corpo):
    """Trava anti-mensagem-vazia: descarta manchetes muito curtas
    (menos de 4 palavras, tipo cabecalhos isolados de agenda: 'Eventos',
    'Balancos') ou sem corpo E sem cara de fato completo."""
    titulo = (titulo or "").strip()
    corpo = (corpo or "").strip()

    palavras_titulo = [p for p in re.split(r"\s+", titulo) if p.strip(" 📊📈📅🗓️📌-:")]
    if len(palavras_titulo) < 4:
        return False

    if not corpo and len(palavras_titulo) < 6:
        return False

    return True


def split_channel_post_into_items(raw_text):
    """Um unico post de canal pode conter mais de uma manchete
    distinta, separadas por linha em branco. Divide o texto em itens
    individuais (titulo + corpo), garantindo que cada manchete vire
    uma mensagem propria no Telegram, nunca misturadas num so balao.
    Blocos que sao apenas o nome de uma agencia (ex: 'Reuters' isolado
    numa linha) nao viram item novo - sao anexados como atribuicao do
    item anterior. Boletins de agenda (varios horarios/marcadores) nao
    sao fatiados por cabecalho - viram um unico envio estruturado."""
    text = clean_channel_post_text(raw_text)
    if not text.strip():
        return []

    if is_agenda_bulletin(text):
        return [{
            "titulo": "Agenda do dia: principais eventos e indicadores",
            "corpo": text.strip(),
            "agency_hint": "",
        }]

    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]

    items = []
    for block in blocks:
        linhas = [l.strip() for l in block.split("\n") if l.strip()]
        if not linhas:
            continue

        if len(linhas) == 1 and linhas[0].lower() in [a.lower() for a in KNOWN_AGENCIES]:
            if items:
                items[-1]["agency_hint"] = linhas[0]
            continue

        titulo = linhas[0]
        corpo = "\n".join(linhas[1:]).strip()
        items.append({"titulo": titulo, "corpo": corpo, "agency_hint": ""})
    return items


def is_channel_bio(text):
    bio_markers = [
        "ver canal", "para entrar em contato", "@jonasesteves", "contato@",
        "taxa de apenas", "mensalmente", "garantia de 7 dias",
        "colabore com nosso trabalho", "assinando nosso servico",
        "assinando nosso serviço", "pagina de assinatura", "página de assinatura",
        "principais cotacoes do mercado financeiro", "principais cotações do mercado financeiro",
    ]
    lower_text = text.lower()
    return any(marker in lower_text for marker in bio_markers)


def detect_real_source(clean_text, clean_channel):
    for agency in KNOWN_AGENCIES:
        if agency.lower() in clean_text.lower():
            return agency
    return CHANNEL_DISPLAY_NAMES.get(clean_channel.lower(), clean_channel)


def process_forwarded_channels(sent_hashes, recent_titles):
    """Busca posts novos dos canais encaminhados, envia ao grupo do
    Telegram, e retorna uma lista de entradas no MESMO formato usado
    pelo restante do pipeline (title/body/source/sentiment/link/time/
    date) - assim esse conteudo passa a contar para os Sinais do Dia,
    paginas de ativo/tema/evento e briefings, nao so aparece no grupo.

    sent_hashes/recent_titles sao os MESMOS objetos ja usados pelo
    pipeline RSS (mutados na hora, sem precisar retornar) - garante que
    uma noticia ja publicada via RSS bloqueia o encaminhador de
    republicar a mesma pauta com fraseado de canal, e vice-versa."""
    state = load_channel_state()
    new_portal_entries = []
    has_updates = False

    for channel in FORWARDED_CHANNELS:
        clean_channel = channel.lstrip("@").strip()
        last_id = state.get(clean_channel, 0)
        posts = fetch_channel_posts(clean_channel)

        if not posts:
            print("AVISO: nenhum post encontrado para " + clean_channel)
            continue

        if last_id == 0:
            print("Inicializando " + clean_channel + " no post " + str(posts[-1]["id"]) + ".")
            state[clean_channel] = posts[-1]["id"]
            has_updates = True
            continue

        new_posts = [p for p in posts if p["id"] > last_id]
        print(
            "Canal " + clean_channel + ": ultimo processado=" + str(last_id)
            + " | mais recente disponivel=" + str(posts[-1]["id"])
            + " | novos encontrados=" + str(len(new_posts))
        )

        for post in new_posts:
            items = split_channel_post_into_items(post["text"])

            if not items:
                print("AVISO: post " + str(post["id"]) + " de " + clean_channel + " nao gerou nenhum item processavel (texto vazio apos limpeza, ou so imagem/sticker).")
                state[clean_channel] = post["id"]
                has_updates = True
                continue

            post_link = "https://t.me/" + clean_channel + "/" + str(post["id"])

            for item in items:
                titulo_puro = item["titulo"]
                corpo_puro = item["corpo"]
                agency_hint = item.get("agency_hint", "")

                item_text_check = titulo_puro + " " + corpo_puro
                if is_channel_bio(item_text_check):
                    print("Ignorado (bio do canal): " + titulo_puro[:60])
                    continue
                if not titulo_puro:
                    continue

                # Trava anti-mensagem-vazia: descarta cabecalhos isolados
                # de agenda (ex: "Eventos", "Balancos") sem conteudo real.
                if not has_minimum_content(titulo_puro, corpo_puro):
                    print("Descartado por conteudo insuficiente: " + titulo_puro[:60])
                    continue

                # Filtro obrigatorio 1: palavras negativas (crime, gossip,
                # esporte, etc) - mesmo filtro usado no RSS principal,
                # aplicado aqui via um "entry" equivalente.
                fake_entry_for_filter = {"title": titulo_puro, "summary": corpo_puro}
                if not is_relevant(fake_entry_for_filter):
                    print("Descartado pelo filtro de palavras negativas (encaminhador): " + titulo_puro[:60])
                    continue

                # Filtro de duplicidade - compara com o que ja foi
                # publicado (via RSS OU via outro canal encaminhado) nas
                # ultimas DEDUP_WINDOW_HOURS. Roda ANTES da chamada de
                # IA de proposito - descarta reposts obvios sem gastar
                # uma classificacao. Hash exato (link/titulo) primeiro,
                # depois similaridade de titulo (pega parafraseio).
                # Nao usa item_hash() aqui de proposito: ela prioriza o
                # link sobre o titulo, mas varios itens de um MESMO post
                # compartilham o mesmo post_link (split_channel_post_into_items)
                # - usar so o link colidiria o hash de itens diferentes
                # do mesmo post. Combina link+titulo pra manter unico por item.
                post_link_provisorio = "https://t.me/" + clean_channel + "/" + str(post["id"])
                h_forward = hashlib.md5((post_link_provisorio + "|" + titulo_puro).encode("utf-8")).hexdigest()
                if h_forward in sent_hashes:
                    print("Descartado por duplicidade (hash, encaminhador): " + titulo_puro[:60])
                    continue
                if is_duplicate_title(titulo_puro, recent_titles):
                    print("Descartado por duplicidade (titulo similar, encaminhador): " + titulo_puro[:60])
                    continue

                # Filtro obrigatorio 2: validacao + pontuacao de
                # materialidade via IA (mesma chamada usada no pipeline
                # RSS - Fase 2, antes o encaminhador so tinha o check
                # booleano de is_market_relevant_ai, sem nenhum limite
                # de volume). Canais ja publicam em portugues -
                # translate=False.
                ai_result = classify_news_ai(titulo_puro, corpo_puro, translate=False)
                if ai_result and ai_result.get("relevante_mercado") is False:
                    print("Descartado pela IA (nao relevante para mercado, encaminhador): " + titulo_puro[:60])
                    continue

                canal_score = ai_result.get("score_materialidade") if ai_result else None
                canal_motivo = ai_result.get("motivo_materialidade") if ai_result else None

                if agency_hint:
                    fonte_detectada = agency_hint
                else:
                    fonte_detectada = detect_real_source(item_text_check, clean_channel)
                titulo_puro = re.sub(
                    r"(?i)^\s*(reuters|bloomberg|cnbc|wsj)\s*$", "", titulo_puro
                ).strip()
                if not titulo_puro:
                    continue

                corpo_puro = re.sub(r"(?i)pontos[- ]chave:?", "", corpo_puro).strip()

                is_real_agency = fonte_detectada in KNOWN_AGENCIES
                source_for_message = fonte_detectada if is_real_agency else ""

                entry_for_format = {"title": titulo_puro, "summary": corpo_puro, "link": post_link}
                message, final_title, final_body, sentiment = format_message(
                    source_for_message, entry_for_format, ai_result
                )

                dispatch_tier = decide_dispatch_tier(canal_score)
                hashtags = extract_ticker_hashtags(titulo_puro + " " + corpo_puro)
                earnings = maybe_extract_earnings_details(
                    dispatch_tier, hashtags, titulo_puro, corpo_puro, final_title, final_body
                )

                enviado_ou_enfileirado = False
                if dispatch_tier == "breaking":
                    breaking_message = build_breaking_message(
                        title=final_title, resumo=final_body, motivo=canal_motivo,
                        sentiment=sentiment, source=source_for_message, hashtags=hashtags,
                        earnings=earnings,
                    )
                    enviado_ou_enfileirado = send_telegram_message(breaking_message)
                    if enviado_ou_enfileirado:
                        time.sleep(3)
                elif dispatch_tier == "round":
                    if editorial_foundation is not None:
                        editorial_foundation.add_to_round_queue({
                            "title": final_title,
                            "resumo": truncate_text_clean(final_body, GIRO_ITEM_MAX_CHARS) if final_body else final_title,
                            "hashtags": hashtags,
                            "source": source_for_message,
                            "score": canal_score,
                            "link": post_link,
                            "earnings": earnings,
                        })
                        enviado_ou_enfileirado = True
                    else:
                        enviado_ou_enfileirado = send_telegram_message(message)
                        if enviado_ou_enfileirado:
                            time.sleep(3)

                if enviado_ou_enfileirado:
                    now = datetime.now(BR_TZ)
                    print(("Encaminhado (breaking)" if dispatch_tier == "breaking" else "Encaminhado (giro)") + " de " + clean_channel + " (id " + str(post["id"]) + "): " + titulo_puro[:40] + "...")

                    sent_hashes.add(h_forward)
                    add_to_recent_titles(recent_titles, titulo_puro)
                    save_state(sent_hashes, recent_titles)

                    new_portal_entries.append({
                        "title": final_title,
                        "body": truncate_text_clean(final_body, 200) if final_body else "Confira mais detalhes no link abaixo.",
                        "source": CHANNEL_DISPLAY_NAMES.get(clean_channel.lower(), clean_channel),
                        "sentiment": sentiment,
                        "link": post_link,
                        "time": now.strftime("%H:%M"),
                        "date": now.strftime("%Y-%m-%d"),
                    })

                    has_updates = True

            state[clean_channel] = post["id"]
            has_updates = True

    if has_updates:
        save_channel_state(state)

    return new_portal_entries


PORTAL_HISTORY_FILE = "portal_history.json"


def load_portal_history():
    if os.path.exists(PORTAL_HISTORY_FILE):
        try:
            with open(PORTAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


PORTAL_HISTORY_RETENTION_HOURS = 72


def save_portal_history(entries):
    """Mantem o historico por IDADE (72h), nao por contagem fixa de
    itens. Um limite fixo de 30 itens purgava mencoes validas de
    ativos/temas antes mesmo da janela de 48h usada pela classificacao
    terminar - causando paginas de ativo/tema que deveriam existir
    nunca atingirem o threshold minimo."""
    cutoff = datetime.now(BR_TZ) - timedelta(hours=PORTAL_HISTORY_RETENTION_HOURS)
    trimmed = []
    for e in entries:
        try:
            dt = datetime.strptime(e["date"] + " " + e["time"], "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=BR_TZ)
        except Exception:
            continue
        if dt >= cutoff:
            trimmed.append(e)
    with open(PORTAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


def generate_portal(entries, entries_today=None, template_path="docs/template.html", output_path="docs/index.html", home_insights=None, market_snapshot=None):
    """Le o template.html, substitui os placeholders de ticker e feed
    pelos dados reais mais recentes, e salva em output_path. Desde que
    o Terminal virou a home (docs/index.html), a chamada real usa
    output_path="docs/dados-terminal.html" - um arquivo interno (nao e
    uma pagina do site, nao tem link em lugar nenhum), lido pelo
    Terminal via fetch() no cliente."""
    if not os.path.exists(template_path):
        print("AVISO: template.html nao encontrado, portal nao gerado.")
        return

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    def sentiment_class(s):
        if s == "BULLISH":
            return "alta", "ALTA"
        if s == "BEARISH":
            return "baixa", "BAIXA"
        return "info", "INFO"

    cards_html = ""
    for e in entries[:12]:
        cls, label = sentiment_class(e["sentiment"])
        link = e.get("link", "#") or "#"
        cards_html += (
            '<div class="card">'
            '<div class="card-meta"><span class="badge ' + cls + '">' + label + "</span>"
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a>'
            "</div>\n"
        )

    start_marker_c = "<!-- FEED_CARDS_START -->"
    end_marker_c = "<!-- FEED_CARDS_END -->"
    start_marker_k = "<!-- COCKPIT_START -->"
    end_marker_k = "<!-- COCKPIT_END -->"
    start_marker_s = "<!-- SIGNALS_START -->"
    end_marker_s = "<!-- SIGNALS_END -->"
    start_marker_i = "<!-- INTELLIGENCE_START -->"
    end_marker_i = "<!-- INTELLIGENCE_END -->"
    start_marker_e = "<!-- EVENTS_START -->"
    end_marker_e = "<!-- EVENTS_END -->"
    start_marker_v = "<!-- SINCE_VISIT_DATA_START -->"
    end_marker_v = "<!-- SINCE_VISIT_DATA_END -->"

    entries_for_today = entries_today if entries_today is not None else []
    clusters = compute_news_clusters(entries_for_today)

    if start_marker_c in template and end_marker_c in template:
        before = template.split(start_marker_c)[0]
        after = template.split(end_marker_c)[1]
        template = before + start_marker_c + "\n" + cards_html + end_marker_c + after

    if start_marker_k in template and end_marker_k in template:
        cockpit_html = build_cockpit_html(entries, entries_today, market_snapshot)
        before = template.split(start_marker_k)[0]
        after = template.split(end_marker_k)[1]
        template = before + start_marker_k + "\n" + cockpit_html + end_marker_k + after

    if start_marker_s in template and end_marker_s in template:
        signals_html = build_signals_html(clusters)
        before = template.split(start_marker_s)[0]
        after = template.split(end_marker_s)[1]
        template = before + start_marker_s + "\n" + signals_html + end_marker_s + after

    if start_marker_i in template and end_marker_i in template:
        intelligence_html = ""
        sentences = home_insights or []
        for s in sentences:
            intelligence_html += "<p style='color:var(--cream);font-size:1.05rem;line-height:1.6;margin-bottom:12px;'>" + html_module.escape(s) + "</p>"
        if intelligence_html:
            intelligence_section = (
                "<section><div class='section-head'>"
                "<span class='kicker'>Inteligência do dia</span>"
                "</div>"
                "<div style='max-width:720px;'>" + intelligence_html + "</div>"
                "</section>"
            )
        else:
            intelligence_section = ""
        before = template.split(start_marker_i)[0]
        after = template.split(end_marker_i)[1]
        template = before + start_marker_i + "\n" + intelligence_section + end_marker_i + after

    if start_marker_e in template and end_marker_e in template:
        events_html = build_events_html(entries_for_today, entries)
        before = template.split(start_marker_e)[0]
        after = template.split(end_marker_e)[1]
        template = before + start_marker_e + "\n" + events_html + end_marker_e + after

    if start_marker_v in template and end_marker_v in template:
        since_visit_json = build_since_visit_data_json(entries_for_today)
        before = template.split(start_marker_v)[0]
        after = template.split(end_marker_v)[1]
        script_block = (
            "<script id=\"since-visit-data\" type=\"application/json\">"
            + since_visit_json + "</script>"
        )
        template = before + start_marker_v + "\n" + script_block + "\n" + end_marker_v + after

    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")
    template = template.replace(
        '<span class="mono" id="last-updated">Atualizado automaticamente</span>',
        '<span class="mono" id="last-updated">Atualizado em ' + updated_at + "</span>",
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)

    print("Portal atualizado: " + output_path)


JANELA_OPERACAO_INICIO_MINUTOS = 6 * 60 + 50
JANELA_OPERACAO_FIM_MINUTOS = 22 * 60 + 30


def dentro_da_janela_de_operacao():
    """Guarda de seguranca - o bot so deve operar das 06h50 as 22h30
    (BR_TZ). O controle principal fica no agendamento externo
    (cron-job.org), mas essa checagem evita processamento (e consumo
    de API) caso o cron dispare fora da janela por qualquer motivo."""
    agora = datetime.now(BR_TZ)
    minutos = agora.hour * 60 + agora.minute
    return JANELA_OPERACAO_INICIO_MINUTOS <= minutos <= JANELA_OPERACAO_FIM_MINUTOS


FERIADOS_STATE_FILE = "docs/feriados_cache.json"

# Lista fixa de reserva - usada SOMENTE se a Brasil API estiver fora do
# ar. Precisa de manutencao manual todo ano (mesmo tipo de manutencao
# que ja fazemos com SEED_EVENTS).
FERIADOS_B3_FALLBACK_2026 = [
    "2026-01-01",  # Confraternizacao Universal
    "2026-02-16",  # Carnaval (segunda)
    "2026-02-17",  # Carnaval (terca)
    "2026-04-03",  # Sexta-feira Santa
    "2026-04-21",  # Tiradentes
    "2026-05-01",  # Dia do Trabalho
    "2026-06-04",  # Corpus Christi
    "2026-09-07",  # Independencia
    "2026-10-12",  # Nossa Senhora Aparecida
    "2026-11-02",  # Finados
    "2026-11-15",  # Proclamacao da Republica
    "2026-11-20",  # Consciencia Negra
    "2026-12-25",  # Natal
]


def _carregar_feriados_do_ano(ano):
    """Busca feriados nacionais via Brasil API (gratuita, sem chave,
    mantida pela comunidade), com cache local por ano - nao busca de
    novo depois da primeira vez no mesmo ano. Se a API falhar, cai na
    lista fixa de reserva - nunca trava a checagem por causa de uma
    API externa fora do ar."""
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
    das mensagens padrao (Snapshot, Evening Briefing, Night Wrap). NAO
    bloqueia a coleta normal de noticia nem o Breaking (oportunista) -
    so as mensagens de rotina que pressupoem que houve pregao."""
    agora = datetime.now(BR_TZ)
    if agora.weekday() >= 5:  # 5=sabado, 6=domingo
        return False
    feriados_do_ano = _carregar_feriados_do_ano(agora.year)
    hoje_str = agora.strftime("%Y-%m-%d")
    return hoje_str not in feriados_do_ano


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return

    if not dentro_da_janela_de_operacao():
        print("Fora da janela de operacao (06h50-22h30 BRT) - ciclo ignorado.")
        return

    # Night Wrap deve ser SEMPRE a ultima mensagem do dia - se ja foi
    # enviado hoje, nenhum outro processamento roda ate amanha (nem
    # RSS, nem encaminhador, nem Giro do Mercado, nem Breaking). Guarda
    # simples no topo do ciclo, antes de qualquer outro trabalho.
    if load_night_wrap_state().get("last_night_wrap_date") == datetime.now(BR_TZ).strftime("%Y-%m-%d"):
        print("Night Wrap ja foi enviado hoje - ciclo ignorado (Night Wrap e sempre a ultima mensagem do dia).")
        return

    sent_hashes, recent_titles = load_state()
    new_count = 0
    portal_entries = []

    # Modo sombra (Fase 1) - carregado 1x antes do loop, isolado. Se
    # falhar por qualquer motivo, o modo sombra fica desligado neste
    # ciclo mas o fluxo real de publicacao continua normalmente.
    try:
        shadow_stories_state = editorial_foundation.load_active_stories()
    except Exception as e:
        print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))
        shadow_stories_state = None

    for source, feed_info in FEEDS.items():
        url = feed_info["url"]
        feed = fetch_feed(url)
        if not feed.entries:
            print("AVISO: Feed '" + source + "' retornou vazio ou falhou")
            continue

        # Contadores por fonte (Etapa 7) - visibilidade de quanto cada
        # fonte nova esta contribuindo de verdade, e por que o resto
        # foi descartado.
        recebidos = len(feed.entries[:10])
        aprovados = 0
        motivos_descarte = {}

        def registrar_descarte(motivo):
            motivos_descarte[motivo] = motivos_descarte.get(motivo, 0) + 1
            # Modo sombra (Fase 1) - isolado, nunca afeta a decisao real.
            try:
                editorial_foundation.increment_shadow_stat("descartadas_atual")
            except Exception as e:
                print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

        for entry in feed.entries[:10]:
            try:
                editorial_foundation.increment_shadow_stat("total_ingeridas")
            except Exception as e:
                print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

            h = item_hash(entry)
            if h in sent_hashes:
                registrar_descarte("ja enviado (hash conhecido)")
                continue

            title = entry.get("title", "")
            if is_duplicate_title(title, recent_titles):
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte("duplicado")
                continue

            raw_body = get_entry_body(entry)

            # FASE 3A - a chamada de IA agora roda logo apos a
            # deduplicacao tecnica (hash + titulo similar), ANTES dos
            # filtros de negocio atuais (is_relevant, filtro por
            # fonte) - exatamente o fluxo pedido: "nova camada
            # editorial sombra" avalia tudo que sobrou da limpeza
            # tecnica, antes do pipeline atual decidir o que fazer.
            #
            # CUSTO REAL: itens que antes eram descartados por
            # palavra-chave/filtro de fonte SEM gastar chamada de IA
            # agora GANHAM 1 chamada de IA mesmo assim, so para a
            # pontuacao sombra. E um aumento real de volume de
            # chamadas a Groq - vale monitorar a cota de perto.
            is_english = source not in PORTUGUESE_SOURCES
            ai_result = None
            if USE_AI:
                ai_result = classify_news_ai(title, raw_body, translate=is_english)
                # Pausa apos TODA chamada de IA, nao so apos o envio -
                # itens descartados logo em seguida (fora do escopo,
                # filtro de fonte, etc) tambem gastaram uma chamada e
                # precisam do mesmo respiro, senao uma rajada de
                # noticias estoura o rate limit do Groq (30 req/min)
                # mesmo com poucos itens aprovados/enviados.
                time.sleep(2.5)

            shadow_score = ai_result.get("score_materialidade") if ai_result else None
            shadow_motivo = ai_result.get("motivo_materialidade") if ai_result else None
            shadow_decisao = None
            try:
                shadow_decisao = editorial_foundation.compute_shadow_decision(shadow_score)
            except Exception as e:
                print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

            def registrar_descarte_com_sombra(motivo):
                """Registra o descarte REAL (igual sempre foi) e, em
                paralelo, o que o sistema sombra diria pra essa mesma
                noticia - permite comparar as 2 decisoes mesmo quando
                o descarte acontece por um filtro que roda antes do
                antigo ponto de chamada da IA."""
                registrar_descarte(motivo)
                try:
                    editorial_foundation.log_decision(
                        title, source, shadow_score, shadow_motivo,
                        shadow_decisao or "discard", decisao_sistema_atual="descartado"
                    )
                except Exception as e:
                    print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

            if ai_result and ai_result.get("relevante_mercado") is False:
                print("Descartada pela IA (fora do escopo de mercado): " + title[:60])
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte_com_sombra("IA classificou como fora do escopo")
                continue

            if not is_relevant(entry) or not is_recent_enough(entry):
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte_com_sombra("sem impacto economico / fora do escopo")
                continue

            passou_filtro, motivo_filtro = passes_source_specific_filter(source, entry)
            if not passou_filtro:
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte_com_sombra(motivo_filtro)
                continue

            check_title = title
            check_body = raw_body
            if not has_minimum_content(check_title, check_body):
                print("Descartada por conteudo insuficiente: " + title[:60])
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte_com_sombra("conteudo insuficiente")
                continue

            message, final_title, final_body, sentiment = format_message(source, entry, ai_result)

            # Fase 2 - decisao real de despacho (graduada do modo sombra
            # Fase 1): breaking sai na hora, round entra na fila do Giro
            # do Mercado (1 msg/hora em vez de 1 msg/noticia), discard
            # nao publica. Ver decide_dispatch_tier().
            dispatch_tier = decide_dispatch_tier(shadow_score)
            hashtags = extract_ticker_hashtags(title + " " + raw_body)
            earnings = maybe_extract_earnings_details(
                dispatch_tier, hashtags, title, raw_body, final_title, final_body
            )

            enviado_ou_enfileirado = False
            if dispatch_tier == "breaking":
                breaking_message = build_breaking_message(
                    title=final_title, resumo=final_body, motivo=shadow_motivo,
                    sentiment=sentiment, source=source, hashtags=hashtags,
                    earnings=earnings,
                )
                enviado_ou_enfileirado = send_telegram_message(breaking_message)
                if enviado_ou_enfileirado:
                    time.sleep(3)
            elif dispatch_tier == "round":
                if editorial_foundation is not None:
                    editorial_foundation.add_to_round_queue({
                        "title": final_title,
                        "resumo": truncate_text_clean(final_body, GIRO_ITEM_MAX_CHARS) if final_body else final_title,
                        "hashtags": hashtags,
                        "source": source,
                        "score": shadow_score,
                        "link": entry.get("link", ""),
                        "earnings": earnings,
                    })
                    enviado_ou_enfileirado = True
                else:
                    # Fallback seguro: sem editorial_foundation nao ha
                    # fila pra guardar o item - envia na hora pra nao
                    # perder a noticia (mesmo espirito de resiliencia
                    # usado no resto do pipeline).
                    enviado_ou_enfileirado = send_telegram_message(message)
                    if enviado_ou_enfileirado:
                        time.sleep(3)

            if enviado_ou_enfileirado:
                sent_hashes.add(h)
                add_to_recent_titles(recent_titles, title)
                new_count += 1
                aprovados += 1
                print(("Enviado (breaking)" if dispatch_tier == "breaking" else "Enfileirado (giro)") + ": " + title[:50] + " [" + sentiment + "]")
                save_state(sent_hashes, recent_titles)

                # Modo sombra (Fase 1) - roda DEPOIS da decisao real ja
                # tomada. Qualquer falha aqui e isolada e nunca desfaz
                # nem atrasa a publicacao/enfileiramento, que ja
                # aconteceu.
                try:
                    editorial_foundation.increment_shadow_stat("aprovadas_atual")

                    cluster_key = editorial_foundation.derive_cluster_key(title + " " + raw_body, TICKER_MENTION_LIST)

                    if shadow_stories_state is not None and cluster_key:
                        story_existente = editorial_foundation.find_story_by_cluster_key(shadow_stories_state, cluster_key)
                        if story_existente:
                            editorial_foundation.update_story(shadow_stories_state, story_existente["id"], materiality_score=shadow_score, source=source)
                        else:
                            nova_story = editorial_foundation.create_story(cluster_key, materiality_score=shadow_score, source=source)
                            shadow_stories_state["stories"].append(nova_story)

                    editorial_foundation.log_decision(title, source, shadow_score, shadow_motivo, shadow_decisao or "discard", decisao_sistema_atual="publicado")
                except Exception as e:
                    print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

                portal_entries.append({
                    "title": final_title,
                    "body": truncate_text_clean(final_body, 200),
                    "source": source,
                    "sentiment": sentiment,
                    "link": entry.get("link", ""),
                    "time": datetime.now(BR_TZ).strftime("%H:%M"),
                    "date": datetime.now(BR_TZ).strftime("%Y-%m-%d"),
                })
            else:
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                registrar_descarte_com_sombra(
                    "score de materialidade abaixo do limiar (" + str(shadow_score) + ")"
                    if dispatch_tier == "discard" else "falha ao publicar/enfileirar"
                )

        descartados = recebidos - aprovados
        if source in ("TechCrunch", "Poder360", "IBGE") or descartados > 0:
            resumo_fonte = (
                "Fonte: " + source + "\n"
                "Itens recebidos: " + str(recebidos) + "\n"
                "Itens aprovados: " + str(aprovados) + "\n"
                "Itens descartados: " + str(descartados)
            )
            if motivos_descarte:
                resumo_fonte += "\nMotivos:"
                for motivo, qtd in motivos_descarte.items():
                    resumo_fonte += "\n- " + motivo + " (" + str(qtd) + ")"
            print(resumo_fonte)

    # Modo sombra (Fase 1) - fecha o ciclo: salva o estado de stories
    # acumulado e regenera o relatorio diario. Isolado - falha aqui
    # nunca afeta nada do que ja foi publicado neste ciclo.
    try:
        if shadow_stories_state is not None:
            editorial_foundation.save_active_stories(shadow_stories_state)
        editorial_foundation.generate_shadow_daily_report()
    except Exception as e:
        print("Aviso (modo sombra, isolado, nao afeta publicacao real): " + str(e))

    try:
        forwarded_entries = process_forwarded_channels(sent_hashes, recent_titles)
        if forwarded_entries:
            portal_entries.extend(forwarded_entries)
            print(str(len(forwarded_entries)) + " noticia(s) dos canais encaminhados integrada(s) ao pipeline.")
    except Exception as e:
        print("Erro ao processar canais encaminhados (isolado, nao afeta o fluxo principal): " + str(e))

    all_portal_entries = portal_entries + load_portal_history()
    save_portal_history(all_portal_entries)

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in all_portal_entries if e.get("date") == today_str]

    archive = load_daily_archive()

    try:
        asset_archive, theme_archive = update_all_archives(entries_today)
        intelligence = compute_market_intelligence(entries_today, asset_archive, theme_archive)
        insights = build_market_insights(intelligence)
        print("Inteligencia de mercado calculada: " + str(len(insights["home"])) + " insight(s) na Home.")
    except Exception as e:
        print("Erro ao calcular inteligencia de mercado (isolado, nao afeta o fluxo principal): " + str(e))
        asset_archive, theme_archive = {}, {}
        insights = {"home": []}

    # Calculado UMA UNICA VEZ por execucao - reaproveitado pela Home
    # (Cockpit) e pelos Briefings, sem nenhuma chamada de API duplicada.
    market_snapshot = compute_market_snapshot()

    # output_path NAO aponta mais para uma pagina publica - dados-terminal.html
    # e um arquivo interno (sem nav, sem link em lugar nenhum do site) que so
    # existe para o Terminal (index.html) ler o feed gerado aqui via
    # fetch("dados-terminal.html") no lado do cliente (ver docs/terminal.js).
    generate_portal(all_portal_entries, entries_today, output_path="docs/dados-terminal.html", home_insights=insights["home"], market_snapshot=market_snapshot)

    try:
        events_state_for_briefing = load_events_state()
        combined_events = list(SEED_EVENTS) + events_state_for_briefing.get("events", [])
    except Exception as e:
        print("Erro ao carregar eventos (isolado, nao afeta o fluxo principal): " + str(e))
        combined_events = list(SEED_EVENTS)

    try:
        build_catalyst_radar_json(combined_events)
    except Exception as e:
        print("Erro ao gerar radar de catalisadores (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        processar_briefings_telegram(all_portal_entries, combined_events, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, market_snapshot)
    except Exception as e:
        print("Erro ao processar briefings (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        processar_giro_do_mercado(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        print("Erro ao processar Giro do Mercado (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        processar_market_snapshot_telegram(market_snapshot, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        print("Erro ao processar Snapshot 12h00 (isolado, nao afeta Briefings nem noticias): " + str(e))

    try:
        processar_night_wrap_telegram(market_snapshot, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        print("Erro ao processar Night Wrap (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        from social import content_engine
        content_engine.checar_aprovacoes_pendentes()
    except Exception as e:
        print("Erro ao checar aprovacoes do Social Content Engine (isolado): " + str(e))

    try:
        export_status_json()
    except Exception as e:
        print("Erro ao publicar status.json (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        from social import content_engine
        clusters_para_social = compute_news_clusters(entries_today)
        content_engine.run_social_content_engine(
            entries_today, clusters_para_social, insights, market_snapshot, combined_events
        )
    except Exception as e:
        print("Erro no Social Content Engine (isolado, nao afeta o fluxo principal): " + str(e))

    try:
        from social import design_engine
        design_engine.process_pending_designs()
    except Exception as e:
        print("Erro no Social Design Engine (isolado, nao afeta o fluxo principal): " + str(e))

    thermo_today = compute_sentiment_thermometer(entries_today)
    archive = [d for d in archive if d["date"] != today_str]
    archive.append({
        "date": today_str,
        "total": thermo_today["total"],
        "alta": thermo_today["alta"],
        "baixa": thermo_today["baixa"],
        "info": thermo_today["info"],
    })
    save_daily_archive(archive)
    build_weekly_summary_html(archive)
    export_resumo_historico(archive)

    print("Ciclo concluido. " + str(new_count) + " noticia(s) enviada(s).")


if __name__ == "__main__":
    main()
