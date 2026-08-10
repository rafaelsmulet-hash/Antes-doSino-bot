"""
Carteira de Dividendos - Antes do Sino (ferramenta PESSOAL do dono do
projeto, nao um produto pros assinantes do bot)
============================================================================
Modulo isolado (mesmo espirito de diario_decisao.py e
social/content_engine.py - nunca importa main.py, recebe
fetch_raw_quote_fn pronto por parametro) que, todo dia 10 do mes,
calcula como dividir um aporte fixo entre um universo pre-definido de
acoes pagadoras de dividendo e manda o resultado por Telegram pro
TELEGRAM_ADMIN_CHAT_ID (uso pessoal, ja existente no projeto pra
avisos privados - ver social/content_engine.py e
social/design_engine.py).

Regra de alocacao (mecanica, documentada, NAO e "a IA decide"):
  - Cada mes, le o yield de dividendo atual de cada ativo (campo
    opcional da brapi.dev, so disponivel em plano pago deles - ver
    _extrair_metrica). Se nao tiver, usa o proprio preco como metrica
    alternativa - mesma logica de "comparar com a propria media
    historica", so que baseada em preco em vez de yield.
  - O modulo NAO tem historico de anos pra comparar - ele CONSTROI o
    proprio historico a partir do dia em que comeca a rodar. Enquanto
    um ativo tem menos de MIN_LEITURAS_PARA_MEDIA leituras
    acumuladas, entra no aporte com peso igual aos demais (sem
    comparacao nenhuma ainda).
  - Depois de ter historico suficiente: peso proporcional a quanto a
    metrica atual esta ACIMA da propria media ja acumulada (ativo
    "relativamente mais barato" que o seu normal recebe mais aporte).
  - Sinal de saida e SEMPRE so um alerta no texto, nunca uma acao
    automatica: quando a metrica atual de um ativo cai muito abaixo
    (< LIMITE_ALERTA_SAIDA) da propria media, o texto avisa "vale
    revisar" - a decisao continua sendo do usuario.

Escopo explicitamente FORA deste modulo: recomendar ativos que nao
estao no UNIVERSO fixo, decidir "vender" automaticamente, e qualquer
opiniao/julgamento sobre o motivo da variacao de preco - so o
calculo da regra.
"""

import os
import json
from datetime import datetime, timezone, timedelta

import requests

try:
    from cryptography.fernet import Fernet
except ImportError:  # cryptography ausente nunca pode derrubar o pipeline principal
    Fernet = None

BR_TZ = timezone(timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

# Reaproveita a mesma chave do Diario de Decisao Comportamental - nao
# ha necessidade de uma chave separada, os dois arquivos sao estado
# privado do mesmo projeto.
DECISOES_ENCRYPTION_KEY = os.environ.get("DECISOES_ENCRYPTION_KEY", "")

CARTEIRA_HISTORICO_FILE = "carteira_historico_yield.json"
CARTEIRA_STATUS_FILE = "carteira_status.json"

UNIVERSO = ["TAEE11", "TRPL4", "CMIG4", "BBAS3", "ITSA4", "SAPR11", "EGIE3", "BBSE3"]
APORTE_MENSAL = 500.0
DIA_DO_APORTE = 10
MIN_LEITURAS_PARA_MEDIA = 6
LIMITE_ALERTA_SAIDA = 0.5
PESO_MAX = 2.5
PESO_MIN = 0.3


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

def _load_json_seguro(caminho, default):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def carregar_historico():
    return _load_json_seguro(CARTEIRA_HISTORICO_FILE, {"leituras": []})


def salvar_historico(estado):
    with open(CARTEIRA_HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def _fernet():
    if not Fernet or not DECISOES_ENCRYPTION_KEY:
        return None
    try:
        return Fernet(DECISOES_ENCRYPTION_KEY.encode("utf-8"))
    except Exception:
        return None


def publicar_status_criptografado(payload):
    """Publica carteira_status.json criptografado (mesmo padrao de
    decisoes_usuarios.json) - e o que a pagina docs/carteira.html le
    atraves do Worker, depois de autenticar com senha."""
    fernet = _fernet()
    if not fernet:
        print(
            "AVISO: DECISOES_ENCRYPTION_KEY nao configurada - "
            + CARTEIRA_STATUS_FILE + " NAO foi salvo."
        )
        return
    dados = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with open(CARTEIRA_STATUS_FILE, "wb") as f:
        f.write(fernet.encrypt(dados))


# ---------------------------------------------------------------------------
# Calculo da alocacao
# ---------------------------------------------------------------------------

def _extrair_metrica(resultado_bruto):
    """(tipo, valor, preco). Tenta yield de dividendo primeiro (campo
    opcional, so em plano pago da brapi - nome exato do campo nao
    confirmado, tentamos as variacoes mais prováveis); se nao vier,
    cai pro proprio preco como metrica."""
    preco = resultado_bruto.get("regularMarketPrice")
    yield_bruto = (
        resultado_bruto.get("dividendYield")
        or resultado_bruto.get("dividendsYield")
        or resultado_bruto.get("dividendYieldTTM")
    )
    if yield_bruto:
        try:
            return "yield", float(yield_bruto), preco
        except (TypeError, ValueError):
            pass
    return "preco", preco, preco


def _media_historica(leituras, ticker, tipo_metrica):
    valores = [l["valor"] for l in leituras if l["ticker"] == ticker and l["tipo"] == tipo_metrica]
    if not valores:
        return None, 0
    return sum(valores) / len(valores), len(valores)


def calcular_alocacao(leituras_atuais, historico):
    """"Atrativo" (score) sempre significa a mesma coisa nas duas
    metricas: quanto MAIOR, mais o ativo esta favoravel a receber
    aporte agora, relativo a propria historia.
      - yield: score = yield_atual / yield_medio (yield mais alto que
        o normal = preco relativamente baixo pro dividendo pago =
        "esta barato", compra mais).
      - preco (fallback, sem dado de dividendo): score =
        preco_medio / preco_atual - INVERTIDO em relacao ao yield de
        proposito, porque pra preco e o INVERSO que significa "barato"
        (preco atual abaixo da propria media = compra mais; preco
        atual acima da propria media = relativamente caro agora)."""
    pesos_brutos = {}
    alertas = {}

    for leitura in leituras_atuais:
        ticker = leitura["ticker"]
        tipo = leitura["tipo"]
        valor = leitura["valor"]
        media, n = _media_historica(historico["leituras"], ticker, tipo)

        if media is None or n < MIN_LEITURAS_PARA_MEDIA or media <= 0 or valor <= 0:
            pesos_brutos[ticker] = 1.0
            continue

        score = (valor / media) if tipo == "yield" else (media / valor)
        pesos_brutos[ticker] = max(PESO_MIN, min(score, PESO_MAX))
        if score < LIMITE_ALERTA_SAIDA:
            alertas[ticker] = score

    soma_pesos = sum(pesos_brutos.values()) or 1.0
    alocacao = []
    for leitura in leituras_atuais:
        ticker = leitura["ticker"]
        peso_normalizado = pesos_brutos.get(ticker, 1.0) / soma_pesos
        alocacao.append({
            "ticker": ticker,
            "preco": leitura["preco"],
            "valor_rs": round(APORTE_MENSAL * peso_normalizado, 2),
            "tipo_metrica": leitura["tipo"],
            "alerta_saida": ticker in alertas,
        })
    return alocacao


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _formata_preco(valor):
    return "R$ " + f"{valor:.2f}".replace(".", ",")


def _montar_mensagem(alocacao, tem_historico_suficiente):
    linhas = [
        "📊 <b>Aporte do dia " + str(DIA_DO_APORTE) + "</b> — "
        + _formata_preco(APORTE_MENSAL)
    ]
    if not tem_historico_suficiente:
        linhas.append("(ainda sem histórico suficiente — peso igual entre os ativos por enquanto)")
    linhas.append("")

    for item in sorted(alocacao, key=lambda x: -x["valor_rs"]):
        linha = item["ticker"] + ": " + _formata_preco(item["valor_rs"]) + " (papel a " + _formata_preco(item["preco"]) + ")"
        if item["alerta_saida"]:
            linha += " ⚠️ métrica bem abaixo da própria média — vale revisar"
        linhas.append(linha)

    linhas.append("")
    linhas.append("Sem julgamento nem opinião — só o cálculo da regra que você definiu. A decisão final é sua.")
    return "\n".join(linhas)


def _enviar_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Carteira de Dividendos: TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_CHAT_ID não configurado - aviso não enviado.")
        return False
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print("Erro ao enviar mensagem da Carteira de Dividendos (isolado): " + str(e))
        return False


# ---------------------------------------------------------------------------

def processar_aporte_mensal(fetch_raw_quote_fn):
    """Roda todo ciclo (a cada ~5min via main()) - so executa de
    verdade no dia DIA_DO_APORTE, e no maximo uma vez por mes (marca
    no proprio historico pra nao repetir se o bot rodar de novo no
    mesmo dia)."""
    agora = datetime.now(BR_TZ)
    if agora.day != DIA_DO_APORTE:
        return

    historico = carregar_historico()
    mes_ref = agora.strftime("%Y-%m")
    ja_rodou_este_mes = any(
        l.get("mes_referencia") == mes_ref and l.get("aporte") for l in historico["leituras"]
    )
    if ja_rodou_este_mes:
        return

    leituras_atuais = []
    for ticker in UNIVERSO:
        resultado = fetch_raw_quote_fn(ticker)
        if not resultado:
            continue
        tipo, valor, preco = _extrair_metrica(resultado)
        if valor is None or preco is None:
            continue
        leituras_atuais.append({"ticker": ticker, "tipo": tipo, "valor": valor, "preco": preco})

    if not leituras_atuais:
        print("Carteira de Dividendos: nenhuma cotação disponível hoje, tenta de novo no próximo ciclo.")
        return

    alocacao = calcular_alocacao(leituras_atuais, historico)
    tem_historico_suficiente = any(
        _media_historica(historico["leituras"], l["ticker"], l["tipo"])[1] >= MIN_LEITURAS_PARA_MEDIA
        for l in leituras_atuais
    )

    texto = _montar_mensagem(alocacao, tem_historico_suficiente)
    _enviar_telegram(texto)

    for l in leituras_atuais:
        historico["leituras"].append({
            "data": agora.isoformat(),
            "mes_referencia": mes_ref,
            "ticker": l["ticker"],
            "tipo": l["tipo"],
            "valor": l["valor"],
            "preco": l["preco"],
            "aporte": True,
        })
    salvar_historico(historico)

    publicar_status_criptografado({
        "atualizado_em": agora.isoformat(),
        "aporte_mensal": APORTE_MENSAL,
        "alocacao": alocacao,
        "universo": UNIVERSO,
    })
