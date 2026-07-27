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
    quotes = []
    for ticker in COCKPIT_TICKERS:
        try:
            url = "https://brapi.dev/api/quote/" + ticker + "?token=" + BRAPI_TOKEN
            response = requests.get(url, timeout=15)
            data = response.json()
            results = data.get("results", [])
            for r in results:
                quotes.append({
                    "symbol": r.get("symbol", ""),
                    "price": r.get("regularMarketPrice", 0),
                    "change": r.get("regularMarketChangePercent", 0),
                })
        except Exception as e:
            print("Erro ao buscar cotacao " + ticker + " (brapi): " + str(e))
            continue
    return quotes


def fetch_usd_brl():
    """O endpoint de cambio da brapi.dev nao esta disponivel no plano
    gratuito (retorna 403). Mantido desativado ate upgrade de plano."""
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


def compute_hourly_volume(entries_today):
    """Conta quantas noticias saíram em cada hora do dia (a partir do
    campo 'time' HH:MM ja registrado em cada entrada)."""
    counts = {}
    for e in entries_today:
        time_str = e.get("time", "")
        if ":" in time_str:
            hour = time_str.split(":")[0]
            counts[hour] = counts.get(hour, 0) + 1
    return counts


def build_hourly_volume_html(entries_today):
    counts = compute_hourly_volume(entries_today)

    if not counts:
        return '<div class="hourly-empty">Sem notícias registradas hoje ainda.</div>'

    sorted_hours = sorted(counts.keys(), key=lambda h: int(h))
    max_count = max(counts.values())

    rows = ""
    for hour in sorted_hours:
        count = counts[hour]
        width_pct = round((count / max_count) * 100)
        rows += (
            '<div class="hourly-row">'
            '<span class="hourly-hour">' + hour + "h</span>"
            '<div class="hourly-bar-track">'
            '<div class="hourly-bar-fill" style="width:' + str(width_pct) + '%"></div>'
            "</div>"
            '<span class="hourly-count">' + str(count) + "</span>"
            "</div>"
        )
    return rows


def build_cockpit_html(portal_entries, entries_today=None):
    if entries_today is None:
        entries_today = portal_entries

    quotes = fetch_cockpit_quotes()
    usd = fetch_usd_brl()
    selic = fetch_selic()
    thermo = compute_sentiment_thermometer(portal_entries)
    today_thermo = compute_sentiment_thermometer(entries_today)
    top_mentions = compute_top_mentions(portal_entries)
    status = market_status()
    terminal_rows = build_terminal_news_html(portal_entries)
    hourly_html = build_hourly_volume_html(entries_today)

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

        '<div class="cockpit-card hourly-card">'
        '<span class="cockpit-label">Volume de notícias por horário</span>'
        '<div class="hourly-list">' + hourly_html + "</div>"
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


def build_daily_summary_html(entries_today, today_str):
    """Gera a pagina de resumo diario, sem chamada extra de IA - usa
    apenas dados ja processados (contagem de sentimento, manchetes)."""
    thermo = compute_sentiment_thermometer(entries_today)

    if thermo["total"] == 0:
        intro = "Ainda não há notícias suficientes hoje para um resumo."
    elif thermo["alta"] > thermo["baixa"]:
        intro = (
            "Dia com predominância de notícias positivas para o mercado ("
            + str(thermo["alta"]) + "% de alta contra " + str(thermo["baixa"]) + "% de baixa)."
        )
    elif thermo["baixa"] > thermo["alta"]:
        intro = (
            "Dia com predominância de notícias negativas para o mercado ("
            + str(thermo["baixa"]) + "% de baixa contra " + str(thermo["alta"]) + "% de alta)."
        )
    else:
        intro = "Dia equilibrado entre notícias de alta e baixa para o mercado."

    items_html = ""
    for e in entries_today:
        if e["sentiment"] == "BULLISH":
            tag = '<span class="badge alta">ALTA</span>'
        elif e["sentiment"] == "BEARISH":
            tag = '<span class="badge baixa">BAIXA</span>'
        else:
            tag = '<span class="badge info">INFO</span>'
        items_html += (
            '<div class="card">'
            '<div class="card-meta">' + tag +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            "</div>"
        )

    if not items_html:
        items_html = '<p style="color:var(--slate)">Nenhuma notícia registrada ainda hoje.</p>'

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Resumo Diário - " + today_str + " | Antes do Sino</title>"
        "<link rel='stylesheet' href='assets.css'>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='https://t.me/tribute/app?startapp=sZPm' class='nav-cta'>Entrar no grupo</a></nav>"
        "<section><div class='section-head'>"
        "<span class='kicker'>Resumo Diário</span>"
        "<h2>" + today_str + "</h2>"
        "<p style='color:var(--slate);margin-top:14px;'>" + intro + "</p>"
        "</div>"
        "<div class='feed-grid'>" + items_html + "</div>"
        "</section>"
        "<footer><span>&copy; Antes do Sino</span>"
        "<a href='index.html' style='color:var(--gold)'>Voltar ao site</a></footer>"
        "</body></html>"
    )

    os.makedirs("docs", exist_ok=True)
    with open("docs/resumo-diario.html", "w", encoding="utf-8") as f:
        f.write(page)


def build_weekly_summary_html(archive):
    """Gera a pagina de resumo semanal a partir do arquivo diario
    acumulado (ultimos 7 dias com dados)."""
    last_7 = archive[-7:]

    rows_html = ""
    for day in last_7:
        rows_html += (
            '<div class="card">'
            "<h3>" + day["date"] + "</h3>"
            "<p>" + str(day["total"]) + " notícias · "
            + str(day["alta"]) + "% alta · "
            + str(day["baixa"]) + "% baixa · "
            + str(day["info"]) + "% neutro</p>"
            "</div>"
        )

    if not rows_html:
        rows_html = '<p style="color:var(--slate)">Ainda não há dias suficientes registrados.</p>'

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Resumo Semanal | Antes do Sino</title>"
        "<link rel='stylesheet' href='assets.css'>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='https://t.me/tribute/app?startapp=sZPm' class='nav-cta'>Entrar no grupo</a></nav>"
        "<section><div class='section-head'>"
        "<span class='kicker'>Resumo Semanal</span>"
        "<h2>Últimos dias de mercado</h2>"
        "</div>"
        "<div class='feed-grid'>" + rows_html + "</div>"
        "</section>"
        "<footer><span>&copy; Antes do Sino</span>"
        "<a href='index.html' style='color:var(--gold)'>Voltar ao site</a></footer>"
        "</body></html>"
    )

    os.makedirs("docs", exist_ok=True)
    with open("docs/resumo-semanal.html", "w", encoding="utf-8") as f:
        f.write(page)


PREMARKET_STATE_FILE = "premarket_carousel_state.json"


def load_premarket_state():
    if os.path.exists(PREMARKET_STATE_FILE):
        try:
            with open(PREMARKET_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_premarket_state(state):
    with open(PREMARKET_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_run_premarket_carousel():
    """So dispara uma vez por dia, entre 8h25 e 8h50 (horario de Brasilia)."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_premarket_state()
    if state.get("last_run_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (8 * 60 + 25) <= minutes <= (8 * 60 + 50)


def get_premarket_window_entries(all_entries):
    """Filtra noticias entre o fechamento de ontem (~18h) e agora, para
    servir de base ao resumo da pre-abertura."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    window = []
    for e in all_entries:
        e_date = e.get("date", "")
        e_time = e.get("time", "00:00")
        if e_date == today_str:
            window.append(e)
        elif e_date == yesterday_str:
            try:
                hour = int(e_time.split(":")[0])
                if hour >= 18:
                    window.append(e)
            except Exception:
                continue
    return window


def rank_premarket_highlights(entries, top_n=4):
    """Prioriza noticias com sentimento definido (nao neutro) e mais
    recentes, sem chamada de IA."""
    def score(e):
        sentiment_weight = 0 if e.get("sentiment") == "NEUTRAL" else 1
        return (sentiment_weight, e.get("date", ""), e.get("time", ""))

    sorted_entries = sorted(entries, key=score, reverse=True)
    return sorted_entries[:top_n]


def build_premarket_ai_content(highlights):
    """Uma unica chamada a Groq para escrever os textos dos slides e as
    legendas adaptadas para Instagram/TikTok e X, a partir das noticias
    mais relevantes da janela pre-mercado."""
    if not USE_AI or not highlights:
        return None

    headlines_text = ""
    for h in highlights:
        headlines_text += "- [" + h.get("sentiment", "NEUTRAL") + "] " + h["title"] + ": " + h["body"] + "\n"

    prompt = (
        "Voce e um editor de conteudo para um canal de noticias de mercado financeiro "
        "chamado 'Antes do Sino'. Com base nas noticias mais relevantes desde o ultimo "
        "fechamento do pregao, escreva o conteudo de um carrossel de 'pre-abertura' e "
        "as legendas para redes sociais.\n\n"
        "Noticias disponiveis:\n" + headlines_text + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"slide2_title": "...", "slide2_sub": "...", '
        '"slide3_title": "...", "slide3_sub": "...", '
        '"slide4_title": "...", "slide4_sub": "...", '
        '"titulo_post": "...", '
        '"legenda_instagram": "...", '
        '"legenda_x": "..."}\n\n'
        "Regras: slide2_title deve resumir o cenario geral de abertura em poucas palavras. "
        "slide3 e slide4 devem trazer os fatos mais relevantes das noticias fornecidas, "
        "com sub-textos curtos e factuais (sem inventar dados que nao estao nas noticias). "
        "titulo_post deve ser uma manchete curta e direta. legenda_instagram deve ter no "
        "maximo 5 hashtags no final. legenda_x deve ser mais curta, estilo Twitter/X, sem "
        "hashtags em excesso. Todos os textos em portugues do Brasil, sem markdown."
    )

    try:
        raw_response = ask_groq(prompt)
        raw_response = re.sub(r"```json|```", "", raw_response).strip()
        return json.loads(raw_response)
    except Exception as e:
        print("Erro ao gerar conteudo pre-abertura (Groq): " + str(e))
        return None


def build_slide_prompt_text(kind, title_text, sub_text=""):
    """Monta o prompt de imagem em portugues, no formato exato que ja
    usamos manualmente para colar no Gemini - sem gerar nenhuma imagem,
    so o texto do prompt pronto para copiar."""
    base = (
        "Crie uma imagem quadrada 1080x1080, fundo gradiente azul-marinho escuro "
        "(#0B1F3A para #050D1A). "
    )
    if kind == "capa":
        return (
            base + "No topo, pequeno icone dourado minimalista relacionado ao tema, "
            "line-art fino. Texto branco bold, tamanho moderado (nao ocupando mais "
            "que 15% da altura da imagem), centralizado: \"" + title_text + "\". "
            "Abaixo, em fonte ainda menor: \"" + sub_text + "\". Design limpo, "
            "profissional, estilo fintech premium."
        )
    if kind == "content":
        return (
            base + "No topo, icone pequeno dourado relacionado ao tema, line-art "
            "fino. Texto branco bold, tamanho moderado (nao ocupando mais que 15% "
            "da altura da imagem), centralizado: \"" + title_text + "\". Abaixo, em "
            "fonte ainda menor: \"" + sub_text + "\". Design limpo, profissional."
        )
    if kind == "cta":
        return (
            base + "com sino dourado maior e elaborado centralizado, leve brilho ao "
            "redor. Texto branco bold, tamanho moderado, acima do sino: \"" +
            title_text + "\". Abaixo, texto dourado: \"Antes do Sino no Telegram\" "
            "e menor: \"Link na bio\". Design profissional, elegante."
        )
    return base + title_text


def run_premarket_carousel(all_entries):
    """Fluxo completo: filtra noticias da janela pre-mercado, gera texto
    via IA, gera as 5 imagens do carrossel via Pollinations, e salva tudo
    numa pagina do site para o usuario buscar e postar."""
    highlights = rank_premarket_highlights(get_premarket_window_entries(all_entries))
    ai_content = build_premarket_ai_content(highlights)

    if not ai_content:
        print("AVISO: nao foi possivel gerar conteudo do carrossel pre-mercado hoje.")
        return

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")

    slides = [
        ("capa", "ANTES DE ABRIR O PREGAO", today_str),
        ("content", ai_content.get("slide2_title", ""), ai_content.get("slide2_sub", "")),
        ("content", ai_content.get("slide3_title", ""), ai_content.get("slide3_sub", "")),
        ("content", ai_content.get("slide4_title", ""), ai_content.get("slide4_sub", "")),
        ("cta", "Acompanhe a abertura em tempo real", ""),
    ]

    prompts_html = ""
    for i, (kind, title_text, sub_text) in enumerate(slides, start=1):
        prompt_text = build_slide_prompt_text(kind, title_text, sub_text)
        prompts_html += (
            "<div style='margin-bottom:20px;padding:18px;background:rgba(255,255,255,0.03);"
            "border-radius:12px;border:1px solid var(--line);'>"
            "<h4 style='margin-bottom:10px;color:var(--gold);'>Slide " + str(i) + "</h4>"
            "<p style='white-space:pre-wrap;color:var(--cream);font-family:monospace;"
            "font-size:0.9rem;'>" + html_module.escape(prompt_text) + "</p>"
            "</div>"
        )

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Pre-Abertura de Hoje | Antes do Sino</title>"
        "<link rel='stylesheet' href='assets.css'>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"
        "<section><div class='section-head'>"
        "<span class='kicker'>Gerado automaticamente</span>"
        "<h2>" + html_module.escape(ai_content.get("titulo_post", "")) + "</h2>"
        "</div>"
        "<h3 style='margin-bottom:16px;'>Prompts para colar no Gemini</h3>"
        + prompts_html +
        "<div style='margin-top:30px;padding:20px;background:rgba(255,255,255,0.03);border-radius:12px;'>"
        "<h4 style='margin-bottom:10px;'>Legenda Instagram/TikTok</h4>"
        "<p style='white-space:pre-wrap;color:var(--slate);'>" + html_module.escape(ai_content.get("legenda_instagram", "")) + "</p>"
        "</div>"
        "<div style='margin-top:16px;padding:20px;background:rgba(255,255,255,0.03);border-radius:12px;'>"
        "<h4 style='margin-bottom:10px;'>Legenda X</h4>"
        "<p style='white-space:pre-wrap;color:var(--slate);'>" + html_module.escape(ai_content.get("legenda_x", "")) + "</p>"
        "</div>"
        "</section>"
        "</body></html>"
    )

    with open("docs/premarket-hoje.html", "w", encoding="utf-8") as f:
        f.write(page)

    state = load_premarket_state()
    state["last_run_date"] = today_str
    save_premarket_state(state)

    print("Prompts de pre-abertura gerados com sucesso: docs/premarket-hoje.html")


def should_run_close_carousel():
    """So dispara uma vez por dia, entre 18h25 e 18h55 (horario de Brasilia)."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_premarket_state()
    if state.get("last_close_run_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (18 * 60 + 25) <= minutes <= (18 * 60 + 55)


def get_ibovespa_quote():
    """Reaproveita fetch_cockpit_quotes e extrai apenas o Ibovespa."""
    quotes = fetch_cockpit_quotes()
    for q in quotes:
        if q.get("symbol") == "^BVSP":
            return q
    return None


def build_close_ai_content(highlights, ibov_quote):
    """Uma unica chamada a Groq para escrever os textos do carrossel de
    fechamento e as legendas, usando a cotacao real do Ibovespa quando
    disponivel e as noticias mais relevantes do dia."""
    if not USE_AI:
        return None

    headlines_text = ""
    for h in highlights:
        headlines_text += "- [" + h.get("sentiment", "NEUTRAL") + "] " + h["title"] + ": " + h["body"] + "\n"

    if ibov_quote:
        quote_text = (
            "Ibovespa fechou em " + ("alta" if ibov_quote["change"] >= 0 else "queda") +
            " de " + str(abs(round(ibov_quote["change"], 2))) + "%, em " +
            str(round(ibov_quote["price"])) + " pontos."
        )
    else:
        quote_text = "Cotacao oficial do Ibovespa nao disponivel nesta execucao - nao invente numeros."

    prompt = (
        "Voce e um editor de conteudo para um canal de noticias de mercado financeiro "
        "chamado 'Antes do Sino'. Escreva o conteudo de um carrossel de 'resumo do pregao' "
        "(fechamento do dia) e as legendas para redes sociais.\n\n"
        "Dado oficial do fechamento: " + quote_text + "\n\n"
        "Noticias relevantes do dia:\n" + headlines_text + "\n\n"
        "Responda APENAS em JSON plano, sem markdown, no formato exato:\n"
        '{"slide2_title": "...", "slide2_sub": "...", '
        '"slide3_title": "...", "slide3_sub": "...", '
        '"slide4_title": "...", "slide4_sub": "...", '
        '"titulo_post": "...", '
        '"legenda_instagram": "...", '
        '"legenda_x": "..."}\n\n'
        "Regras: slide2 deve trazer o fechamento do indice (use o dado oficial fornecido; "
        "se nao houver dado oficial, fale de forma qualitativa sem inventar numero). "
        "slide3 e slide4 devem trazer os fatos mais relevantes do dia, com sub-textos curtos "
        "e factuais, sem inventar dados que nao estao nas noticias fornecidas. titulo_post "
        "deve ser uma manchete curta e direta sobre o fechamento. legenda_instagram deve ter "
        "no maximo 5 hashtags no final. legenda_x deve ser mais curta, estilo Twitter/X. "
        "Todos os textos em portugues do Brasil, sem markdown."
    )

    try:
        raw_response = ask_groq(prompt)
        raw_response = re.sub(r"```json|```", "", raw_response).strip()
        return json.loads(raw_response)
    except Exception as e:
        print("Erro ao gerar conteudo de fechamento (Groq): " + str(e))
        return None


def run_close_carousel(all_entries):
    """Fluxo completo do carrossel de fechamento: busca cotacao real do
    Ibovespa, filtra noticias do dia, gera texto via IA, gera as 5
    imagens via Pollinations, e salva numa pagina do site."""
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in all_entries if e.get("date") == today_str]
    highlights = rank_premarket_highlights(entries_today)
    ibov_quote = get_ibovespa_quote()
    ai_content = build_close_ai_content(highlights, ibov_quote)

    if not ai_content:
        print("AVISO: nao foi possivel gerar conteudo do carrossel de fechamento hoje.")
        return

    slides = [
        ("capa", "RESUMO DE MERCADO", "Pregao de " + today_str),
        ("content", ai_content.get("slide2_title", ""), ai_content.get("slide2_sub", "")),
        ("content", ai_content.get("slide3_title", ""), ai_content.get("slide3_sub", "")),
        ("content", ai_content.get("slide4_title", ""), ai_content.get("slide4_sub", "")),
        ("cta", "Quer receber isso em tempo real, todos os dias?", ""),
    ]

    prompts_html = ""
    for i, (kind, title_text, sub_text) in enumerate(slides, start=1):
        prompt_text = build_slide_prompt_text(kind, title_text, sub_text)
        prompts_html += (
            "<div style='margin-bottom:20px;padding:18px;background:rgba(255,255,255,0.03);"
            "border-radius:12px;border:1px solid var(--line);'>"
            "<h4 style='margin-bottom:10px;color:var(--gold);'>Slide " + str(i) + "</h4>"
            "<p style='white-space:pre-wrap;color:var(--cream);font-family:monospace;"
            "font-size:0.9rem;'>" + html_module.escape(prompt_text) + "</p>"
            "</div>"
        )

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Fechamento de Hoje | Antes do Sino</title>"
        "<link rel='stylesheet' href='assets.css'>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"
        "<section><div class='section-head'>"
        "<span class='kicker'>Gerado automaticamente</span>"
        "<h2>" + html_module.escape(ai_content.get("titulo_post", "")) + "</h2>"
        "</div>"
        "<h3 style='margin-bottom:16px;'>Prompts para colar no Gemini</h3>"
        + prompts_html +
        "<div style='margin-top:30px;padding:20px;background:rgba(255,255,255,0.03);border-radius:12px;'>"
        "<h4 style='margin-bottom:10px;'>Legenda Instagram/TikTok</h4>"
        "<p style='white-space:pre-wrap;color:var(--slate);'>" + html_module.escape(ai_content.get("legenda_instagram", "")) + "</p>"
        "</div>"
        "<div style='margin-top:16px;padding:20px;background:rgba(255,255,255,0.03);border-radius:12px;'>"
        "<h4 style='margin-bottom:10px;'>Legenda X</h4>"
        "<p style='white-space:pre-wrap;color:var(--slate);'>" + html_module.escape(ai_content.get("legenda_x", "")) + "</p>"
        "</div>"
        "</section>"
        "</body></html>"
    )

    with open("docs/fechamento-hoje.html", "w", encoding="utf-8") as f:
        f.write(page)

    state = load_premarket_state()
    state["last_close_run_date"] = today_str
    save_premarket_state(state)

    print("Prompts de fechamento gerados com sucesso: docs/fechamento-hoje.html")


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


def generate_portal(entries, entries_today=None, template_path="docs/template.html", output_path="docs/index.html"):
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
        cockpit_html = build_cockpit_html(entries, entries_today)
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
                    "date": datetime.now(BR_TZ).strftime("%Y-%m-%d"),
                })

                time.sleep(3)

    all_portal_entries = portal_entries + load_portal_history()
    save_portal_history(all_portal_entries)

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in all_portal_entries if e.get("date") == today_str]

    archive = load_daily_archive()

    generate_portal(all_portal_entries, entries_today)
    build_daily_summary_html(entries_today, today_str)

    if should_run_premarket_carousel():
        print("Horario da pre-abertura detectado, gerando carrossel automatico...")
        run_premarket_carousel(all_portal_entries)

    if should_run_close_carousel():
        print("Horario de fechamento detectado, gerando carrossel automatico...")
        run_close_carousel(all_portal_entries)

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

    print("Ciclo concluido. " + str(new_count) + " noticia(s) enviada(s).")


if __name__ == "__main__":
    main()
