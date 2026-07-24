import feedparser
import requests
import json
import os
import time
import hashlib
import re
import difflib
import html as html_module
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")

COCKPIT_TICKERS = ["^BVSP", "PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "WEGE3", "B3SA3", "BBAS3", "MGLU3"]

ECONOMIC_CALENDAR = [
    {"date": "04-05/08/2026", "event": "Reunião do Copom (decisão da Selic)"},
    {"date": "A cada ~45 dias", "event": "Próximas reuniões do Copom seguem esse ciclo"},
]

TICKER_MENTION_LIST = [
    "petr4", "petr3", "vale3", "itub4", "bbdc4", "bbas3", "wege3",
    "mglu3", "abev3", "b3sa3", "azul4", "gol", "embr3", "hapv3",
    "petrobras", "vale", "itau", "bradesco", "banco do brasil",
    "weg", "magazine luiza", "ambev", "azul", "embraer", "hapvida",
]

USE_AI = bool(GROQ_API_KEY)
STATE_FILE = "sent_items.json"

BR_TZ = timezone(timedelta(hours=-3))

FEEDS = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Money Times": "https://www.moneytimes.com.br/mercados/feed",
    "Investing.com Brasil": "https://br.investing.com/rss/news_25.rss",
    "CNBC - Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "CNBC - Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC - US News": "https://www.cnbc.com/id/15837362/device/rss/rss.html",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",
    "UOL Economia": "https://rss.uol.com.br/feed/economia.xml",
    "G1 Economia": "https://g1.globo.com/dynamo/economia/rss2.xml",
    "Exame": "https://exame.com/feed/",
    "Seu Dinheiro": "https://www.seudinheiro.com/feed/",
    "Suno Noticias": "https://www.suno.com.br/noticias/feed/",
    "Brazil Journal": "https://braziljournal.com/feed/",
    "Neofeed": "https://neofeed.com.br/feed/",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
    "Business Insider": "https://www.businessinsider.com/rss",
    "WSJ Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "Nasdaq": "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
    "ZeroHedge": "https://feeds.feedburner.com/zerohedge/feed",
}

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
]

PORTUGUESE_SOURCES = {
    "InfoMoney", "Money Times", "Investing.com Brasil", "UOL Economia",
    "G1 Economia", "Exame", "Seu Dinheiro", "Suno Noticias",
    "Brazil Journal", "Neofeed",
}

WORDPRESS_BOILERPLATE_PATTERNS = [
    r"The post .* appeared first on \w+\s*\.?",
    r"O post .* apareceu primeiro (n[oa]) \w+\s*\.?",
]


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("hashes", [])), data.get("titles", [])
        except Exception as e:
            print("AVISO: falha ao carregar estado (" + str(e) + "). Criando novo.")
    return set(), []


def save_state(hashes, titles):
    trimmed_hashes = list(hashes)[-3000:]
    trimmed_titles = titles[-500:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"hashes": trimmed_hashes, "titles": trimmed_titles}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("ERRO ao salvar estado: " + str(e))


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
    if any(nw in text for nw in NEGATIVE_KEYWORDS):
        return False
    if not KEYWORDS:
        return True
    return any(kw.lower() in text for kw in KEYWORDS)


def is_duplicate_title(title, recent_titles):
    for old_title in recent_titles:
        ratio = difflib.SequenceMatcher(None, title.lower(), old_title.lower()).ratio()
        if ratio > 0.92:
            return True
    return False


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


def strip_boilerplate(text):
    for pattern in WORDPRESS_BOILERPLATE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
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


def needs_ai(source, body):
    has_body = bool(strip_html_tags(body).strip())
    is_english = source not in PORTUGUESE_SOURCES
    return is_english or not has_body


def ask_groq(prompt):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": "Bearer " + GROQ_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=20,
    )
    data = response.json()
    if "choices" not in data:
        raise ValueError("Resposta sem choices: " + str(data))
    return data["choices"][0]["message"]["content"].strip()


def summarize_with_ai(title, body, translate=True):
    if not USE_AI:
        return None
    try:
        body_cleaned = strip_html_tags(body).strip()

        if translate:
            instruction = (
                "Voce recebeu uma noticia de mercado financeiro em ingles. Faca tres coisas:\n"
                "1. Traduza o titulo para portugues do Brasil.\n"
                "2. Escreva um resumo de no maximo 2 frases em portugues do Brasil. Se o texto "
                "original for curto ou vazio, baseie o resumo no titulo, explicando o contexto "
                "provavel do evento para o mercado.\n"
                "3. Classifique o sentimento da noticia para o mercado como BULLISH, BEARISH ou NEUTRAL.\n\n"
                "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
                '{"title": "titulo traduzido", "summary": "resumo aqui", "sentiment": "BULLISH"}\n\n'
                "Titulo original: " + title + "\n"
                "Texto original: " + body_cleaned
            )
        else:
            instruction = (
                "Voce recebeu uma noticia de mercado financeiro em portugues. Faca duas coisas:\n"
                "1. Mantenha o titulo original em portugues no campo title.\n"
                "2. Escreva um resumo de no maximo 2 frases em portugues do Brasil. Se o texto "
                "original for curto ou vazio, baseie o resumo no titulo.\n"
                "3. Classifique o sentimento da noticia para o mercado como BULLISH, BEARISH ou NEUTRAL.\n\n"
                "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
                '{"title": "titulo original", "summary": "resumo aqui", "sentiment": "BEARISH"}\n\n'
                "Titulo original: " + title + "\n"
                "Texto original: " + body_cleaned
            )

        raw_response = ask_groq(instruction)
        raw_response = re.sub(r"```json|```", "", raw_response).strip()
        parsed = json.loads(raw_response)

        return {
            "title": parsed.get("title", title) or title,
            "body": parsed.get("summary", body_cleaned) or body_cleaned,
            "sentiment": parsed.get("sentiment", "NEUTRAL").upper(),
        }
    except Exception as e:
        print("Erro IA (Groq): " + str(e))
        return None


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
    title = entry.get("title", "Sem titulo")
    body = get_entry_body(entry)
    sentiment = "NEUTRAL"

    if ai_result:
        title = ai_result.get("title", title) or title
        body = ai_result.get("body", "") or body
        sentiment = ai_result.get("sentiment", "NEUTRAL")

    body = strip_html_tags(body)
    body = strip_boilerplate(body)
    body = re.sub(r"(?i)pontos[- ]chave:?", "", body)
    body = re.sub(r"https?://\S+", "", body)
    body = re.sub(r"www\.\S+", "", body)
    body = re.sub(r"\n+", "\n", body).strip()

    if not body:
        body = "Leia mais no link."

    if sentiment == "BULLISH":
        marker = "\U0001F7E2 <b>[ALTA]</b>"
    elif sentiment == "BEARISH":
        marker = "\U0001F7E1 <b>[BAIXA]</b>"
    else:
        marker = "\u26AA <b>[INFORMATIVO]</b>"

    title_esc = html_module.escape(title, quote=False)
    body_esc = html_module.escape(body, quote=False)
    source_esc = html_module.escape(source, quote=False)

    result = marker + " <b>" + title_esc + "</b>\n\n" + body_esc + "\n\n<i>" + source_esc + "</i>"
    if len(result) > 3900:
        result = smart_truncate(result, 3900)
    return result, title, body, sentiment


def fetch_cockpit_quotes():
    if not BRAPI_TOKEN:
        return []
    try:
        tickers_str = ",".join(COCKPIT_TICKERS)
        url = "https://brapi.dev/api/quote/" + tickers_str + "?token=" + BRAPI_TOKEN
        response = requests.get(url, timeout=15)
        data = response.json()
        results = data.get("results", [])
        quotes = []
        for r in results:
            quotes.append({
                "symbol": r.get("symbol", ""),
                "price": r.get("regularMarketPrice", 0),
                "change": r.get("regularMarketChangePercent", 0),
            })
        return quotes
    except Exception as e:
        print("Erro ao buscar cotacoes (brapi): " + str(e))
        return []


def fetch_usd_brl():
    if not BRAPI_TOKEN:
        return None
    try:
        url = "https://brapi.dev/api/v2/currency?currency=USD-BRL&token=" + BRAPI_TOKEN
        response = requests.get(url, timeout=15)
        data = response.json()
        results = data.get("currency", [])
        if results:
            r = results[0]
            return {
                "price": r.get("bidPrice", 0),
                "change": r.get("pctChange", 0),
            }
        return None
    except Exception as e:
        print("Erro ao buscar dolar (brapi): " + str(e))
        return None


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


def compute_top_mentions(entries, limit=5):
    counts = {}
    for e in entries:
        text = (e["title"] + " " + e["body"]).lower()
        for term in TICKER_MENTION_LIST:
            if term in text:
                counts[term] = counts.get(term, 0) + 1

    sorted_terms = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_terms[:limit]


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


def build_terminal_news_html(entries, limit=8):
    """Monta uma lista compacta estilo terminal (Bloomberg/Reuters) com
    as noticias mais recentes, uma linha por item."""
    if not entries:
        return '<div class="terminal-empty">Sem noticias no momento.</div>'

    rows = ""
    for e in entries[:limit]:
        if e["sentiment"] == "BULLISH":
            tag = '<span class="term-tag alta">ALTA</span>'
        elif e["sentiment"] == "BEARISH":
            tag = '<span class="term-tag baixa">BAIXA</span>'
        else:
            tag = '<span class="term-tag info">INFO</span>'

        rows += (
            '<div class="term-row">'
            '<span class="term-time">' + e["time"] + "</span>"
            + tag +
            '<span class="term-title">' + html_module.escape(e["title"]) + "</span>"
            '<span class="term-src">' + html_module.escape(e["source"]) + "</span>"
            "</div>"
        )
    return rows


def build_calendar_html():
    """Monta a lista fixa do calendario economico."""
    rows = ""
    for item in ECONOMIC_CALENDAR:
        rows += (
            '<div class="calendar-item">'
            '<span class="calendar-date">' + html_module.escape(item["date"]) + "</span>"
            '<span class="calendar-event">' + html_module.escape(item["event"]) + "</span>"
            "</div>"
        )
    return rows


def build_cockpit_html(portal_entries):
    quotes = fetch_cockpit_quotes()
    usd = fetch_usd_brl()
    selic = fetch_selic()
    thermo = compute_sentiment_thermometer(portal_entries)
    top_mentions = compute_top_mentions(portal_entries)
    status = market_status()
    terminal_rows = build_terminal_news_html(portal_entries)
    calendar_rows = build_calendar_html()

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

    mentions_html = ""
    if top_mentions:
        for term, count in top_mentions:
            mentions_html += (
                '<div class="mention-item">'
                '<span class="mention-name">' + html_module.escape(term.upper()) + "</span>"
                '<span class="mention-count">' + str(count) + " menções</span>"
                "</div>"
            )
    else:
        mentions_html = '<div class="mention-empty">Sem dados suficientes ainda.</div>'

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
        '<div class="thermo-bar">'
        '<div class="thermo-seg alta" style="width:' + str(thermo["alta"]) + '%"></div>'
        '<div class="thermo-seg info" style="width:' + str(thermo["info"]) + '%"></div>'
        '<div class="thermo-seg baixa" style="width:' + str(thermo["baixa"]) + '%"></div>'
        "</div>"
        '<div class="thermo-legend">'
        '<span><span class="dot alta"></span>' + str(thermo["alta"]) + "% alta</span>"
        '<span><span class="dot info"></span>' + str(thermo["info"]) + "% neutro</span>"
        '<span><span class="dot baixa"></span>' + str(thermo["baixa"]) + "% baixa</span>"
        "</div>"
        "</div>"

        '<div class="cockpit-card">'
        '<span class="cockpit-label">Mais citados hoje</span>'
        '<div class="mentions-list">' + mentions_html + "</div>"
        "</div>"

        '<div class="cockpit-card terminal-card">'
        '<span class="cockpit-label">Terminal de notícias</span>'
        '<div class="terminal-list">' + terminal_rows + "</div>"
        "</div>"

        '<div class="cockpit-card calendar-card">'
        '<span class="cockpit-label">Calendário econômico</span>'
        '<div class="calendar-list">' + calendar_rows + "</div>"
        "</div>"

        "</div>"
    )

    return cockpit_html


PORTAL_HISTORY_FILE = "portal_history.json"


def load_portal_history():
    if os.path.exists(PORTAL_HISTORY_FILE):
        try:
            with open(PORTAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_portal_history(entries):
    trimmed = entries[:30]
    with open(PORTAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


def generate_portal(entries, template_path="docs/template.html", output_path="docs/index.html"):
    """Le o template.html, substitui os placeholders de ticker e feed
    pelos dados reais mais recentes, e salva como index.html (o que o
    GitHub Pages efetivamente publica)."""
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

    ticker_html = ""
    for e in entries[:12]:
        cls, _ = sentiment_class(e["sentiment"])
        ticker_html += (
            '<div class="tick"><span class="dot ' + cls + '"></span>'
            '<span class="headline">' + html_module.escape(e["title"]) + "</span>"
            '<span class="src">' + html_module.escape(e["source"]) + "</span></div>\n"
        )

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

    start_marker_t = "<!-- TICKER_ITEMS_START -->"
    end_marker_t = "<!-- TICKER_ITEMS_END -->"
    start_marker_c = "<!-- FEED_CARDS_START -->"
    end_marker_c = "<!-- FEED_CARDS_END -->"
    start_marker_k = "<!-- COCKPIT_START -->"
    end_marker_k = "<!-- COCKPIT_END -->"

    if start_marker_t in template and end_marker_t in template:
        before = template.split(start_marker_t)[0]
        after = template.split(end_marker_t)[1]
        template = before + start_marker_t + "\n" + ticker_html + end_marker_t + after

    if start_marker_c in template and end_marker_c in template:
        before = template.split(start_marker_c)[0]
        after = template.split(end_marker_c)[1]
        template = before + start_marker_c + "\n" + cards_html + end_marker_c + after

    if start_marker_k in template and end_marker_k in template:
        cockpit_html = build_cockpit_html(entries)
        before = template.split(start_marker_k)[0]
        after = template.split(end_marker_k)[1]
        template = before + start_marker_k + "\n" + cockpit_html + end_marker_k + after

    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")
    template = template.replace(
        '<span class="mono" id="last-updated">Atualizado automaticamente</span>',
        '<span class="mono" id="last-updated">Atualizado em ' + updated_at + "</span>",
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)

    print("Portal atualizado: " + output_path)


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return

    sent_hashes, recent_titles = load_state()
    new_count = 0
    portal_entries = []

    for source, url in FEEDS.items():
        feed = fetch_feed(url)
        if not feed.entries:
            print("AVISO: Feed '" + source + "' retornou vazio ou falhou")
            continue

        for entry in feed.entries[:10]:
            h = item_hash(entry)
            if h in sent_hashes:
                continue

            title = entry.get("title", "")
            if is_duplicate_title(title, recent_titles):
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            if not is_relevant(entry) or not is_recent_enough(entry):
                sent_hashes.add(h)
                save_state(sent_hashes, recent_titles)
                continue

            raw_body = get_entry_body(entry)
            is_english = source not in PORTUGUESE_SOURCES

            ai_result = None
            if needs_ai(source, raw_body):
                ai_result = summarize_with_ai(title, raw_body, translate=is_english)

            message, final_title, final_body, sentiment = format_message(source, entry, ai_result)

            if send_telegram_message(message):
                sent_hashes.add(h)
                recent_titles.append(title)
                new_count += 1
                print("Enviado: " + title[:50] + " [" + sentiment + "]")
                save_state(sent_hashes, recent_titles)

                portal_entries.append({
                    "title": final_title,
                    "body": final_body[:200],
                    "source": source,
                    "sentiment": sentiment,
                    "link": entry.get("link", ""),
                    "time": datetime.now(BR_TZ).strftime("%H:%M"),
                })

                time.sleep(3)

    all_portal_entries = portal_entries + load_portal_history()
    save_portal_history(all_portal_entries)
    generate_portal(all_portal_entries)
    print("Ciclo concluido. " + str(new_count) + " noticia(s) enviada(s).")


if __name__ == "__main__":
    main()
