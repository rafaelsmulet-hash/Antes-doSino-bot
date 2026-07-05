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
from deep_translator import GoogleTranslator

# Configurações de Ambiente (Secrets do GitHub ou Render)
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

PORTUGUESE_SOURCES = {
    "InfoMoney", "Money Times", "Investing.com Brasil", "UOL Economia",
    "G1 Economia", "Exame", "Seu Dinheiro", "Suno Noticias",
    "Brazil Journal", "Neofeed",
}

WORDPRESS_BOILERPLATE_PATTERNS = [
    r"The post .* appeared first on \w+\s*\.?",
    r"O post .* apareceu primeiro (n[oa]) \w+\s*\.?",
]

# ==========================================
# CONTROLE DE ESTADO (SISTEMA ANTI-LOOP)
# ==========================================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("hashes", [])), data.get("titles", [])
        except Exception as e:
            print(f"AVISO: Falha ao carregar estado ({e}). Criando um novo.")
    return set(), []

def save_state(hashes, titles):
    trimmed_hashes = list(hashes)[-3000:]
    trimmed_titles = titles[-500:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"hashes": trimmed_hashes, "titles": trimmed_titles}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"ERRO CRÍTICO ao salvar estado: {e}")

def normalize_url(url):
    return url.split("?")[0].split("#")[0]

def item_hash(entry):
    key = normalize_url(entry.get("link", "")) or entry.get("title", "")
    return hashlib.md5(key.encode("utf-8")).hexdigest()

# ==========================================
# FILTROS DE RELEVÂNCIA E LIMPEZA
# ==========================================
def is_relevant(entry):
    if not KEYWORDS:
        return True
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
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
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()

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

# ==========================================
# REQUISITOS DE CONEXÃO E TRADUÇÃO GRÁTIS + IA
# ==========================================
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

def needs_ai(source, body):
    has_body = bool(strip_html_tags(body).strip())
    return not has_body or source not in PORTUGUESE_SOURCES

def summarize_with_gemini(title, body, source_name, translate=True):
    try:
        body_cleaned = strip_html_tags(body).strip() if body else ""
        
        # Ajuste cirúrgico para o Yahoo Finance ou feeds com corpos sabidamente vazios
        if "Yahoo" in source_name or not body_cleaned:
            body_cleaned = ""

        # --- ETAPA DE TRADUÇÃO GRATUITA ---
        if translate:
            try:
                title = GoogleTranslator(source='en', target='pt').translate(title)
                if body_cleaned:
                    body_cleaned = GoogleTranslator(source='en', target='pt').translate(body_cleaned)
            except Exception as e:
                print(f"AVISO: Falha na tradução gratuita ({e}). Usando original.")

        if not USE_AI_SUMMARY:
            return {"title": title, "body": body_cleaned}

        # --- LÓGICA AGRESSIVA PARA CURADORIA DE FONTES SEM CORPO (COMO YAHOO) ---
        if not body_cleaned:
            prompt = (
                "Voce recebeu o titulo traduzido de uma noticia importante de mercado financeiro internacional. "
                "Como o corpo da noticia nao esta disponivel, use o seu conhecimento de mercado para criar "
                "um paragrafo explicativo (maximo 2 frases) em portugues do Brasil, detalhando o contexto "
                "macroeconomico ou o impacto esperado que esse tipo de evento traz para os investidores.\n"
                "Responda APENAS com o texto explicativo puro, sem markdown, sem asteriscos, sem introducoes.\n\n"
                f"Titulo: {title}"
            )
        else:
            prompt = (
                "Resuma esta noticia de mercado financeiro em portugues do Brasil. "
                "Responda APENAS com um resumo de no maximo 2 frases em texto simples, sem markdown, sem asteriscos.\n\n"
                f"Texto original: {body_cleaned}"
            )

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        data = response.json()
        if "candidates" not in data:
            return {"title": title, "body": body_cleaned}
            
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = text.replace("**", "").replace("*", "")
        return {"title": title, "body": text}
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return None

# ==========================================
# SISTEMA DE ENVIO E LOGICA PRINCIPAL
# ==========================================
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def format_message(source, entry, ai_result):
    title = entry.get("title", "Sem título")
    body = entry.get("summary", "")

    if ai_result:
        title = ai_result.get("title", title) or title
        body = ai_result.get("body", "") or body

    body = strip_html_tags(body)
    body = strip_boilerplate(body)
    
    # Limpeza profunda de links promocionais embutidos no feed
    body = re.sub(r"https?://\S+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"www\.\S+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\n+", "\n", body).strip()

    if not body:
        body = "Acompanhe os desdobramentos desta notícia direto nos canais oficiais."

    # Escapamento de tags HTML para segurança da API do Telegram
    title_tag = html_module.escape(str(title).strip(), quote=False)
    body_tag = html_module.escape(str(body).strip(), quote=False)
    source_tag = html_module.escape(str(source).strip().upper(), quote=False)

    # Retorna a estrutura visual padrão unificada do Antes do Sino
    return f"<b>🔔 {title_tag}</b>\n\n{body_tag}\n\n<i>Fonte: {source_tag}</i>"

def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return

    sent_hashes, recent_titles = load_state()
    new_count = 0

    for source, url in FEEDS.items():
        feed = fetch_feed(url)
        if not feed.entries:
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

            raw_body = entry.get("summary", "")
            is_english = source not in PORTUGUESE_SOURCES

            if needs_ai(source, raw_body):
                ai_result = summarize_with_gemini(title, raw_body, source_name=source, translate=is_english)
            else:
                ai_result = None

            message = format_message(source, entry, ai_result)

            if send_telegram_message(message):
                sent_hashes.add(h)
                recent_titles.append(title)
                new_count += 1
                print(f"Enviado com sucesso: {title[:50]}...")
                save_state(sent_hashes, recent_titles)
                time.sleep(3)

    print(f"Ciclo concluído. {new_count} notícias novas enviadas.")

if __name__ == "__main__":
    main()
