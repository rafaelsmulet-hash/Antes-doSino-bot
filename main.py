import os
import re
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ==========================================
# CONFIGURAÇÕES E SINALIZADORES
# ==========================================
USE_AI_SUMMARY = True  # Mude para False se quiser desativar o Gemini temporariamente

# Dicionário com as suas mais de 20 fontes RSS (Exemplos principais)
# Adicione ou ajuste as URLs conforme a sua lista original
RSS_FEEDS = {
    "infomoney": "https://www.infomoney.com.br/feed/",
    "moneytimes": "https://www.moneytimes.com.br/feed/",
    "valorinveste": "https://valorinveste.globo.com/rss/valor-investe/",
    "bloomberg": "https://www.bloomberg.com/feeds/bground.xml",
    "cnbc": "https://search.cnbc.com/rs/search/combinedfeed.xml",
    "marketwatch": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "wsj": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex"
}

# Lista de fontes que já estão em português (não precisam de tradução)
PORTUGUESE_SOURCES = ["infomoney", "moneytimes", "valorinveste", "exame", "cnbcbrasil", "cnnbrasil"]

# Palavras-chave para filtrar notícias altamente relevantes (B3, EUA e Macro)
KEYWORDS = [
    "juros", "ações", "dividendos", "fed", "ipca", "payroll", "brent", "petróleo",
    "lucro", "prejuízo", "fuso", "ticker", "banco central", "inflação", "selic"
]

# Configurações de ambiente vindas do GitHub Actions ou Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA E FILTRO
# ==========================================
def strip_html_tags(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text()

def is_relevant(title, body):
    """
    Verifica se a notícia contém alguma das mais de 100 palavras-chave definidas.
    """
    text_to_check = f"{title} {body}".lower()
    return any(keyword in text_to_check for keyword in KEYWORDS)

# ==========================================
# REGRAS DO MOTOR DE PROCESSAMENTO
# ==========================================
def summarize_with_gemini(title, body, translate=True):
    """
    Traduz o conteúdo de forma gratuita (se necessário) e aciona o 
    Gemini em português para resumir a notícia de forma cirúrgica.
    """
    try:
        body_cleaned = strip_html_tags(body).strip()
        
        # --- ETAPA 1: TRADUÇÃO GRATUITA E ILIMITADA ---
        if translate:
            try:
                print(f"Traduzindo gratuitamente: {title[:30]}...")
                title = GoogleTranslator(source='en', target='pt').translate(title)
                if body_cleaned:
                    body_cleaned = GoogleTranslator(source='en', target='pt').translate(body_cleaned)
            except Exception as e:
                print(f"AVISO: Falha na tradução gratuita ({e}). Mantendo texto original.")

        # Plano de Contingência: Se o Gemini estiver desativado, retorna o texto traduzido puro
        if not USE_AI_SUMMARY or not GEMINI_API_KEY:
            return {"title": title, "body": body_cleaned}

        # --- ETAPA 2: CONFIGURAÇÃO DOS PROMPTS EM PORTUGUÊS ---
        if not body_cleaned:
            prompt = (
                "Você recebeu o título de uma notícia de mercado financeiro em português.\n"
                "Sua tarefa: Crie um parágrafo curto (máximo 2 frases) em português explicando "
                "o contexto macroeconômico ou o impacto provável desta notícia para os investidores, "
                "baseando-se no seu conhecimento de mercado.\n"
                "Responda APENAS com texto simples, sem asteriscos, sem markdown, sem repetir o título.\n\n"
                f"Título: {title}"
            )
        else:
            prompt = (
                "Resuma esta notícia de mercado financeiro em português do Brasil. "
                "Responda APENAS com um resumo de no máximo 2 frases em texto simples, sem markdown, sem asteriscos.\n\n"
                f"Texto original: {body_cleaned}"
            )

        # --- ETAPA 3: REQUISIÇÃO PARA A API DO GEMINI ---
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        data = response.json()
        
        # Contingência caso a IA retorne erro ou bata no limite da API
        if "candidates" not in data:
            print(f"Aviso Gemini (resposta sem candidatos válidos). Enviando tradução limpa.")
            return {"title": title, "body": body_cleaned}
            
        summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        summary = summary.replace("**", "").replace("*", "")
        
        return {"title": title, "body": summary}

    except Exception as e:
        print(f"Erro crítico no processamento de tradução/resumo: {e}")
        return None

# ==========================================
# ENVIO PARA O TELEGRAM
# ==========================================
def send_to_telegram(title, body, source_name):
    """
    Formata e dispara a notícia final para o canal do Telegram do Antes do Sino.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Erro: Tokens do Telegram não configurados.")
        return

    # Formatação limpa em HTML
    message_text = (
        f"🔔 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"📌 <i>Fonte: {source_name.upper()}</i>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            print(f"Notícia enviada com sucesso: {title[:30]}...")
        else:
            print(f"Erro ao enviar para o Telegram: {res.text}")
    except Exception as e:
        print(f"Falha na conexão com a API do Telegram: {e}")

# ==========================================
# LAÇO PRINCIPAL DE EXECUÇÃO (MAIN)
# ==========================================
def main():
    print("Iniciando varredura dos feeds RSS do Antes do Sino...")
    
    for source_name, url in RSS_FEEDS.items():
        try:
            print(f"Acessando fonte: {source_name}...")
            response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                print(f"Erro ao acessar {source_name}: Status {response.status_code}")
                continue
                
            # Parse do XML do RSS
            root = ET.fromstring(response.content)
            
            # Varre os itens (notícias) do feed
            for item in root.findall(".//item")[:5]:  # Pega as 5 últimas de cada feed para evitar duplicados antigos
                title = item.find("title").text if item.find("title") is not None else ""
                body = item.find("description").text if item.find("description") is not None else ""
                
                if not title:
                    continue
                    
                # 1. Filtra por relevância (palavras-chave)
                if is_relevant(title, body):
                    # Define se precisa de tradução (se a fonte não for brasileira)
                    need_translation = source_name not in PORTUGUESE_SOURCES
                    
                    # 2. Processa tradução gratuita + resumo da IA
                    processed_news = summarize_with_gemini(title, body, translate=need_translation)
                    
                    if processed_news:
                        # 3. Dispara para o Telegram
                        send_to_telegram(
                            title=processed_news["title"],
                            body=processed_news["body"],
                            source_name=source_name
                        )
                        
        except Exception as e:
            print(f"Erro ao processar a fonte {source_name}: {e}")
            continue

if __name__ == "__main__":
    main()
