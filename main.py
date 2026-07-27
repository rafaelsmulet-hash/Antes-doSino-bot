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


def build_cockpit_html(portal_entries, entries_today=None):
    if entries_today is None:
        entries_today = portal_entries

    quotes = fetch_cockpit_quotes()
    usd = fetch_usd_brl()
    selic = fetch_selic()
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


def filter_brazil_only(entries):
    """Mantem apenas noticias de fontes brasileiras, para os carrosseis
    de pre-abertura e fechamento focarem no mercado local."""
    return [e for e in entries if e.get("source") in PORTUGUESE_SOURCES]


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
    highlights = rank_premarket_highlights(filter_brazil_only(get_premarket_window_entries(all_entries)))
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
    highlights = rank_premarket_highlights(filter_brazil_only(entries_today))
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


def compute_news_clusters(entries):
    """Agrupa noticias por ativo/tema em comum, e pontua cada cluster
    internamente por numero de fontes distintas, forca de sentimento e
    recorrencia - sem expor nenhum numero de indice ao usuario, so o
    resultado ja ordenado."""
    clusters = {}
    for e in entries:
        text = (e["title"] + " " + e["body"]).lower()
        for term in TICKER_MENTION_LIST:
            if term in text:
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


def build_worry_line_html(clusters):
    """Responde a pergunta 'preciso me preocupar com alguma coisa?' em
    uma unica frase, sem exigir interpretacao."""
    if not clusters:
        return (
            '<div class="worry-line calm">'
            '<span class="worry-dot"></span> Dia tranquilo, sem sinais fortes de atenção no mercado até agora.'
            "</div>"
        )

    top = clusters[0]
    if top["distinct_sources"] < 2:
        return (
            '<div class="worry-line calm">'
            '<span class="worry-dot"></span> Dia tranquilo, sem sinais fortes de atenção no mercado até agora.'
            "</div>"
        )

    rep = top["representative"]
    asset_label = top["term"].upper()
    if rep["sentiment"] == "BEARISH":
        return (
            '<div class="worry-line alert">'
            '<span class="worry-dot"></span> Atenção: <b>' + html_module.escape(asset_label) +
            "</b> concentra o mercado hoje, com sinal de baixa."
            "</div>"
        )
    elif rep["sentiment"] == "BULLISH":
        return (
            '<div class="worry-line alert">'
            '<span class="worry-dot"></span> Destaque: <b>' + html_module.escape(asset_label) +
            "</b> concentra o mercado hoje, com sinal de alta."
            "</div>"
        )
    else:
        return (
            '<div class="worry-line info">'
            '<span class="worry-dot"></span> <b>' + html_module.escape(asset_label) +
            "</b> é o assunto mais comentado do mercado agora."
            "</div>"
        )


def build_signals_html(clusters, generated_asset_slugs=None, limit=5):
    """Monta os cards de 'Sinais do Dia' - as noticias que realmente
    movimentaram o mercado, rankeadas por relevancia, nao por horario.
    Quando a noticia menciona um ativo que ja tem pagina propria
    gerada, adiciona um link interno para ela - reforca SEO e ajuda o
    usuario a se aprofundar sem sair da Home."""
    if generated_asset_slugs is None:
        generated_asset_slugs = set()

    if not clusters:
        return '<p style="color:var(--slate);">Ainda sem sinais suficientes hoje. Volte mais tarde.</p>'

    def find_asset_link(entry):
        for profile in ASSET_PROFILES:
            if profile["slug"] in generated_asset_slugs and match_asset_terms(entry, profile["terms"]):
                return profile
        return None

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
        asset_match = find_asset_link(rep)
        asset_link_html = ""
        if asset_match:
            asset_link_html = (
                '<a href="ativos/' + asset_match["slug"] + '.html" class="read" '
                'style="margin-right:16px;">📊 Ver ' + html_module.escape(asset_match["label"]) + "</a>"
            )

        cards_html += (
            '<div class="signal-card">'
            '<div class="card-meta">' + badge +
            '<span class="src">' + html_module.escape(rep["source"]) + "</span>"
            '<span class="time">' + rep["time"] + "</span></div>"
            "<h3>" + html_module.escape(rep["title"]) + "</h3>"
            "<p>" + html_module.escape(rep["body"]) + "</p>"
            '<span class="signal-reason">🔎 ' + reason + "</span>"
            "<div>" + asset_link_html +
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a></div>'
            "</div>\n"
        )
    return cards_html


EVENTS_STATE_FILE = "events_detected.json"

SEED_EVENTS = [
    {"date": "2026-08-04", "label": "Reunião do Copom (decisão da Selic)",
     "keywords": ["copom", "selic", "juros"], "organizer": "Banco Central do Brasil"},
]


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
        '"keywords": ["palavra1", "palavra2"]}]\n\n'
        "O campo keywords deve conter 2 a 4 termos curtos (em portugues, minusculas) "
        "que apareceriam em noticias relacionadas a esse evento, para permitir "
        "encontrar essas noticias depois. Se nao houver nenhum evento futuro claro e "
        "com data especifica mencionada, responda apenas: []"
    )

    try:
        raw_response = ask_groq(prompt)
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
                valid.append({
                    "date": item["date"],
                    "label": item["label"],
                    "keywords": [str(k).lower() for k in keywords][:4],
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

    all_events = list(SEED_EVENTS)
    seed_labels = set(e["label"].lower().strip() for e in SEED_EVENTS)
    for ev in registry:
        if ev["label"].lower().strip() not in seed_labels:
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

        label_escaped = html_module.escape(ev["label"])
        event_entries_count = len(get_event_entries(all_history, ev))
        if event_entries_count >= MIN_EVENT_NEWS_THRESHOLD:
            slug = slugify_label(ev["label"])
            label_html = '<a href="eventos/' + slug + '.html" style="color:var(--cream);">' + label_escaped + "</a>"
        else:
            label_html = label_escaped

        events_html += (
            '<div class="event-item">'
            '<span class="event-countdown">' + countdown + "</span>"
            '<span class="event-label">' + label_html + "</span>"
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


MIN_NEWS_THRESHOLD = 2
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


def fetch_asset_quote(ticker_symbol):
    """Busca a cotacao de um unico ticker via brapi.dev, respeitando o
    limite de 1 ativo por requisicao do plano gratuito. Falha de forma
    graciosa: qualquer erro retorna None, e quem chama simplesmente
    omite o bloco de cotacao, sem quebrar a pagina."""
    if not BRAPI_TOKEN:
        return None
    try:
        url = "https://brapi.dev/api/quote/" + ticker_symbol + "?token=" + BRAPI_TOKEN
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return {
            "price": r.get("regularMarketPrice"),
            "change": r.get("regularMarketChangePercent"),
        }
    except Exception as e:
        print("Erro ao buscar cotacao de " + ticker_symbol + " (fallback gracioso): " + str(e))
        return None


def compute_asset_summary_sentence(today_entries, label):
    """Frase unica sobre o momento atual do ativo, sem chamada extra de
    IA - regra baseada em contagem de sentimento, no mesmo espirito da
    worry-line da Home."""
    if not today_entries:
        return "Sem notícias recentes sobre " + label + " hoje."

    alta = sum(1 for e in today_entries if e["sentiment"] == "BULLISH")
    baixa = sum(1 for e in today_entries if e["sentiment"] == "BEARISH")
    total = len(today_entries)

    most_recent = sorted(today_entries, key=lambda e: e.get("time", ""), reverse=True)[0]

    if alta > baixa:
        return (
            label + " tem hoje mais notícias positivas que negativas ("
            + str(total) + " no total). Destaque: " + most_recent["title"]
        )
    elif baixa > alta:
        return (
            label + " tem hoje mais notícias negativas que positivas ("
            + str(total) + " no total). Destaque: " + most_recent["title"]
        )
    else:
        return (
            label + " teve " + str(total) + " notícia(s) hoje, sem predominância clara "
            "de sentimento. Destaque: " + most_recent["title"]
        )


def compute_related_assets(profile, all_history, generated_slugs):
    """Encontra ativos relacionados por grupo economico e por
    coocorrencia real (mesma noticia menciona os dois ativos) - nunca
    lista todos os ativos, so os que fazem sentido e que tem pagina
    gerada de verdade."""
    self_entries = get_asset_entries(all_history, profile["terms"])
    scored = []

    for other in ASSET_PROFILES:
        if other["slug"] == profile["slug"] or other["slug"] not in generated_slugs:
            continue

        co_occurrence = sum(1 for e in self_entries if match_asset_terms(e, other["terms"]))
        same_group = 1 if other["group"] == profile["group"] else 0

        if co_occurrence > 0 or same_group:
            scored.append((other, co_occurrence * 2 + same_group))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in scored[:4]]


def compute_asset_clusters(asset_entries_today):
    """Agrupa noticias muito similares (mesma historia coberta por mais
    de uma fonte) usando comparacao de titulo ja existente no projeto,
    e rankeia por numero de fontes + forca de sentimento."""
    clusters = []
    used = set()

    for i, e in enumerate(asset_entries_today):
        if i in used:
            continue
        group = [e]
        used.add(i)
        for j, other in enumerate(asset_entries_today):
            if j in used or j == i:
                continue
            ratio = difflib.SequenceMatcher(None, e["title"].lower(), other["title"].lower()).ratio()
            if ratio > 0.55:
                group.append(other)
                used.add(j)

        distinct_sources = len(set(g["source"] for g in group))
        non_neutral = sum(1 for g in group if g["sentiment"] != "NEUTRAL")
        score = distinct_sources * 2 + non_neutral * 1.5 + len(group)
        clusters.append({"items": group, "score": score, "distinct_sources": distinct_sources})

    clusters.sort(key=lambda c: c["score"], reverse=True)
    return clusters


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
    asset_history = asset_history[-14:]

    archive[slug] = asset_history
    save_asset_archive(archive)
    return asset_history


def build_asset_page_html(profile, all_history, entries_today, generated_slugs):
    slug = profile["slug"]
    label = profile["label"]
    terms = profile["terms"]
    why_it_matters = profile["why"]
    quote_ticker = profile.get("quote_ticker", "")

    asset_history_entries = get_asset_entries(all_history, terms)
    asset_today_entries = get_asset_entries(entries_today, terms)
    asset_recent_entries = get_asset_entries_recent(all_history, terms, ASSET_RECENT_WINDOW_HOURS)

    if len(asset_recent_entries) < MIN_NEWS_THRESHOLD:
        return None

    quote = fetch_asset_quote(quote_ticker) if quote_ticker else None

    trend = update_asset_archive_entry(slug, asset_today_entries)
    summary_sentence = compute_asset_summary_sentence(asset_today_entries, label)
    clusters = compute_asset_clusters(asset_today_entries)
    related = compute_related_assets(profile, all_history, generated_slugs)

    def sentiment_badge(s):
        if s == "BULLISH":
            return '<span class="badge alta">ALTA</span>'
        if s == "BEARISH":
            return '<span class="badge baixa">BAIXA</span>'
        return '<span class="badge info">INFO</span>'

    clusters_html = ""
    for c in clusters[:4]:
        rep = c["items"][0]
        reason = (
            "Coberto por " + str(c["distinct_sources"]) + " fontes diferentes"
            if c["distinct_sources"] >= 2 else "Notícia em destaque"
        )
        clusters_html += (
            '<div class="signal-card">'
            '<div class="card-meta">' + sentiment_badge(rep["sentiment"]) +
            '<span class="src">' + html_module.escape(rep["source"]) + "</span>"
            '<span class="time">' + rep["time"] + "</span></div>"
            "<h3>" + html_module.escape(rep["title"]) + "</h3>"
            "<p>" + html_module.escape(rep["body"]) + "</p>"
            '<span class="signal-reason">🔎 ' + reason + "</span>"
            "</div>\n"
        )
    if not clusters_html:
        clusters_html = '<p style="color:var(--slate);">Sem notícias suficientes hoje sobre ' + html_module.escape(label) + ".</p>"

    # Historico: fallback elegante - so mostra evolucao dia a dia quando
    # ha pelo menos 3 dias de dados reais. Antes disso, so uma frase.
    if len(trend) >= 3:
        trend_rows = ""
        for day in reversed(trend[-7:]):
            trend_rows += (
                "<div class='event-item'><span class='event-date'>" + day["date"] + "</span>"
                "<span class='event-label'>" + str(day["count"]) + " menções</span>"
                "<span class='event-countdown'>" + str(day["alta"]) + " alta / " + str(day["baixa"]) + " baixa</span>"
                "</div>"
            )
        history_block = (
            "<section><div class='section-head'>"
            "<span class='kicker'>Histórico</span>"
            "<h2>Evolução recente</h2>"
            "</div>"
            "<div class='events-list'>" + trend_rows + "</div>"
            "</section>"
        )
    else:
        history_block = (
            "<section><div class='section-head'>"
            "<span class='kicker'>Histórico</span>"
            "<h2>Evolução recente</h2>"
            "<p style='color:var(--slate);margin-top:10px;'>Histórico de cobertura em consolidação para este ativo.</p>"
            "</div>"
            "</section>"
        )

    all_feed_html = ""
    sorted_all = sorted(asset_history_entries, key=lambda e: (e.get("date", ""), e.get("time", "")), reverse=True)
    for e in sorted_all[:30]:
        link = e.get("link", "#") or "#"
        all_feed_html += (
            '<div class="card">'
            '<div class="card-meta">' + sentiment_badge(e["sentiment"]) +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e.get("date", "") + " " + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a>'
            "</div>\n"
        )

    related_html = ""
    for other in related:
        related_html += '<a href="' + other["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(other["label"]) + "</a>"
    related_block = ""
    if related_html:
        related_block = (
            "<section><div class='section-head'>"
            "<span class='kicker'>Ativos relacionados</span>"
            "</div>"
            "<div>" + related_html + "</div>"
            "</section>"
        )

    # Bloco de cotacao: so aparece se a brapi.dev respondeu com sucesso.
    # Fallback gracioso - se quote for None (falha ou ticker americano
    # nao suportado no plano gratuito), o bloco inteiro e omitido, sem
    # gerar erro nem espaco vazio na pagina.
    quote_block = ""
    if quote and quote.get("price") is not None:
        change = quote.get("change") or 0
        change_class = "alta" if change >= 0 else "baixa"
        change_sign = "+" if change >= 0 else ""
        quote_block = (
            "<div style='display:inline-flex;align-items:center;gap:10px;margin-top:14px;"
            "padding:8px 16px;background:rgba(255,255,255,0.03);border:1px solid var(--line);"
            "border-radius:100px;font-family:monospace;'>"
            "<b>" + html_module.escape(quote_ticker) + "</b>"
            "<span>" + str(round(quote["price"], 2)) + "</span>"
            "<span class='badge " + change_class + "'>" + change_sign + str(round(change, 2)) + "%</span>"
            "</div>"
        )

    meta_description = html_module.escape(summary_sentence[:155])
    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")
    updated_iso = datetime.now(BR_TZ).isoformat()
    page_url = "https://antesdosino.com.br/ativos/" + slug + ".html"
    page_title = html_module.escape(label) + " hoje - notícias e sentimento | Antes do Sino"

    # JSON-LD: descreve o publicador (NewsMediaOrganization) e lista as
    # noticias da pagina como ItemList - ajuda buscadores a entenderem
    # a natureza do conteudo sem exigir nenhuma biblioteca externa.
    schema_items = []
    for e in sorted_all[:10]:
        schema_items.append({
            "@type": "ListItem",
            "position": len(schema_items) + 1,
            "url": e.get("link", page_url) or page_url,
            "name": e["title"],
        })
    schema_json = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "NewsMediaOrganization",
                "name": "Antes do Sino",
                "url": "https://antesdosino.com.br",
            },
            {
                "@type": "ItemList",
                "name": "Notícias sobre " + label,
                "itemListElement": schema_items,
            },
        ],
    }
    schema_script = json.dumps(schema_json, ensure_ascii=False)

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>" + page_title + "</title>"
        "<meta name='description' content='" + meta_description + "'>"
        "<link rel='canonical' href='" + page_url + "'>"
        "<meta property='og:type' content='website'>"
        "<meta property='og:title' content='" + page_title + "'>"
        "<meta property='og:description' content='" + meta_description + "'>"
        "<meta property='og:url' content='" + page_url + "'>"
        "<meta property='og:site_name' content='Antes do Sino'>"
        "<meta name='twitter:card' content='summary'>"
        "<meta name='twitter:title' content='" + page_title + "'>"
        "<meta name='twitter:description' content='" + meta_description + "'>"
        "<link rel='stylesheet' href='../assets.css'>"
        "<script type='application/ld+json'>" + schema_script + "</script>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Ativo</span>"
        "<h1 style='font-family:Fraunces,serif;font-size:2rem;font-weight:600;'>" + html_module.escape(label) + "</h1>"
        + quote_block +
        "<p style='color:var(--slate);margin-top:14px;font-size:1.05rem;'>" + html_module.escape(summary_sentence) + "</p>"
        "<p style='color:var(--slate-dim);margin-top:10px;font-size:0.9rem;border-left:2px solid var(--bronze);padding-left:12px;'>"
        "<b style='color:var(--bronze);'>Por que isso importa:</b> " + html_module.escape(why_it_matters) + "</p>"
        "</div></section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>O que está movimentando agora</span>"
        "<h2>Principais notícias sobre " + html_module.escape(label) + "</h2>"
        "</div>"
        "<div class='signals-grid'>" + clusters_html + "</div>"
        "</section>"

        + history_block +

        "<section><div class='section-head'>"
        "<span class='kicker'>Aprofunde-se</span>"
        "<h2>Todas as notícias sobre " + html_module.escape(label) + "</h2>"
        "</div>"
        "<div class='feed-grid'>" + all_feed_html + "</div>"
        "</section>"

        + related_block +

        "<footer><span>&copy; Antes do Sino — dados públicos, não é recomendação de investimento.</span>"
        "<span class='mono'>Atualizado em " + updated_at + "</span></footer>"
        "</body></html>"
    )

    return page


def gerar_sitemap_completo(diretorio_docs="docs"):
    """Gera/atualiza o sitemap.xml escaneando diretamente as pastas de
    saida (docs/ativos e docs/temas) - desacoplado de qualquer lista em
    memoria, entao funciona corretamente independente da ordem em que
    os modulos de ativos e temas sao executados. So inclui o que
    realmente existe em disco, nunca pagina inexistente ou fraca."""
    now_iso = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    base_url = "https://antesdosino.com.br"

    urls_xml = (
        "  <url><loc>" + base_url + "/</loc><lastmod>" + now_iso + "</lastmod></url>\n"
        "  <url><loc>" + base_url + "/planos.html</loc><lastmod>" + now_iso + "</lastmod></url>\n"
        "  <url><loc>" + base_url + "/como-funciona.html</loc><lastmod>" + now_iso + "</lastmod></url>\n"
    )

    ativos_dir = diretorio_docs + "/ativos"
    if os.path.isdir(ativos_dir):
        for filename in sorted(os.listdir(ativos_dir)):
            if filename.endswith(".html") and filename != "index.html":
                slug = filename[:-5]
                urls_xml += (
                    "  <url><loc>" + base_url + "/ativos/" + slug + ".html</loc>"
                    "<lastmod>" + now_iso + "</lastmod></url>\n"
                )

    temas_dir = diretorio_docs + "/temas"
    if os.path.isdir(temas_dir):
        for filename in sorted(os.listdir(temas_dir)):
            if filename.endswith(".html") and filename != "index.html":
                slug = filename[:-5]
                urls_xml += (
                    "  <url><loc>" + base_url + "/temas/" + slug + ".html</loc>"
                    "<lastmod>" + now_iso + "</lastmod></url>\n"
                )

    eventos_dir = diretorio_docs + "/eventos"
    if os.path.isdir(eventos_dir):
        for filename in sorted(os.listdir(eventos_dir)):
            if filename.endswith(".html") and filename != "index.html":
                slug = filename[:-5]
                urls_xml += (
                    "  <url><loc>" + base_url + "/eventos/" + slug + ".html</loc>"
                    "<lastmod>" + now_iso + "</lastmod></url>\n"
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


def gerar_paginas_ativos(noticias, diretorio_saida="docs/ativos"):
    """Funcao principal e modular do modulo de paginas de ativos.

    Parametros:
        noticias: lista completa de noticias ja processadas pelo bot
                  (historico acumulado, com campos title/body/source/
                  sentiment/link/time/date).
        diretorio_saida: pasta onde as paginas HTML serao escritas.

    Regras aplicadas:
        - So gera pagina para ativos com pelo menos MIN_NEWS_THRESHOLD
          noticias dentro da janela de ASSET_RECENT_WINDOW_HOURS horas.
        - Ativos sem volume minimo sao ignorados no build e omitidos
          do sitemap.xml.
        - "Ativos relacionados" e calculado por coocorrencia real nas
          noticias + grupo economico, nunca lista todos os ativos.
    """
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in noticias if e.get("date") == today_str]

    os.makedirs(diretorio_saida, exist_ok=True)
    generated = []

    generated_slugs = set()
    for profile in ASSET_PROFILES:
        recent = get_asset_entries_recent(noticias, profile["terms"], ASSET_RECENT_WINDOW_HOURS)
        if len(recent) >= MIN_NEWS_THRESHOLD:
            generated_slugs.add(profile["slug"])

    for profile in ASSET_PROFILES:
        page_html = build_asset_page_html(profile, noticias, entries_today, generated_slugs)
        if page_html is None:
            print("Volume insuficiente para " + profile["slug"] + " (minimo "
                  + str(MIN_NEWS_THRESHOLD) + " noticias em " + str(ASSET_RECENT_WINDOW_HOURS)
                  + "h) - pagina nao gerada.")
            continue
        with open(diretorio_saida + "/" + profile["slug"] + ".html", "w", encoding="utf-8") as f:
            f.write(page_html)
        generated.append(profile)
        print("Pagina de ativo gerada: " + profile["slug"] + ".html")

    if generated:
        index_items = ""
        for p in generated:
            index_items += (
                '<div class="card"><h3><a href="' + p["slug"] + '.html" style="color:var(--cream);">'
                + html_module.escape(p["label"]) + "</a></h3></div>"
            )
        index_page = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            "<title>Ativos acompanhados | Antes do Sino</title>"
            "<link rel='stylesheet' href='../assets.css'></head><body>"
            "<nav><div class='brand'>🔔 Antes do Sino</div>"
            "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"
            "<section><div class='section-head'><span class='kicker'>Ativos</span>"
            "<h2>Ativos acompanhados em tempo real</h2></div>"
            "<div class='feed-grid'>" + index_items + "</div></section>"
            "</body></html>"
        )
        with open(diretorio_saida + "/index.html", "w", encoding="utf-8") as f:
            f.write(index_page)

    gerar_sitemap_completo(diretorio_docs="docs")
    return generated


def generate_asset_pages(all_history, entries_today):
    """Wrapper mantido por compatibilidade com o restante do bot -
    delega para a funcao modular gerar_paginas_ativos."""
    return gerar_paginas_ativos(all_history, diretorio_saida="docs/ativos")


THEME_PROFILES = [
    {"slug": "copom-juros", "label": "Juros & Copom",
     "keywords": ["copom", "selic", "taxa de juros", "fed", "fomc", "roberto campos neto", "jerome powell", "monetária"],
     "why": "Decisões de juros no Brasil e nos EUA afetam diretamente o custo do crédito, o câmbio e a atratividade da bolsa frente à renda fixa."},
    {"slug": "petroleo-commodities", "label": "Petróleo & Commodities",
     "keywords": ["petróleo", "brent", "wti", "opep", "minério de ferro", "vale", "petrobras", "commodities"],
     "why": "Commodities pesam fortemente no Ibovespa e influenciam a inflação global - movimentos aqui se propagam para câmbio e juros."},
    {"slug": "inflacao-fiscal", "label": "Inflação & Meta Fiscal",
     "keywords": ["ipca", "igp-m", "inflação", "arcabouço fiscal", "déficit", "superávit", "haddad", "meta fiscal"],
     "why": "A trajetória fiscal e a inflação são os principais termômetros da confiança dos investidores na economia brasileira."},
    {"slug": "balancos-resultados", "label": "Temporada de Balanços",
     "keywords": ["balanço", "lucro líquido", "receita", "ebitda", "dividendo", "jcp", "proventos", "1tri", "2tri", "3tri", "4tri", "trimestre"],
     "why": "A temporada de resultados revela a saúde financeira real das empresas, movendo preços de ações de forma direta."},
    {"slug": "cambio-dolar", "label": "Câmbio & Dólar",
     "keywords": ["dólar", "cambio", "moeda americana", "real", "ptax", "desvalorização", "valorização"],
     "why": "O dólar impacta importações, inflação e o custo de dívida em moeda estrangeira das empresas brasileiras."},
]

MIN_THEME_NEWS_THRESHOLD = 3


def match_theme_keywords(entry, keywords):
    text = (entry["title"] + " " + entry["body"]).lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
            return True
    return False


def get_theme_entries(all_history, keywords):
    return [e for e in all_history if match_theme_keywords(e, keywords)]


def get_theme_entries_recent(all_history, keywords, hours=ASSET_RECENT_WINDOW_HOURS):
    cutoff = datetime.now(BR_TZ) - timedelta(hours=hours)
    recent = []
    for e in get_theme_entries(all_history, keywords):
        try:
            dt = datetime.strptime(e["date"] + " " + e["time"], "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=BR_TZ)
        except Exception:
            continue
        if dt >= cutoff:
            recent.append(e)
    return recent


def build_theme_summary_sentence(recent_entries, label):
    """Frase unica sobre o momento atual do tema, regra baseada em
    contagem de sentimento - sem chamada extra de IA."""
    if not recent_entries:
        return "Sem notícias recentes sobre " + label + "."

    alta = sum(1 for e in recent_entries if e["sentiment"] == "BULLISH")
    baixa = sum(1 for e in recent_entries if e["sentiment"] == "BEARISH")
    total = len(recent_entries)
    most_recent = sorted(recent_entries, key=lambda e: (e.get("date", ""), e.get("time", "")), reverse=True)[0]

    if alta > baixa:
        return (
            label + " tem predominância de notícias positivas nas últimas 48h ("
            + str(total) + " no total). Destaque: " + most_recent["title"]
        )
    elif baixa > alta:
        return (
            label + " tem predominância de notícias negativas nas últimas 48h ("
            + str(total) + " no total). Destaque: " + most_recent["title"]
        )
    else:
        return (
            label + " teve " + str(total) + " notícia(s) nas últimas 48h, sem "
            "predominância clara de sentimento. Destaque: " + most_recent["title"]
        )


def compute_related_assets_for_theme(theme, all_history, generated_asset_slugs):
    """Ativos relacionados ao tema, por coocorrencia real (a mesma
    noticia do tema tambem menciona o ativo) - nunca lista todos."""
    theme_entries = get_theme_entries(all_history, theme["keywords"])
    scored = []
    for profile in ASSET_PROFILES:
        if profile["slug"] not in generated_asset_slugs:
            continue
        co_occurrence = sum(1 for e in theme_entries if match_asset_terms(e, profile["terms"]))
        if co_occurrence > 0:
            scored.append((profile, co_occurrence))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in scored[:4]]


def compute_related_themes(theme, all_history, generated_theme_slugs):
    """Outros temas relacionados, por coocorrencia real (mesma noticia
    aparece nos dois temas) - nunca lista todos os temas."""
    theme_entries = get_theme_entries(all_history, theme["keywords"])
    scored = []
    for other in THEME_PROFILES:
        if other["slug"] == theme["slug"] or other["slug"] not in generated_theme_slugs:
            continue
        co_occurrence = sum(1 for e in theme_entries if match_theme_keywords(e, other["keywords"]))
        if co_occurrence > 0:
            scored.append((other, co_occurrence))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in scored[:3]]


def build_theme_page_html(theme, all_history, generated_asset_slugs, generated_theme_slugs):
    slug = theme["slug"]
    label = theme["label"]
    keywords = theme["keywords"]
    why_it_matters = theme["why"]

    theme_history_entries = get_theme_entries(all_history, keywords)
    theme_recent_entries = get_theme_entries_recent(all_history, keywords, ASSET_RECENT_WINDOW_HOURS)

    if len(theme_recent_entries) < MIN_THEME_NEWS_THRESHOLD:
        return None

    summary_sentence = build_theme_summary_sentence(theme_recent_entries, label)

    def sentiment_badge(s):
        if s == "BULLISH":
            return '<span class="badge alta">ALTA</span>'
        if s == "BEARISH":
            return '<span class="badge baixa">BAIXA</span>'
        return '<span class="badge info">INFO</span>'

    def render_card(e):
        return (
            '<div class="card">'
            '<div class="card-meta">' + sentiment_badge(e["sentiment"]) +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e.get("date", "") + " " + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            "</div>\n"
        )

    # Bloco 2: agrupado por sentimento (Bullish / Bearish / Neutral),
    # conforme pedido - nao por similaridade de titulo como nos ativos.
    bullish_items = [e for e in theme_recent_entries if e["sentiment"] == "BULLISH"]
    bearish_items = [e for e in theme_recent_entries if e["sentiment"] == "BEARISH"]
    neutral_items = [e for e in theme_recent_entries if e["sentiment"] == "NEUTRAL"]

    def render_sentiment_group(items, group_title, group_class):
        if not items:
            return ""
        cards = ""
        for e in items[:6]:
            cards += render_card(e)
        return (
            "<div style='margin-bottom:28px;'>"
            "<h3 style='color:var(--" + group_class + ");font-size:1rem;margin-bottom:12px;'>"
            + group_title + " (" + str(len(items)) + ")</h3>"
            "<div class='feed-grid'>" + cards + "</div>"
            "</div>"
        )

    sentiment_groups_html = (
        render_sentiment_group(bullish_items, "🟢 Notícias de Alta", "up")
        + render_sentiment_group(bearish_items, "🟡 Notícias de Baixa", "down")
        + render_sentiment_group(neutral_items, "⚪ Informativas", "slate")
    )
    if not sentiment_groups_html:
        sentiment_groups_html = '<p style="color:var(--slate);">Sem notícias suficientes agrupadas ainda.</p>'

    # Bloco 3: feed cronologico completo do tema
    chrono_html = ""
    sorted_all = sorted(theme_history_entries, key=lambda e: (e.get("date", ""), e.get("time", "")), reverse=True)
    for e in sorted_all[:30]:
        link = e.get("link", "#") or "#"
        chrono_html += (
            '<div class="card">'
            '<div class="card-meta">' + sentiment_badge(e["sentiment"]) +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e.get("date", "") + " " + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a>'
            "</div>\n"
        )

    # Bloco 4: links para ativos e temas relacionados
    related_assets = compute_related_assets_for_theme(theme, all_history, generated_asset_slugs)
    related_themes = compute_related_themes(theme, all_history, generated_theme_slugs)

    related_links_html = ""
    for a in related_assets:
        related_links_html += '<a href="../ativos/' + a["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(a["label"]) + "</a>"
    for t in related_themes:
        related_links_html += '<a href="' + t["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(t["label"]) + "</a>"

    related_block = ""
    if related_links_html:
        related_block = (
            "<section><div class='section-head'>"
            "<span class='kicker'>Continue explorando</span>"
            "</div>"
            "<div>" + related_links_html + "</div>"
            "</section>"
        )

    meta_description = html_module.escape(summary_sentence[:155])
    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")
    page_url = "https://antesdosino.com.br/temas/" + slug + ".html"
    page_title = html_module.escape(label) + " hoje - notícias e sentimento | Antes do Sino"

    schema_items = []
    for e in sorted_all[:10]:
        schema_items.append({
            "@type": "ListItem",
            "position": len(schema_items) + 1,
            "url": e.get("link", page_url) or page_url,
            "name": e["title"],
        })
    schema_json = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": label,
        "url": page_url,
        "mainEntity": {
            "@type": "ItemList",
            "name": "Notícias sobre " + label,
            "itemListElement": schema_items,
        },
    }
    schema_script = json.dumps(schema_json, ensure_ascii=False)

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>" + page_title + "</title>"
        "<meta name='description' content='" + meta_description + "'>"
        "<link rel='canonical' href='" + page_url + "'>"
        "<meta property='og:type' content='website'>"
        "<meta property='og:title' content='" + page_title + "'>"
        "<meta property='og:description' content='" + meta_description + "'>"
        "<meta property='og:url' content='" + page_url + "'>"
        "<meta property='og:site_name' content='Antes do Sino'>"
        "<meta name='twitter:card' content='summary'>"
        "<meta name='twitter:title' content='" + page_title + "'>"
        "<meta name='twitter:description' content='" + meta_description + "'>"
        "<link rel='stylesheet' href='../assets.css'>"
        "<script type='application/ld+json'>" + schema_script + "</script>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Tema</span>"
        "<h1 style='font-family:Fraunces,serif;font-size:2rem;font-weight:600;'>" + html_module.escape(label) + "</h1>"
        "<p style='color:var(--slate);margin-top:14px;font-size:1.05rem;'>" + html_module.escape(summary_sentence) + "</p>"
        "<p style='color:var(--slate-dim);margin-top:10px;font-size:0.9rem;border-left:2px solid var(--bronze);padding-left:12px;'>"
        "<b style='color:var(--bronze);'>Por que isso importa agora:</b> " + html_module.escape(why_it_matters) + "</p>"
        "</div></section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>O que está movendo o tema</span>"
        "<h2>Notícias agrupadas por sentimento</h2>"
        "</div>"
        + sentiment_groups_html +
        "</section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Aprofunde-se</span>"
        "<h2>Todas as notícias sobre " + html_module.escape(label) + "</h2>"
        "</div>"
        "<div class='feed-grid'>" + chrono_html + "</div>"
        "</section>"

        + related_block +

        "<footer><span>&copy; Antes do Sino — dados públicos, não é recomendação de investimento.</span>"
        "<span class='mono'>Atualizado em " + updated_at + "</span></footer>"
        "</body></html>"
    )

    return page


def gerar_paginas_temas(noticias, diretorio_saida="docs/temas"):
    """Funcao principal e modular de geracao das paginas de tema.

    Parametros:
        noticias: lista completa de noticias ja processadas pelo bot
                  (historico acumulado).
        diretorio_saida: pasta onde as paginas HTML serao escritas.

    Regras aplicadas:
        - So gera pagina para temas com pelo menos
          MIN_THEME_NEWS_THRESHOLD noticias qualificadas dentro da
          janela de ASSET_RECENT_WINDOW_HOURS horas.
        - Links relacionados (ativos e outros temas) sao calculados por
          coocorrencia real nas noticias, nunca listam tudo.
        - Atualiza o sitemap.xml ao final, incluindo os temas gerados.
    """
    os.makedirs(diretorio_saida, exist_ok=True)
    generated = []

    generated_theme_slugs = set()
    for theme in THEME_PROFILES:
        recent = get_theme_entries_recent(noticias, theme["keywords"], ASSET_RECENT_WINDOW_HOURS)
        if len(recent) >= MIN_THEME_NEWS_THRESHOLD:
            generated_theme_slugs.add(theme["slug"])

    generated_asset_slugs = set()
    for profile in ASSET_PROFILES:
        recent = get_asset_entries_recent(noticias, profile["terms"], ASSET_RECENT_WINDOW_HOURS)
        if len(recent) >= MIN_NEWS_THRESHOLD:
            generated_asset_slugs.add(profile["slug"])

    for theme in THEME_PROFILES:
        page_html = build_theme_page_html(theme, noticias, generated_asset_slugs, generated_theme_slugs)
        if page_html is None:
            print("Volume insuficiente para tema " + theme["slug"] + " (minimo "
                  + str(MIN_THEME_NEWS_THRESHOLD) + " noticias em " + str(ASSET_RECENT_WINDOW_HOURS)
                  + "h) - pagina nao gerada.")
            continue
        with open(diretorio_saida + "/" + theme["slug"] + ".html", "w", encoding="utf-8") as f:
            f.write(page_html)
        generated.append(theme)
        print("Pagina de tema gerada: " + theme["slug"] + ".html")

    if generated:
        index_items = ""
        for t in generated:
            index_items += (
                '<div class="card"><h3><a href="' + t["slug"] + '.html" style="color:var(--cream);">'
                + html_module.escape(t["label"]) + "</a></h3></div>"
            )
        index_page = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            "<title>Temas acompanhados | Antes do Sino</title>"
            "<link rel='stylesheet' href='../assets.css'></head><body>"
            "<nav><div class='brand'>🔔 Antes do Sino</div>"
            "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"
            "<section><div class='section-head'><span class='kicker'>Temas</span>"
            "<h2>Temas acompanhados em tempo real</h2></div>"
            "<div class='feed-grid'>" + index_items + "</div></section>"
            "</body></html>"
        )
        with open(diretorio_saida + "/index.html", "w", encoding="utf-8") as f:
            f.write(index_page)

    gerar_sitemap_completo(diretorio_docs="docs")
    return generated


MIN_EVENT_NEWS_THRESHOLD = 2
EVENT_WINDOW_DAYS_PAST = 2
EVENT_WINDOW_DAYS_FUTURE = 30


def slugify_label(label):
    """Converte um rotulo de evento em slug de URL, sem depender de
    biblioteca externa - remove acentos via unicodedata (biblioteca
    padrao do Python) e troca qualquer caractere fora de a-z0-9 por
    hifen."""
    normalized = unicodedata.normalize("NFKD", label)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    lowered = without_accents.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug


def get_event_keywords(event):
    """Retorna as palavras-chave do evento, com fallback para eventos
    antigos no registro que foram salvos antes do campo 'keywords'
    existir - nesse caso, deriva palavras a partir do proprio rotulo."""
    keywords = event.get("keywords", [])
    if keywords:
        return keywords
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", event["label"].lower())
    return words[:4]


def match_event_keywords(entry, keywords):
    text = (entry["title"] + " " + entry["body"]).lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
            return True
    return False


def get_event_entries(all_history, event):
    keywords = get_event_keywords(event)
    if not keywords:
        return []
    return [e for e in all_history if match_event_keywords(e, keywords)]


def is_event_in_window(event_date_str, days_past=EVENT_WINDOW_DAYS_PAST, days_future=EVENT_WINDOW_DAYS_FUTURE):
    """Verifica se a data do evento esta dentro da janela valida:
    ocorrido ha no maximo 'days_past' dias, ou previsto para os
    proximos 'days_future' dias."""
    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except Exception:
        return False
    today = datetime.now(BR_TZ).date()
    days_diff = (event_date - today).days
    return -days_past <= days_diff <= days_future


def compute_related_assets_for_event(event_entries, generated_asset_slugs):
    scored = []
    for profile in ASSET_PROFILES:
        if profile["slug"] not in generated_asset_slugs:
            continue
        co_occurrence = sum(1 for e in event_entries if match_asset_terms(e, profile["terms"]))
        if co_occurrence > 0:
            scored.append((profile, co_occurrence))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in scored[:4]]


def compute_related_themes_for_event(event_entries, generated_theme_slugs):
    scored = []
    for theme in THEME_PROFILES:
        if theme["slug"] not in generated_theme_slugs:
            continue
        co_occurrence = sum(1 for e in event_entries if match_theme_keywords(e, theme["keywords"]))
        if co_occurrence > 0:
            scored.append((theme, co_occurrence))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in scored[:3]]


def build_event_page_html(event, all_history, generated_asset_slugs, generated_theme_slugs):
    label = event["label"]
    event_date_str = event["date"]
    keywords = get_event_keywords(event)
    slug = slugify_label(label)

    event_entries = get_event_entries(all_history, event)

    if len(event_entries) < MIN_EVENT_NEWS_THRESHOLD:
        return None
    if not is_event_in_window(event_date_str):
        return None

    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    today = datetime.now(BR_TZ).date()
    days_diff = (event_date - today).days
    display_date = event_date.strftime("%d/%m/%Y")

    if days_diff > 0:
        timing_note = "Previsto para " + display_date + " (em " + str(days_diff) + " dia(s))."
    elif days_diff == 0:
        timing_note = "Acontece hoje, " + display_date + "."
    else:
        timing_note = "Ocorreu em " + display_date + " (há " + str(abs(days_diff)) + " dia(s))."

    organizer = event.get("organizer") or guess_event_organizer(label, keywords)

    def sentiment_badge(s):
        if s == "BULLISH":
            return '<span class="badge alta">ALTA</span>'
        if s == "BEARISH":
            return '<span class="badge baixa">BAIXA</span>'
        return '<span class="badge info">INFO</span>'

    def render_card(e):
        link = e.get("link", "#") or "#"
        return (
            '<div class="card">'
            '<div class="card-meta">' + sentiment_badge(e["sentiment"]) +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e.get("date", "") + " " + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a>'
            "</div>\n"
        )

    bullish_items = [e for e in event_entries if e["sentiment"] == "BULLISH"]
    bearish_items = [e for e in event_entries if e["sentiment"] == "BEARISH"]
    neutral_items = [e for e in event_entries if e["sentiment"] == "NEUTRAL"]

    def render_group(items, title, color_var):
        if not items:
            return ""
        cards = ""
        for e in items[:6]:
            cards += render_card(e)
        return (
            "<div style='margin-bottom:28px;'>"
            "<h3 style='color:var(--" + color_var + ");font-size:1rem;margin-bottom:12px;'>"
            + title + " (" + str(len(items)) + ")</h3>"
            "<div class='feed-grid'>" + cards + "</div>"
            "</div>"
        )

    sentiment_groups_html = (
        render_group(bullish_items, "🟢 Notícias de Alta", "up")
        + render_group(bearish_items, "🟡 Notícias de Baixa", "down")
        + render_group(neutral_items, "⚪ Informativas", "slate")
    )
    if not sentiment_groups_html:
        sentiment_groups_html = '<p style="color:var(--slate);">Sem notícias suficientes agrupadas ainda.</p>'

    related_assets = compute_related_assets_for_event(event_entries, generated_asset_slugs)
    related_themes = compute_related_themes_for_event(event_entries, generated_theme_slugs)

    related_links_html = ""
    for a in related_assets:
        related_links_html += '<a href="../ativos/' + a["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(a["label"]) + "</a>"
    for t in related_themes:
        related_links_html += '<a href="../temas/' + t["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(t["label"]) + "</a>"

    related_block = ""
    if related_links_html:
        related_block = (
            "<section><div class='section-head'>"
            "<span class='kicker'>Ativos e temas impactados</span>"
            "</div>"
            "<div>" + related_links_html + "</div>"
            "</section>"
        )

    summary_context = (
        label + ". " + timing_note + " Acompanhe abaixo o que as notícias mais recentes "
        "dizem sobre o possível impacto no mercado."
    )
    meta_description = html_module.escape(summary_context[:155])
    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")
    page_url = "https://antesdosino.com.br/eventos/" + slug + ".html"
    page_title = html_module.escape(label) + " - contexto e notícias | Antes do Sino"

    schema_json = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": label,
        "startDate": event_date_str,
        "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
        "location": {
            "@type": "VirtualLocation",
            "url": page_url,
        },
        "description": summary_context,
        "organizer": {
            "@type": "Organization",
            "name": organizer,
        },
    }
    schema_script = json.dumps(schema_json, ensure_ascii=False)

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>" + page_title + "</title>"
        "<meta name='description' content='" + meta_description + "'>"
        "<link rel='canonical' href='" + page_url + "'>"
        "<meta property='og:type' content='website'>"
        "<meta property='og:title' content='" + page_title + "'>"
        "<meta property='og:description' content='" + meta_description + "'>"
        "<meta property='og:url' content='" + page_url + "'>"
        "<meta property='og:site_name' content='Antes do Sino'>"
        "<meta name='twitter:card' content='summary'>"
        "<meta name='twitter:title' content='" + page_title + "'>"
        "<meta name='twitter:description' content='" + meta_description + "'>"
        "<link rel='stylesheet' href='../assets.css'>"
        "<script type='application/ld+json'>" + schema_script + "</script>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Evento</span>"
        "<h1 style='font-family:Fraunces,serif;font-size:2rem;font-weight:600;'>" + html_module.escape(label) + "</h1>"
        "<p style='color:var(--gold);margin-top:10px;font-weight:600;'>" + timing_note + "</p>"
        "<p style='color:var(--slate);margin-top:14px;font-size:1.05rem;'>Acompanhe o que o mercado está dizendo "
        "sobre este evento e o possível impacto nos preços.</p>"
        "</div></section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Notícias e análises relacionadas</span>"
        "<h2>O que estão dizendo sobre este evento</h2>"
        "</div>"
        + sentiment_groups_html +
        "</section>"

        + related_block +

        "<footer><span>&copy; Antes do Sino — dados públicos, não é recomendação de investimento.</span>"
        "<span class='mono'>Atualizado em " + updated_at + "</span></footer>"
        "</body></html>"
    )

    return page


def gerar_paginas_eventos(noticias, diretorio_saida="docs/eventos"):
    """Funcao principal e modular de geracao das paginas de evento.

    Parametros:
        noticias: lista completa de noticias ja processadas pelo bot
                  (historico acumulado).
        diretorio_saida: pasta onde as paginas HTML serao escritas.

    Regras aplicadas:
        - Fonte dos eventos: registro automatico (events_detected.json,
          extraido pela Groq a partir das proprias noticias) + lista
          minima de referencia (SEED_EVENTS).
        - So gera pagina se a data estiver dentro da janela valida
          (ocorrido ha no maximo 2 dias, ou previsto para os proximos
          30 dias) E houver pelo menos MIN_EVENT_NEWS_THRESHOLD
          noticias associadas.
        - Links para ativos/temas sao por coocorrencia real, nunca
          listam tudo.
        - Atualiza o sitemap.xml ao final (via escaneamento de disco).
    """
    os.makedirs(diretorio_saida, exist_ok=True)

    events_state = load_events_state()
    candidate_events = list(SEED_EVENTS) + events_state.get("events", [])

    seen_labels = set()
    unique_events = []
    for ev in candidate_events:
        key = ev["label"].lower().strip()
        if key not in seen_labels:
            seen_labels.add(key)
            unique_events.append(ev)

    generated_theme_slugs = set()
    for theme in THEME_PROFILES:
        recent = get_theme_entries_recent(noticias, theme["keywords"], ASSET_RECENT_WINDOW_HOURS)
        if len(recent) >= MIN_THEME_NEWS_THRESHOLD:
            generated_theme_slugs.add(theme["slug"])

    generated_asset_slugs = set()
    for profile in ASSET_PROFILES:
        recent = get_asset_entries_recent(noticias, profile["terms"], ASSET_RECENT_WINDOW_HOURS)
        if len(recent) >= MIN_NEWS_THRESHOLD:
            generated_asset_slugs.add(profile["slug"])

    generated = []
    for event in unique_events:
        page_html = build_event_page_html(event, noticias, generated_asset_slugs, generated_theme_slugs)
        if page_html is None:
            print("Evento '" + event["label"] + "' fora da janela valida ou sem "
                  "volume minimo - pagina nao gerada.")
            continue
        slug = slugify_label(event["label"])
        with open(diretorio_saida + "/" + slug + ".html", "w", encoding="utf-8") as f:
            f.write(page_html)
        generated.append({"slug": slug, "label": event["label"]})
        print("Pagina de evento gerada: " + slug + ".html")

    if generated:
        index_items = ""
        for ev in generated:
            index_items += (
                '<div class="card"><h3><a href="' + ev["slug"] + '.html" style="color:var(--cream);">'
                + html_module.escape(ev["label"]) + "</a></h3></div>"
            )
        index_page = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            "<title>Eventos acompanhados | Antes do Sino</title>"
            "<link rel='stylesheet' href='../assets.css'></head><body>"
            "<nav><div class='brand'>🔔 Antes do Sino</div>"
            "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"
            "<section><div class='section-head'><span class='kicker'>Eventos</span>"
            "<h2>Eventos econômicos acompanhados</h2></div>"
            "<div class='feed-grid'>" + index_items + "</div></section>"
            "</body></html>"
        )
        with open(diretorio_saida + "/index.html", "w", encoding="utf-8") as f:
            f.write(index_page)

    gerar_sitemap_completo(diretorio_docs="docs")
    return generated


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
            return {"last_morning_date": "", "last_evening_date": ""}
    return {"last_morning_date": "", "last_evening_date": ""}


def save_briefings_state(state):
    os.makedirs(os.path.dirname(BRIEFINGS_STATE_FILE), exist_ok=True)
    with open(BRIEFINGS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def should_send_morning_briefing():
    """Janela de 08h15 as 08h45, uma vez por dia."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_briefings_state()
    if state.get("last_morning_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (8 * 60 + 15) <= minutes <= (8 * 60 + 45)


def should_send_evening_briefing():
    """Janela de 18h15 as 18h45, uma vez por dia."""
    now = datetime.now(BR_TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_briefings_state()
    if state.get("last_evening_date") == today_str:
        return False
    minutes = now.hour * 60 + now.minute
    return (18 * 60 + 15) <= minutes <= (18 * 60 + 45)


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


def get_br_asset_radar(entries, limit=3):
    """Retorna os papeis da B3 (excluindo big techs americanas) com
    maior densidade de noticias recentes - usado no radar de acoes."""
    counts = []
    for profile in ASSET_PROFILES:
        if profile["group"] not in BR_ASSET_GROUPS:
            continue
        count = len(get_asset_entries(entries, profile["terms"]))
        if count > 0:
            counts.append((profile, count))
    counts.sort(key=lambda pair: pair[1], reverse=True)
    return [pair[0] for pair in counts[:limit]]


def summarize_briefing_with_ai(entries, tipo):
    """Uma unica chamada a Groq para gerar a sintese executiva do
    briefing (1 a 2 frases), focada no mercado brasileiro. 'tipo' e
    'abertura' ou 'fechamento'."""
    if not USE_AI or not entries:
        return "Sem dados suficientes para uma sintese hoje."

    headlines_text = ""
    for e in entries[:15]:
        headlines_text += "- " + e["title"] + "\n"

    if tipo == "abertura":
        instrucao = (
            "Escreva uma sintese de 1 a 2 frases sobre o principal vetor esperado para "
            "o pregao de hoje na B3 (Ibovespa), com base nas manchetes abaixo. Foque "
            "em commodities, dolar, noticiario politico/fiscal ou balancos locais. "
            "Responda em portugues do Brasil, texto simples, sem markdown, sem aspas."
        )
    else:
        instrucao = (
            "Escreva uma sintese de 1 a 2 frases sobre o que moveu o pregao de hoje na "
            "B3 (Ibovespa), com base nas manchetes abaixo. Responda em portugues do "
            "Brasil, texto simples, sem markdown, sem aspas."
        )

    prompt = instrucao + "\n\nManchetes:\n" + headlines_text

    try:
        response = ask_groq(prompt)
        return response.strip().strip('"')
    except Exception as e:
        print("Erro ao gerar sintese do briefing (Groq): " + str(e))
        return "Sintese indisponivel no momento - confira as noticias completas no site."


def build_morning_briefing_message(entries_today, eventos):
    """Monta o texto do Morning Briefing ('Antes do Sino - Abertura B3')."""
    today_str = datetime.now(BR_TZ).strftime("%d/%m/%Y")
    today_iso = datetime.now(BR_TZ).strftime("%Y-%m-%d")

    br_entries = get_brazil_relevant_entries(entries_today)
    sintese = summarize_briefing_with_ai(br_entries, "abertura")

    eventos_hoje = [
        ev for ev in eventos
        if ev.get("date") == today_iso and is_event_brazil_focused(ev)
    ][:3]

    eventos_texto = ""
    if eventos_hoje:
        for ev in eventos_hoje:
            eventos_texto += "• " + ev["label"] + "\n"
    else:
        eventos_texto = "Nenhum evento de grande destaque previsto para hoje.\n"

    radar_assets = get_br_asset_radar(br_entries, limit=3)
    radar_texto = ""
    if radar_assets:
        for a in radar_assets:
            radar_texto += "• " + a["label"] + "\n"
    else:
        radar_texto = "Sem destaque de papel especifico ate o momento.\n"

    message = (
        "🔔 <b>ANTES DO SINO — ABERTURA B3</b>\n"
        + today_str + "\n\n"
        "🇧🇷 <b>RADAR DO IBOVESPA</b>\n"
        + html_module.escape(sintese) + "\n\n"
        "📌 <b>EVENTOS DO DIA NA B3 / BRASIL</b>\n"
        + html_module.escape(eventos_texto) + "\n"
        "🎯 <b>AÇÕES E SETORES NO RADAR</b>\n"
        + html_module.escape(radar_texto) + "\n"
        "🌐 Acompanhe ao vivo em antesdosino.com.br"
    )
    return message


def build_evening_briefing_message(entries_today, eventos):
    """Monta o texto do Evening Briefing ('Depois do Sino - Fechamento B3')."""
    today_str = datetime.now(BR_TZ).strftime("%d/%m/%Y")
    tomorrow_iso = (datetime.now(BR_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

    br_entries = get_brazil_relevant_entries(entries_today)
    sintese = summarize_briefing_with_ai(br_entries, "fechamento")

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

    message = (
        "🌆 <b>DEPOIS DO SINO — FECHAMENTO B3</b>\n"
        + today_str + "\n\n"
        "📊 <b>BALANÇO DO PREGÃO</b>\n"
        + html_module.escape(sintese) + "\n\n"
        "🔥 <b>O QUE MOVEU A BOLSA HOJE</b>\n"
        + html_module.escape(top_pautas) + "\n"
        "📅 <b>AMANHÃ NA B3</b>\n"
        + html_module.escape(eventos_texto) + "\n"
        "🌐 Análise completa em antesdosino.com.br"
    )
    return message


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


def processar_briefings_telegram(noticias, eventos, telegram_bot_token, telegram_chat_id):
    """Funcao principal e modular dos briefings automaticos.

    Parametros:
        noticias: lista completa de noticias ja processadas pelo bot.
        eventos: lista combinada de eventos (SEED_EVENTS + registro
                 automatico extraido de events_detected.json).
        telegram_bot_token / telegram_chat_id: credenciais do canal VIP.

    Comportamento:
        - So dispara dentro da janela de horario correspondente (manha
          08h15-08h45, noite 18h15-18h45).
        - Cada briefing e enviado no maximo 1 vez por dia (controle via
          docs/briefings_state.json).
        - Foco editorial 100% Brasil, conforme diretriz do projeto.
    """
    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in noticias if e.get("date") == today_str]
    state = load_briefings_state()

    if should_send_morning_briefing():
        message = build_morning_briefing_message(entries_today, eventos)
        if send_briefing_message(message, telegram_bot_token, telegram_chat_id):
            state["last_morning_date"] = today_str
            save_briefings_state(state)
            print("Morning Briefing enviado com sucesso.")
        else:
            print("Falha ao enviar Morning Briefing - sera tentado novamente no proximo ciclo dentro da janela.")

    if should_send_evening_briefing():
        message = build_evening_briefing_message(entries_today, eventos)
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
    text = re.sub(r"\n*Grupo Bovespa News\s*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^\s*t\.me/\S+\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text


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


def classify_channel_sentiment(title):
    """Classificacao leve por palavra-chave (sem chamada de IA) - os
    posts encaminhados sao curtos e diretos, entao essa heuristica e
    suficiente e evita gasto extra de cota da Groq."""
    title_lower = title.lower()
    if any(w in title_lower for w in ["alta", "sobe", "lucro", "dispara", "recorde", "bullish"]):
        return "BULLISH"
    elif any(w in title_lower for w in ["queda", "cai", "prejuizo", "desaba", "recua", "bearish"]):
        return "BEARISH"
    else:
        return "NEUTRAL"


def process_forwarded_channels():
    """Busca posts novos dos canais encaminhados, envia ao grupo do
    Telegram, e retorna uma lista de entradas no MESMO formato usado
    pelo restante do pipeline (title/body/source/sentiment/link/time/
    date) - assim esse conteudo passa a contar para os Sinais do Dia,
    paginas de ativo/tema/evento e briefings, nao so aparece no grupo."""
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

        for post in new_posts:
            clean_text = clean_channel_post_text(post["text"])

            if is_channel_bio(clean_text):
                print("Ignorado (bio do canal): " + clean_text[:60])
                continue
            if not clean_text:
                continue

            fonte_detectada = detect_real_source(clean_text, clean_channel)
            clean_text = re.sub(
                r"(?i)^\s*(reuters|bloomberg|cnbc|wsj)\s*$", "", clean_text, flags=re.MULTILINE
            ).strip()

            linhas = [l.strip() for l in clean_text.split("\n") if l.strip()]
            if not linhas:
                continue

            titulo_puro = linhas[0]
            sentiment = classify_channel_sentiment(titulo_puro)

            if sentiment == "BULLISH":
                marker = "\U0001F7E2 <b>[ALTA]</b>"
            elif sentiment == "BEARISH":
                marker = "\U0001F7E1 <b>[BAIXA]</b>"
            else:
                marker = "\u26AA <b>[INFORMATIVO]</b>"

            titulo_escapado = html_module.escape(titulo_puro, quote=False)

            if len(linhas) > 1:
                corpo_puro = "\n".join(linhas[1:]).strip()
                corpo_puro = re.sub(r"(?i)pontos[- ]chave:?", "", corpo_puro)
            else:
                corpo_puro = ""
            corpo_escapado = html_module.escape(corpo_puro, quote=False)

            is_real_agency = fonte_detectada in KNOWN_AGENCIES
            fonte_tag = html_module.escape(fonte_detectada, quote=False)

            if corpo_escapado and is_real_agency:
                message = marker + " <b>" + titulo_escapado + "</b>\n\n" + corpo_escapado + "\n\n<i>Fonte: " + fonte_tag + "</i>"
            elif corpo_escapado:
                message = marker + " <b>" + titulo_escapado + "</b>\n\n" + corpo_escapado
            elif is_real_agency:
                message = marker + " <b>" + titulo_escapado + "</b>\n\n<i>Fonte: " + fonte_tag + "</i>"
            else:
                message = marker + " <b>" + titulo_escapado + "</b>"

            if len(message) > 3900:
                message = message[:3900] + "..."

            if send_telegram_message(message):
                post_link = "https://t.me/" + clean_channel + "/" + str(post["id"])
                now = datetime.now(BR_TZ)
                print("Encaminhado de " + clean_channel + " (id " + str(post["id"]) + "): " + clean_text[:40] + "...")

                new_portal_entries.append({
                    "title": titulo_puro,
                    "body": corpo_puro[:200] if corpo_puro else "Leia mais no link.",
                    "source": CHANNEL_DISPLAY_NAMES.get(clean_channel.lower(), clean_channel),
                    "sentiment": sentiment,
                    "link": post_link,
                    "time": now.strftime("%H:%M"),
                    "date": now.strftime("%Y-%m-%d"),
                })

                state[clean_channel] = post["id"]
                has_updates = True
                time.sleep(3)

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
    start_marker_w = "<!-- WORRY_LINE_START -->"
    end_marker_w = "<!-- WORRY_LINE_END -->"
    start_marker_s = "<!-- SIGNALS_START -->"
    end_marker_s = "<!-- SIGNALS_END -->"
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
        cockpit_html = build_cockpit_html(entries, entries_today)
        before = template.split(start_marker_k)[0]
        after = template.split(end_marker_k)[1]
        template = before + start_marker_k + "\n" + cockpit_html + end_marker_k + after

    if start_marker_w in template and end_marker_w in template:
        worry_html = build_worry_line_html(clusters)
        before = template.split(start_marker_w)[0]
        after = template.split(end_marker_w)[1]
        template = before + start_marker_w + "\n" + worry_html + end_marker_w + after

    if start_marker_s in template and end_marker_s in template:
        generated_asset_slugs_for_home = set()
        for profile in ASSET_PROFILES:
            recent = get_asset_entries_recent(entries, profile["terms"], ASSET_RECENT_WINDOW_HOURS)
            if len(recent) >= MIN_NEWS_THRESHOLD:
                generated_asset_slugs_for_home.add(profile["slug"])
        signals_html = build_signals_html(clusters, generated_asset_slugs_for_home)
        before = template.split(start_marker_s)[0]
        after = template.split(end_marker_s)[1]
        template = before + start_marker_s + "\n" + signals_html + end_marker_s + after

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

    try:
        forwarded_entries = process_forwarded_channels()
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

    generate_portal(all_portal_entries, entries_today)
    build_daily_summary_html(entries_today, today_str)
    generate_asset_pages(all_portal_entries, entries_today)
    gerar_paginas_temas(all_portal_entries, diretorio_saida="docs/temas")
    gerar_paginas_eventos(all_portal_entries, diretorio_saida="docs/eventos")

    try:
        events_state_for_briefing = load_events_state()
        combined_events = list(SEED_EVENTS) + events_state_for_briefing.get("events", [])
        processar_briefings_telegram(all_portal_entries, combined_events, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        print("Erro ao processar briefings (isolado, nao afeta o fluxo principal): " + str(e))

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
