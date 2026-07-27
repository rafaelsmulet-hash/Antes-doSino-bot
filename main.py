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
            '<a href="' + link + '" class="read" target="_blank">Leia mais &rarr;</a>'
            "</div>\n"
        )
    return cards_html


EVENTS_STATE_FILE = "events_detected.json"

SEED_EVENTS = [
    {"date": "2026-08-04", "label": "Reunião do Copom (decisão da Selic)"},
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


def extract_events_from_news(entries_today):
    """Usa a Groq para ler as manchetes do dia e identificar mencoes a
    eventos futuros especificos (reunioes, decisoes, divulgacoes) com
    data conhecida - permitindo que a secao de eventos se atualize
    sozinha, sem precisar de aviso manual."""
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
        '[{"date": "AAAA-MM-DD", "label": "Descricao curta do evento"}]\n\n'
        "Se nao houver nenhum evento futuro claro e com data especifica mencionada, "
        "responda apenas: []"
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
                valid.append({"date": item["date"], "label": item["label"]})
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
        existing = [
            e for e in existing
            if datetime.strptime(e["date"], "%Y-%m-%d").date() >= today_date
        ]

        state["events"] = existing
        state["last_extraction_date"] = today_str
        save_events_state(state)

    return state.get("events", [])


def build_events_html(entries_today):
    """Mostra eventos vindos do registro automatico (extraido das
    proprias noticias) combinado com a lista minima de referencia -
    nunca forca conteudo vazio."""
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
        events_html += (
            '<div class="event-item">'
            '<span class="event-countdown">' + countdown + "</span>"
            '<span class="event-label">' + html_module.escape(ev["label"]) + "</span>"
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
    {"slug": "petr4", "label": "Petrobras (PETR4)", "terms": ["petr4", "petr3", "petrobras"]},
    {"slug": "vale3", "label": "Vale (VALE3)", "terms": ["vale3", "vale"]},
    {"slug": "itub4", "label": "Itaú (ITUB4)", "terms": ["itub4", "itau", "itaú"]},
    {"slug": "b3sa3", "label": "B3 (B3SA3)", "terms": ["b3sa3"]},
    {"slug": "bbas3", "label": "Banco do Brasil (BBAS3)", "terms": ["bbas3", "banco do brasil"]},
    {"slug": "wege3", "label": "WEG (WEGE3)", "terms": ["wege3", "weg"]},
    {"slug": "aapl", "label": "Apple (AAPL)", "terms": ["aapl", "apple"]},
    {"slug": "tsla", "label": "Tesla (TSLA)", "terms": ["tsla", "tesla"]},
    {"slug": "nvda", "label": "Nvidia (NVDA)", "terms": ["nvda", "nvidia"]},
    {"slug": "msft", "label": "Microsoft (MSFT)", "terms": ["msft", "microsoft"]},
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


def get_asset_entries(all_history, terms):
    return [e for e in all_history if match_asset_terms(e, terms)]


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


def build_asset_page_html(profile, all_history, entries_today):
    slug = profile["slug"]
    label = profile["label"]
    terms = profile["terms"]

    asset_history_entries = get_asset_entries(all_history, terms)
    asset_today_entries = get_asset_entries(entries_today, terms)

    if not asset_history_entries:
        return None

    trend = update_asset_archive_entry(slug, asset_today_entries)
    summary_sentence = compute_asset_summary_sentence(asset_today_entries, label)
    clusters = compute_asset_clusters(asset_today_entries)

    def sentiment_badge(s):
        if s == "BULLISH":
            return '<span class="badge alta">ALTA</span>'
        if s == "BEARISH":
            return '<span class="badge baixa">BAIXA</span>'
        return '<span class="badge info">INFO</span>'

    clusters_html = ""
    for c in clusters[:3]:
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

    ranked_all = sorted(
        asset_today_entries,
        key=lambda e: (0 if e["sentiment"] == "NEUTRAL" else 1, e.get("time", "")),
        reverse=True
    )[:8]
    ranked_html = ""
    for e in ranked_all:
        ranked_html += (
            '<div class="card">'
            '<div class="card-meta">' + sentiment_badge(e["sentiment"]) +
            '<span class="src">' + html_module.escape(e["source"]) + "</span>"
            '<span class="time">' + e["time"] + "</span></div>"
            "<h3>" + html_module.escape(e["title"]) + "</h3>"
            "<p>" + html_module.escape(e["body"]) + "</p>"
            "</div>\n"
        )
    if not ranked_html:
        ranked_html = '<p style="color:var(--slate);">Sem movimentações relevantes hoje.</p>'

    trend_rows = ""
    for day in reversed(trend[-7:]):
        trend_rows += (
            "<div class='event-item'><span class='event-date'>" + day["date"] + "</span>"
            "<span class='event-label'>" + str(day["count"]) + " menções</span>"
            "<span class='event-countdown'>" + str(day["alta"]) + " alta / " + str(day["baixa"]) + " baixa</span>"
            "</div>"
        )
    if len(trend) <= 1:
        trend_note = "Começamos a acompanhar o histórico de " + label + " a partir de hoje - volte nos próximos dias para ver a evolução."
    else:
        trend_note = "Histórico dos últimos dias com notícias sobre " + label + "."

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

    other_links_html = ""
    for other in ASSET_PROFILES:
        if other["slug"] != slug:
            other_links_html += '<a href="' + other["slug"] + '.html" class="nav-links" style="margin-right:14px;">' + html_module.escape(other["label"]) + "</a>"

    meta_description = html_module.escape(summary_sentence[:155])
    updated_at = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")

    page = (
        "<!DOCTYPE html><html lang='pt-BR'><head>"
        "<script async src='https://www.googletagmanager.com/gtag/js?id=G-KKJKKZB9QG'></script>"
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());gtag('config', 'G-KKJKKZB9QG');</script>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>" + html_module.escape(label) + " hoje - notícias e sentimento | Antes do Sino</title>"
        "<meta name='description' content='" + meta_description + "'>"
        "<link rel='stylesheet' href='../assets.css'>"
        "</head><body>"
        "<nav><div class='brand'>🔔 Antes do Sino</div>"
        "<a href='../index.html' class='nav-cta' style='background:transparent;border:1px solid var(--line);color:var(--cream);'>Voltar</a></nav>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Ativo</span>"
        "<h1 style='font-family:Fraunces,serif;font-size:2rem;font-weight:600;'>" + html_module.escape(label) + "</h1>"
        "<p style='color:var(--slate);margin-top:14px;font-size:1.05rem;'>" + html_module.escape(summary_sentence) + "</p>"
        "</div></section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>O que está movimentando agora</span>"
        "<h2>Principais notícias sobre " + html_module.escape(label) + "</h2>"
        "</div>"
        "<div class='signals-grid'>" + clusters_html + "</div>"
        "</section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Impacto, não cronologia</span>"
        "<h2>Últimas movimentações relevantes</h2>"
        "</div>"
        "<div class='feed-grid'>" + ranked_html + "</div>"
        "</section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Histórico</span>"
        "<h2>Evolução recente</h2>"
        "<p style='color:var(--slate);margin-top:10px;'>" + trend_note + "</p>"
        "</div>"
        "<div class='events-list'>" + trend_rows + "</div>"
        "</section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Aprofunde-se</span>"
        "<h2>Todas as notícias sobre " + html_module.escape(label) + "</h2>"
        "</div>"
        "<div class='feed-grid'>" + all_feed_html + "</div>"
        "</section>"

        "<section><div class='section-head'>"
        "<span class='kicker'>Outros ativos</span>"
        "</div>"
        "<div>" + other_links_html + "</div>"
        "</section>"

        "<footer><span>&copy; Antes do Sino — dados públicos, não é recomendação de investimento.</span>"
        "<span class='mono'>Atualizado em " + updated_at + "</span></footer>"
        "</body></html>"
    )

    return page


def generate_asset_pages(all_history, entries_today):
    """Gera uma pagina por ativo, mas SO quando ha volume real de
    noticias - nunca cria pagina vazia (evita indexar conteudo fraco)."""
    os.makedirs("docs/ativos", exist_ok=True)
    generated = []

    for profile in ASSET_PROFILES:
        page_html = build_asset_page_html(profile, all_history, entries_today)
        if page_html is None:
            print("Sem volume para " + profile["slug"] + " - pagina nao gerada.")
            continue
        with open("docs/ativos/" + profile["slug"] + ".html", "w", encoding="utf-8") as f:
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
        with open("docs/ativos/index.html", "w", encoding="utf-8") as f:
            f.write(index_page)


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
        signals_html = build_signals_html(clusters)
        before = template.split(start_marker_s)[0]
        after = template.split(end_marker_s)[1]
        template = before + start_marker_s + "\n" + signals_html + end_marker_s + after

    if start_marker_e in template and end_marker_e in template:
        events_html = build_events_html(entries_for_today)
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

    all_portal_entries = portal_entries + load_portal_history()
    save_portal_history(all_portal_entries)

    today_str = datetime.now(BR_TZ).strftime("%Y-%m-%d")
    entries_today = [e for e in all_portal_entries if e.get("date") == today_str]

    archive = load_daily_archive()

    generate_portal(all_portal_entries, entries_today)
    build_daily_summary_html(entries_today, today_str)
    generate_asset_pages(all_portal_entries, entries_today)

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
