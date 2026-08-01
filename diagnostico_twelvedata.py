"""
Diagnostico Twelve Data - Antes do Sino (v2 - busca por nome)
=================================================================

Versao 2: em vez de "chutar" varios formatos de simbolo e gastar 1
credito de cotacao por tentativa errada (o que ja custou a cota do
dia duas vezes na v1), essa versao usa o endpoint de BUSCA POR NOME
(/symbol_search), que e um endpoint de catalogo/referencia - mais
barato que buscar cotacao de verdade. So depois de achar o simbolo
certo pelo nome e que fazemos 1 chamada de cotacao real, pra
confirmar que funciona no plano atual.

Como rodar: troca temporariamente "python main.py" por
"python diagnostico_twelvedata.py" na etapa "Rodar bot" do workflow,
roda, le o relatorio no log, depois reverte e apaga este arquivo.

IMPORTANTE: so rodar depois que a cota diaria da Twelve Data tiver
resetado (o teste anterior consumiu tudo - normalmente reseta por
volta da meia-noite UTC).
"""

import os
import time
import requests

TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
URL_SEARCH = "https://api.twelvedata.com/symbol_search"
URL_QUOTE = "https://api.twelvedata.com/quote"

INTERVALO_ENTRE_CHAMADAS_SEGUNDOS = 8

# (nome_exibicao, termo de busca, palavras esperadas no nome do resultado)
ATIVOS_PARA_BUSCAR = [
    ("USD/BRL", "USD BRL", ["dollar", "real", "brazil"]),
    ("WTI (Petroleo)", "WTI crude oil", ["crude", "oil", "wti"]),
    ("Nikkei 225", "Nikkei 225", ["nikkei"]),
    ("Hang Seng", "Hang Seng", ["hang seng"]),
    ("Shanghai Composite", "Shanghai Composite", ["shanghai", "sse"]),
    ("ASX 200", "ASX 200", ["asx", "australia"]),
    ("DAX", "DAX Germany", ["dax", "germany"]),
    ("FTSE 100", "FTSE 100", ["ftse"]),
    ("CAC 40", "CAC 40", ["cac"]),
    ("S&P 500 Futuro", "S&P 500 futures", ["future"]),
    ("Nasdaq Futuro", "Nasdaq 100 futures", ["future"]),
    ("Ouro", "Gold", ["gold"]),
    ("DXY (Indice do Dolar)", "US Dollar Index", ["dollar index", "dxy"]),
]


def buscar_por_nome(termo):
    """Busca no CATALOGO (endpoint de referencia, mais barato que
    cotacao) por instrumentos que combinem com o termo. Retorna a
    lista de candidatos encontrados (symbol + instrument_name)."""
    try:
        params = {"symbol": termo, "apikey": TWELVEDATA_API_KEY}
        response = requests.get(URL_SEARCH, params=params, timeout=15)
        data = response.json()
        if "data" not in data:
            return [], data.get("message", str(data))
        return data["data"], None
    except Exception as e:
        return [], "excecao: " + str(e)


def confirmar_cotacao(simbolo):
    """So chamado DEPOIS de achar um simbolo candidato pela busca -
    1 chamada de cotacao real pra confirmar que funciona no plano
    atual."""
    try:
        params = {"symbol": simbolo, "apikey": TWELVEDATA_API_KEY}
        response = requests.get(URL_QUOTE, params=params, timeout=15)
        data = response.json()
        if data.get("status") == "error" or "close" not in data:
            return False, data.get("message", str(data))
        return True, data.get("close")
    except Exception as e:
        return False, "excecao: " + str(e)


def diagnosticar(nome_exibicao, termo_busca, palavras_esperadas):
    candidatos, erro_busca = buscar_por_nome(termo_busca)
    time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)

    if erro_busca:
        return {"disponivel": False, "motivo": "busca falhou: " + erro_busca, "simbolo": None}

    if not candidatos:
        return {"disponivel": False, "motivo": "nenhum resultado encontrado na busca por '" + termo_busca + "'", "simbolo": None}

    for candidato in candidatos[:5]:
        nome_instrumento = (candidato.get("instrument_name") or "").lower()
        if not any(p in nome_instrumento for p in palavras_esperadas):
            continue

        simbolo = candidato.get("symbol")
        sucesso, resultado = confirmar_cotacao(simbolo)
        time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)

        if sucesso:
            return {
                "disponivel": True,
                "simbolo": simbolo,
                "nome_oficial": candidato.get("instrument_name"),
                "preco": resultado,
                "motivo": None,
            }
        else:
            return {
                "disponivel": False,
                "simbolo": simbolo,
                "motivo": "encontrado no catalogo, mas cotacao falhou: " + str(resultado),
            }

    return {"disponivel": False, "motivo": "busca achou resultado, mas nenhum nome bateu com '" + str(palavras_esperadas) + "'", "simbolo": None}


def gerar_relatorio():
    if not TWELVEDATA_API_KEY:
        print("ERRO: TWELVEDATA_API_KEY nao configurada.")
        return

    print("=" * 70)
    print("DIAGNOSTICO TWELVE DATA v2 - busca por nome (mais barato)")
    print("=" * 70)
    print()

    resultados = {}
    for nome_exibicao, termo_busca, palavras_esperadas in ATIVOS_PARA_BUSCAR:
        print("Buscando: " + nome_exibicao + " (termo: '" + termo_busca + "')")
        r = diagnosticar(nome_exibicao, termo_busca, palavras_esperadas)
        resultados[nome_exibicao] = r
        if r["disponivel"]:
            print("  -> OK: simbolo=" + r["simbolo"] + " | nome=" + str(r.get("nome_oficial")) + " | preco=" + str(r["preco"]))
        else:
            print("  -> falhou: " + str(r["motivo"]))
        print()

    print("=" * 70)
    print("RELATORIO FINAL")
    print("=" * 70)
    print()
    for nome_exibicao, _, _ in ATIVOS_PARA_BUSCAR:
        r = resultados[nome_exibicao]
        if r["disponivel"]:
            print("✅ " + nome_exibicao + " — disponível (símbolo: " + r["simbolo"] + ", preço: " + str(r["preco"]) + ")")
        else:
            print("❌ " + nome_exibicao + " — indisponível (" + str(r["motivo"]) + ")")

    disponiveis = sum(1 for r in resultados.values() if r["disponivel"])
    print()
    print("Resumo: " + str(disponiveis) + " de " + str(len(ATIVOS_PARA_BUSCAR)) + " ativos disponíveis.")


if __name__ == "__main__":
    gerar_relatorio()
