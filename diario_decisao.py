"""
Diario de Decisao Comportamental - Antes do Sino (Fase 1 / MVP)
==================================================================

Modulo TOTALMENTE ISOLADO do main.py, no mesmo espirito de
social/content_engine.py: nao importa nada de main.py, recebe tudo
pronto por parametro (lista de termos de ativo, mapa de hashtag, e
uma funcao de busca de cotacao) - evita import circular e deixa claro
que uma falha aqui nunca pode afetar o pipeline de noticias.

Escopo desta fase (nao expandir sem necessidade - ver combinado):
    - Usuario manda "Comprei PETR4" (ou similar) no chat PRIVADO do
      bot (nunca no grupo).
    - identificar_acao() + identificar_ativo() reconhecem acao/ativo
      por palavra-chave simples, reaproveitando
      editorial_foundation.derive_cluster_key + TICKER_HASHTAG_MAP de
      main.py (recebidos por parametro).
    - Busca a cotacao atual via fetch_quote_fn (main.fetch_brapi_quote,
      tambem por parametro).
    - Salva o registro em decisoes_usuarios.json (raiz do repo, NUNCA
      em docs/ - e dado privado por usuario, docs/ e a raiz publica do
      GitHub Pages) e confirma pro usuario na mesma conversa.
    - FOLLOWUP_DIAS depois, busca o preco de novo e manda so o dado
      (sem julgamento nem opiniao) pro mesmo usuario.

Fora de escopo nesta fase (fica pra depois, ver combinado): deteccao
de padrao comportamental (efeito disposicao, revenge trading), trava
de quem pode usar, e qualquer mudanca no pipeline de noticias.

Polling do Telegram: usa getUpdates com um offset PROPRIO
(DIARIO_OFFSET_FILE), separado do offset do Social Content Engine
(social/content_engine.py). Avaliado explicitamente: os 2 poderiam
compartilhar 1 unica chamada, mas isso acoplaria uma feature nova e
experimental ao fluxo de aprovacao de conteudo social, que e um
assunto completamente diferente. Um poll independente e seguro aqui
porque a API do Telegram so "confirma" (descarta) updates no momento
em que uma chamada e feita com offset mais alto - como os dois polls
rodam dentro do mesmo ciclo (main() completo, a cada ~5min) e cada um
mantem seu proprio offset, nenhum update fica invisivel pro outro; o
custo e so 1 chamada HTTP extra por ciclo.
"""

import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests

BR_TZ = timezone(timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

DECISOES_FILE = "decisoes_usuarios.json"
DIARIO_OFFSET_FILE = "diario_telegram_offset.json"

FOLLOWUP_DIAS = 7

VERBO_PASSADO = {"compra": "comprou", "venda": "vendeu"}


# ---------------------------------------------------------------------------
# Estado - mesmo padrao load/save com tratamento de erro usado no
# resto do projeto (nunca quebra se o arquivo nao existir ou estiver
# corrompido, so volta pro default).
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


def load_decisoes():
    return _load_json_seguro(DECISOES_FILE, {"decisoes": []})


def save_decisoes(state):
    _save_json(DECISOES_FILE, state)


def load_offset():
    return _load_json_seguro(DIARIO_OFFSET_FILE, {"offset": 0})


def save_offset(state):
    _save_json(DIARIO_OFFSET_FILE, state)


# ---------------------------------------------------------------------------
# Identificacao de acao/ativo/motivo a partir do texto livre
# ---------------------------------------------------------------------------

PALAVRAS_COMPRA = ["comprei", "comprar"]
PALAVRAS_VENDA = ["vendi", "vender"]


def identificar_acao(texto):
    """Deteccao simples por palavra-chave (MVP desta fase - nao usa
    IA de proposito, pra manter previsivel e barato). Retorna
    ('compra'|'venda', palavra_encontrada) ou (None, None) se nenhuma
    das duas bater. So reconhece a primeira ocorrencia - mensagem que
    mencionar compra E venda ao mesmo tempo e um caso raro, fora do
    escopo desta fase."""
    texto_lower = texto.lower()
    for palavra in PALAVRAS_COMPRA:
        if palavra in texto_lower:
            return "compra", palavra
    for palavra in PALAVRAS_VENDA:
        if palavra in texto_lower:
            return "venda", palavra
    return None, None


def identificar_ativo(texto, ticker_list, hashtag_map, derive_cluster_key_fn):
    """Reaproveita editorial_foundation.derive_cluster_key (recebida
    pronta por parametro - derive_cluster_key_fn) pra achar o termo de
    ativo mencionado, e TICKER_HASHTAG_MAP de main.py (tambem por
    parametro) pra converter pro ticker canonico (ex: 'petrobras' ->
    'PETR4') - o mesmo formato que fetch_brapi_quote espera. Retorna
    (ticker, termo_encontrado) ou (None, None)."""
    termo = derive_cluster_key_fn(texto, ticker_list)
    if not termo:
        return None, None
    ticker = hashtag_map.get(termo)
    if not ticker:
        return None, None
    return ticker, termo


def extrair_motivo(texto, termo_acao, termo_ativo):
    """O motivo e o resto do texto, tirando so a palavra de acao e o
    termo de ativo que foram efetivamente reconhecidos - mantem o
    resto exatamente como o usuario escreveu, texto livre, sem
    reformatar nem resumir. Se sobrar so espaco/pontuacao solta, usa o
    texto original inteiro em vez de mandar um motivo vazio de volta."""
    resto = texto
    if termo_acao:
        resto = re.sub(re.escape(termo_acao), "", resto, count=1, flags=re.IGNORECASE)
    if termo_ativo:
        resto = re.sub(re.escape(termo_ativo), "", resto, count=1, flags=re.IGNORECASE)
    resto = re.sub(r"^[\s,.:;\-]+|[\s,.:;\-]+$", "", resto)
    resto = re.sub(r"\s+", " ", resto).strip()
    return resto if resto else texto.strip()


def _formata_preco(valor):
    return "R$ " + f"{valor:.2f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Processamento de 1 mensagem de registro
# ---------------------------------------------------------------------------

def processar_mensagem(texto, chat_id, ticker_list, hashtag_map, derive_cluster_key_fn, fetch_quote_fn):
    """Processa 1 mensagem de chat privado, do reconhecimento ate o
    registro. Retorna (sucesso, texto_resposta) - texto_resposta NUNCA
    e None, mesmo quando sucesso=False: o usuario sempre recebe algum
    retorno (pedido de esclarecimento ou aviso de falha), nunca fica
    no silencio."""
    acao, termo_acao = identificar_acao(texto)
    if not acao:
        return False, (
            "Não entendi se foi uma compra ou venda. Manda algo como "
            "\"Comprei PETR4\" ou \"Vendi VALE3 porque saiu resultado ruim\"."
        )

    ticker, termo_ativo = identificar_ativo(texto, ticker_list, hashtag_map, derive_cluster_key_fn)
    if not ticker:
        return False, (
            "Entendi que foi uma " + acao + ", mas não consegui identificar o "
            "ativo. Tenta citar o ticker ou o nome da empresa (ex: PETR4, Vale)."
        )

    cotacao = fetch_quote_fn(ticker)
    if not cotacao or not cotacao.get("price"):
        return False, (
            "Identifiquei " + acao + " de " + ticker + ", mas não consegui buscar "
            "a cotação agora. Tenta de novo em alguns minutos."
        )

    preco = cotacao["price"]
    motivo = extrair_motivo(texto, termo_acao, termo_ativo)

    state = load_decisoes()
    state.setdefault("decisoes", []).append({
        "chat_id": str(chat_id),
        "ativo": ticker,
        "acao": acao,
        "motivo": motivo,
        "preco_registro": preco,
        "timestamp": datetime.now(BR_TZ).isoformat(),
        "followup_enviado": False,
    })
    save_decisoes(state)

    resposta = (
        "Registrado: " + acao.capitalize() + " de " + ticker + " a " + _formata_preco(preco) + ".\n"
        "Motivo: " + motivo + "\n"
        "Vou te avisar como isso evoluiu."
    )
    return True, resposta


# ---------------------------------------------------------------------------
# Polling do Telegram (chat privado) - ver docstring do modulo pra
# explicacao da decisao de usar offset proprio, separado do Social
# Content Engine.
# ---------------------------------------------------------------------------

def _enviar_telegram(chat_id, texto):
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print("Erro ao enviar mensagem do Diario de Decisao (isolado): " + str(e))
        return False


def checar_mensagens_privadas(ticker_list, hashtag_map, derive_cluster_key_fn, fetch_quote_fn):
    """Roda todo ciclo. Le mensagens novas do Telegram vindas de
    qualquer chat PRIVADO (1 a 1 com o bot - nunca do grupo/canal),
    tenta processar cada uma como um registro de decisao, e sempre
    responde alguma coisa pro usuario (registro confirmado ou pedido
    de esclarecimento). Uma falha ao processar 1 mensagem especifica
    nunca impede as demais de serem processadas."""
    if not TELEGRAM_BOT_TOKEN:
        return

    offset_state = load_offset()
    offset = offset_state.get("offset", 0)

    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/getUpdates"
        params = {"offset": offset, "timeout": 0}
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        updates = data.get("result", []) if data.get("ok") else []
    except Exception as e:
        print("Erro ao consultar getUpdates do Diario de Decisao (isolado): " + str(e))
        updates = []

    maior_update_id = offset - 1

    for update in updates:
        update_id = update.get("update_id", 0)
        if update_id > maior_update_id:
            maior_update_id = update_id

        message = update.get("message", {})
        chat = message.get("chat", {})
        texto = (message.get("text") or "").strip()

        if chat.get("type") != "private" or not texto:
            continue

        chat_id = chat.get("id")
        try:
            _sucesso, resposta = processar_mensagem(
                texto, chat_id, ticker_list, hashtag_map, derive_cluster_key_fn, fetch_quote_fn
            )
            _enviar_telegram(chat_id, resposta)
        except Exception as e:
            print("Erro ao processar mensagem do Diario de Decisao (isolado, ignora so esta mensagem): " + str(e))

    if maior_update_id >= offset:
        save_offset({"offset": maior_update_id + 1})


# ---------------------------------------------------------------------------
# Follow-up (FOLLOWUP_DIAS depois do registro)
# ---------------------------------------------------------------------------

def processar_followups(fetch_quote_fn):
    """Roda todo ciclo. Para cada decisao registrada ha >= FOLLOWUP_DIAS
    e que ainda nao recebeu follow-up, busca o preco atual e manda o
    dado puro pro usuario - SEM julgamento nem opiniao (ver escopo
    combinado). Se a busca de cotacao falhar, nao marca como enviado -
    tenta de novo no proximo ciclo, ate conseguir."""
    if not TELEGRAM_BOT_TOKEN:
        return

    state = load_decisoes()
    decisoes = state.get("decisoes", [])
    agora = datetime.now(BR_TZ)
    alterado = False

    for registro in decisoes:
        if registro.get("followup_enviado"):
            continue
        try:
            registrado_em = datetime.fromisoformat(registro["timestamp"])
        except Exception:
            continue

        if (agora - registrado_em) < timedelta(days=FOLLOWUP_DIAS):
            continue

        cotacao = fetch_quote_fn(registro["ativo"])
        if not cotacao or not cotacao.get("price"):
            continue

        preco_hoje = cotacao["price"]
        preco_registro = registro["preco_registro"]
        variacao = ((preco_hoje - preco_registro) / preco_registro * 100) if preco_registro else 0
        variacao_fmt = ("+" if variacao >= 0 else "") + f"{variacao:.1f}".replace(".", ",") + "%"
        verbo = VERBO_PASSADO.get(registro["acao"], registro["acao"])

        texto = (
            "Há " + str(FOLLOWUP_DIAS) + " dias você " + verbo + " " + registro["ativo"]
            + " a " + _formata_preco(preco_registro) + ". Hoje está em "
            + _formata_preco(preco_hoje) + " (variação de " + variacao_fmt + ")."
        )
        _enviar_telegram(registro["chat_id"], texto)
        registro["followup_enviado"] = True
        alterado = True

    if alterado:
        save_decisoes(state)
