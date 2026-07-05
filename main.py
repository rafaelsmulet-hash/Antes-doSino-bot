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

# Configurações de Ambiente (Devem ser configuradas nos Secrets do GitHub)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

USE_AI_SUMMARY = bool(GEMINI_API_KEY)
STATE_FILE = "sent_items.json"

# Limite máximo de notícias enviadas POR EXECUÇÃO para não estourar limites
MAX_NEWS_PER_CYCLE = 5

BR_TZ = timezone(timedelta(hours=-3))

FEEDS = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Money Times": "https://www.moneytimes.com.br/mercados/feed",
    "Investing.com Brasil": "https://br.investing.com/rss/news_25.rss",
    "CNBC - Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "CNBC - Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC - US News": "https://www.cnbc.com/id/15837362/device/rss/rss.
