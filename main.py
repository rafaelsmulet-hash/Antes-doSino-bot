"""
Bot de Notícias de Mercado - Antes do Sino (versão GitHub Actions)
Roda UMA VEZ por execução (não é loop infinito) — o GitHub Actions
chama esse script a cada 5 minutos automaticamente via cron.
"""

import feedparser
import requests
import json
import os
import time
import hashlib
import re
import difflib
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

USE_AI_SUMMARY = bool(GEMINI_API_KEY)
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
    "UOL Economia": "https://rss.uol.com.br/feed/economia.xml",
    "G1 Economia": "https://g1.globo.com/dynamo/economia/rss2.xml",
    "Exame": "https://exame.com/feed/",
    "Seu Dinheiro": "https://www.seudinheiro.com/feed/",
    "Suno Notícias": "https://www.suno.com.br/noticias/feed/",
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
    "selic", "juros", "ibovespa", "dólar", "dolar", "inflação", "inflacao",
    "ações", "acoes", "ação", "acao", "bolsa", "b3", "cdi", "tesouro direto",
    "câmbio", "cambio", "pib", "copom", "banco central", "bc",
    "interest rate", "fed", "federal reserve", "stocks", "stock market",
    "nasdaq", "dow jones", "s&p 500", "s&p", "inflation", "gdp", "bonds",
    "treasury", "earnings", "ipo", "recession", "rate cut", "rate hike",
    "wall street", "market", "economy", "economic", "trading", "investors",
    "yield", "moody's", "fitch",
    "petr4", "petr3", "vale3", "itub4", "bbdc4", "bbdc3", "abev3", "bbas3",
    "wege3", "rent3", "suzb3", "jbss3", "b3sa3", "mglu3", "lren3", "ggbr4",
    "elet3", "elet6", "csna3", "usim5", "prio3", "rail3", "azul4", "cvcb3",
    "hapv3", "radl3", "vivt3", "sanb11", "brfs3", "embr3",
    "petrobras", "vale", "itaú", "itau", "bradesco", "ambev", "banco do brasil",
    "weg", "localiza", "suzano", "jbs", "magazine luiza", "magalu",
    "lojas renner", "renner", "gerdau", "eletrobras", "csn", "usiminas",
    "azul", "gol", "cvc", "hapvida", "raia drogasil", "totvs", "vivo",
    "santander brasil", "brf", "embraer", "natura", "cosan",
    "apple", "microsoft", "google", "alphabet", "amazon", "tesla", "meta",
    "nvidia", "netflix", "jpmorgan", "jp morgan", "goldman sachs",
    "berkshire hathaway", "visa", "mastercard", "disney", "coca-cola",
    "boeing", "intel", "exxon", "chevron", "walmart", "pfizer",
]

WORDPRESS_BOILERPLATE_PATTERNS = [
    r"The post .* appeared first on \w+\s*\.?",
    r"O post .* apareceu primeiro (n[oa]) \w+\s*\.?",
]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("hashes", [])), data.get("titles", [])
    return set(), []


def save_state(hashes, titles):
    trimmed_hashes = list(hashes)[-3000:]
    trimmed_titles = titles[-500:]
    with open(STATE_FILE, "w") as f:
        json.dump({"hashes": trimmed_hashes, "titles": trimmed_titles}, f)


def normalize_url(url):
    return url.split("?")[0].split("#")[0]


def item_hash(entry):
    key = normalize_url(entry.get("link", "")) or entry.get("title", "")
    return hashlib.md5(key.encode()).hexdigest()


def is_relevant(entry):
    if not KEYWORDS:
        return True
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


def is_duplicate_title(title, recent_titles):
    for old_title in recent_titles:
        ratio = difflib.SequenceMatcher(None, title.lower(), old_title.lower()).ratio()
        if ratio > 0.8:
            return True
    return False


def strip_boilerplate(text):
    for pattern in WORDPRESS_BOILERPLATE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


def fetch_feed(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"AVISO: falha ao buscar feed {url}: {e}")
        return feedparser.parse("")


def summarize_with_gemini(title, body):
    if not USE_AI_SUMMARY:
        return None
    try:
        prompt = (
            "Traduza e resuma esta noticia de mercado financeiro para portugues do Brasil. "
            "Responda APENAS com texto simples, sem markdown, sem asteriscos, sem prefixos "
            "como 'Resumo:' ou 'Traducao:'. Formato: primeiro o titulo traduzido em uma linha, "
            "depois uma linha em branco, depois um resumo de no maximo 2 frases. "
            "Se nao houver texto alem do titulo, gere uma frase breve especulando o contexto "
            "provavel da noticia com base apenas no titulo, deixando claro que e uma inferencia.\n\n"
            f"Titulo original: {title}\nTexto original: {body}"
        )
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        data = response.json()
        if "candidates" not in data:
            print(f"Erro Gemini (resposta sem 'candidates'): {data}")
            return None
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        parts = text.split("\n\n", 1)
        translated_title = parts[0].strip()
        summary = parts[1].strip() if len(parts) > 1 else ""
        return {"title": translated_title, "body": summary}
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return None


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            print(f"Rate limit, aguardando {retry_after}s")
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Erro Telegram (status {r.status_code}): {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"Erro Telegram: {e}")
        return False


def format_message(source, entry, ai_result):
    title = entry.get("title", "Sem titulo")
    link = entry.get("link", "")
    body = entry.get("summary", "")

    if ai_result:
        title = ai_result.get("title", title) or title
        body = ai_result.get("body", "") or body

    body = strip_boilerplate(body)
    if not body:
        body = "Leia mais no link."

    msg = f"<b>{title}</b>\n\n{body}\n\n<i>{source}</i>\n🔗 {link}"
    return msg


def is_recent_enough(entry):
    date_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not date_struct:
        return True
    entry_date = datetime(*date_struct[:6], tzinfo=timezone.utc).astimezone(BR_TZ)
    now = datetime.now(BR_TZ)
    return entry_date.date() == now.date()


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return

    sent_hashes, recent_titles = load_state()
    new_count = 0

    for source, url in FEEDS.items():
        feed = fetch_feed(url)
        if not feed.entries:
            print(f"AVISO: Feed '{source}' retornou vazio ou falhou")
            continue

        for entry in feed.entries[:10]:
            h = item_hash(entry)
            if h in sent_hashes:
                continue

            title = entry.get("title", "")
            if is_duplicate_title(title, recent_titles):
                sent_hashes.add(h)
                continue

            if not is_relevant(entry):
                sent_hashes.add(h)
                continue

            if not is_recent_enough(entry):
                sent_hashes.add(h)
                continue

            ai_result = summarize_with_gemini(title, entry.get("summary", ""))
            message = format_message(source, entry, ai_result)

            if send_telegram_message(message):
                sent_hashes.add(h)
                recent_titles.append(title)
                new_count += 1
                print(f"Enviado: {title[:60]}")
                time.sleep(3)

    save_state(sent_hashes, recent_titles)
    print(f"Ciclo concluído. {new_count} notícia(s) enviada(s).")


if __name__ == "__main__":
    main()

