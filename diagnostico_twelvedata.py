"""
Diagnostico Twelve Data - Antes do Sino
==========================================

Script TEMPORARIO, isolado - nao faz parte do pipeline do bot. Testa,
individualmente, cada ativo candidato ao "Radar da Madrugada", com
fallback automatico de simbolo quando fizer sentido, e gera um
relatorio final claro sobre o que realmente funciona no plano
contratado.

Como rodar:
1. Adicionar TWELVEDATA_API_KEY nas variaveis de ambiente (mesmo
   secret que ja usamos no bot).
2. Rodar via workflow (troca temporariamente o "python main.py" por
   "python diagnostico_twelvedata.py" na etapa "Rodar bot"), ou
   localmente se voce tiver Python instalado.
3. Ler o relatorio final impresso no log.
4. Depois de usar, pode apagar este arquivo e reverter o workflow -
   ele nao precisa continuar existindo no projeto.

IMPORTANTE sobre a regra "nunca aproximar":
- Para futuros (S&P Futuro, Nasdaq Futuro), o script NUNCA aceita o
  indice a vista como substituto - se so o indice a vista responder,
  o relatorio marca o futuro como INDISPONIVEL, nao como sucesso.
- Fallbacks testados sao APENAS variacoes de nome do MESMO instrumento
  (ex: "NI225" e "N225" sao dois jeitos de pedir o Nikkei 225 - nunca
  um ativo diferente).
"""

import os
import time
import requests

TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
URL_QUOTE = "https://api.twelvedata.com/quote"

# Cada entrada: (nome_exibicao, tipo, [lista de simbolos candidatos, em ordem de tentativa])
# tipo = "spot" (indice/ativo a vista) ou "futuro" (nunca aceita fallback pra spot)
ATIVOS_PARA_TESTAR = [
    ("USD/BRL", "spot", ["USD/BRL"]),
    ("WTI (Petroleo)", "spot", ["WTI/USD"]),  # "WTI" sozinho removido - colide com a ACAO da W&T Offshore Inc, nao e o petroleo
    ("Nikkei 225", "spot", ["NI225", "N225", "Nikkei 225"]),
    ("Hang Seng", "spot", ["HSI", "HK50", "Hang Seng"]),
    ("Shanghai Composite", "spot", ["SHCOMP", "000001.SS", "Shanghai Composite"]),
    ("ASX 200", "spot", ["AS51", "AXJO", "XJO", "S&P/ASX 200"]),
    ("DAX", "spot", ["DAX", "GDAXI", "DE30"]),
    ("FTSE 100", "spot", ["FTSE", "UK100", "UKX"]),
    ("CAC 40", "spot", ["FCHI", "CAC", "PX1"]),
    ("S&P 500 Futuro", "futuro", ["SPX500USD", "ES1!", "ES=F"]),
    ("Nasdaq Futuro", "futuro", ["NAS100USD", "NQ1!", "NQ=F"]),
    ("Ouro", "spot", ["XAU/USD", "GOLD"]),
    ("DXY (Indice do Dolar)", "spot", ["DXY", "USDX", "DXY/USD"]),
]

# Validacao de nome - depois de um "sucesso", confere se o nome oficial
# devolvido faz sentido pro ativo pedido. Evita repetir o erro do WTI
# (que colidiu com uma acao de mesmo ticker) - se o nome nao bater com
# nenhuma palavra esperada, o resultado e rejeitado por seguranca.
PALAVRAS_ESPERADAS_NO_NOME = {
    "USD/BRL": ["dollar", "real", "brazil"],
    "WTI (Petroleo)": ["crude", "oil", "wti"],
    "Nikkei 225": ["nikkei"],
    "Hang Seng": ["hang seng"],
    "Shanghai Composite": ["shanghai", "sse"],
    "ASX 200": ["asx", "australia"],
    "DAX": ["dax", "germany"],
    "FTSE 100": ["ftse"],
    "CAC 40": ["cac", "france"],
    "S&P 500 Futuro": ["s&p 500 futures", "e-mini", "future"],
    "Nasdaq Futuro": ["nasdaq 100 futures", "e-mini", "future"],
    "Ouro": ["gold"],
    "DXY (Indice do Dolar)": ["dollar index", "dxy"],
}

# Respeita o limite real do plano gratuito: 8 creditos por MINUTO (nao
# por segundo) - 8 segundos de intervalo entre CADA chamada individual
# garante nunca estourar isso, mesmo testando varios simbolos seguidos.
INTERVALO_ENTRE_CHAMADAS_SEGUNDOS = 8

# Simbolos que, se resolverem com sucesso, indicam que na verdade
# caimos no indice a vista (nunca deve ser aceito como resposta valida
# para um item marcado tipo="futuro").
SIMBOLOS_INDICE_A_VISTA_SP = ["SPX", "GSPC", "S&P 500"]
SIMBOLOS_INDICE_A_VISTA_NASDAQ = ["IXIC", "NDX", "COMP"]


def testar_simbolo(simbolo):
    """Faz 1 chamada real a Twelve Data para o simbolo informado.
    Retorna dict com sucesso, nome oficial, preco e erro (quando houver)."""
    try:
        params = {"symbol": simbolo, "apikey": TWELVEDATA_API_KEY}
        response = requests.get(URL_QUOTE, params=params, timeout=15)
        data = response.json()

        if data.get("status") == "error":
            return {
                "sucesso": False,
                "nome_oficial": None,
                "preco": None,
                "erro": data.get("message", "erro desconhecido"),
                "raw": data,
            }

        if "close" not in data:
            return {
                "sucesso": False,
                "nome_oficial": None,
                "preco": None,
                "erro": "resposta sem campo 'close' - " + str(data),
                "raw": data,
            }

        return {
            "sucesso": True,
            "nome_oficial": data.get("name", simbolo),
            "preco": data.get("close"),
            "erro": None,
            "raw": data,
        }
    except Exception as e:
        return {"sucesso": False, "nome_oficial": None, "preco": None, "erro": "excecao: " + str(e), "raw": None}


def diagnosticar_ativo(nome_exibicao, tipo, candidatos):
    """Testa a lista de simbolos candidatos, em ordem, ate achar um que
    funcione de verdade. Para tipo='futuro', nunca aceita um simbolo
    que na pratica devolveu o indice a vista. Tambem valida se o nome
    oficial devolvido faz sentido pro ativo pedido (evita colisao de
    ticker, como aconteceu com "WTI" batendo numa acao)."""
    tentativas = []
    palavras_esperadas = PALAVRAS_ESPERADAS_NO_NOME.get(nome_exibicao, [])

    for simbolo in candidatos:
        resultado = testar_simbolo(simbolo)
        tentativas.append((simbolo, resultado))

        if resultado["sucesso"]:
            nome_lower = (resultado["nome_oficial"] or "").lower()

            if palavras_esperadas and not any(p in nome_lower for p in palavras_esperadas):
                tentativas[-1] = (simbolo, {
                    **resultado,
                    "sucesso": False,
                    "erro": "nome oficial ('" + str(resultado["nome_oficial"]) + "') nao bate com o ativo esperado - REJEITADO (possivel colisao de ticker)",
                })
                time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)
                continue

            if tipo == "futuro":
                candidatos_spot = SIMBOLOS_INDICE_A_VISTA_SP + SIMBOLOS_INDICE_A_VISTA_NASDAQ
                parece_indice_a_vista = any(s.lower() in nome_lower for s in candidatos_spot) or ("index" in nome_lower and "future" not in nome_lower)
                if parece_indice_a_vista:
                    tentativas[-1] = (simbolo, {
                        **resultado,
                        "sucesso": False,
                        "erro": "simbolo resolveu para indice a vista, nao futuro - REJEITADO (regra: nunca aproximar)",
                    })
                    time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)
                    continue

            return {
                "disponivel": True,
                "simbolo_correto": simbolo,
                "nome_oficial": resultado["nome_oficial"],
                "preco": resultado["preco"],
                "tentativas": tentativas,
            }

        time.sleep(INTERVALO_ENTRE_CHAMADAS_SEGUNDOS)  # respeita o limite real de 8 creditos/minuto

    return {
        "disponivel": False,
        "simbolo_correto": None,
        "nome_oficial": None,
        "preco": None,
        "tentativas": tentativas,
    }


def gerar_relatorio():
    if not TWELVEDATA_API_KEY:
        print("ERRO: TWELVEDATA_API_KEY nao configurada. Configure a variavel de ambiente antes de rodar.")
        return

    print("=" * 70)
    print("DIAGNOSTICO TWELVE DATA - Radar da Madrugada")
    print("=" * 70)
    print()

    resultados = {}

    for nome_exibicao, tipo, candidatos in ATIVOS_PARA_TESTAR:
        print("Testando: " + nome_exibicao + " (tentando: " + ", ".join(candidatos) + ")")
        resultado = diagnosticar_ativo(nome_exibicao, tipo, candidatos)
        resultados[nome_exibicao] = resultado

        for simbolo, tentativa in resultado["tentativas"]:
            status = "OK" if tentativa["sucesso"] else "falhou"
            detalhe = tentativa.get("erro") or ("preco=" + str(tentativa.get("preco")))
            print("  -> " + simbolo + ": " + status + " (" + str(detalhe) + ")")
        print()

    print("=" * 70)
    print("RELATORIO FINAL")
    print("=" * 70)
    print()

    for nome_exibicao, tipo, candidatos in ATIVOS_PARA_TESTAR:
        r = resultados[nome_exibicao]
        if r["disponivel"]:
            print("✅ " + nome_exibicao + " — disponível (símbolo correto: " + r["simbolo_correto"] + ", nome oficial: " + str(r["nome_oficial"]) + ", preço atual: " + str(r["preco"]) + ")")
        else:
            ultimo_erro = r["tentativas"][-1][1]["erro"] if r["tentativas"] else "sem tentativa"
            print("❌ " + nome_exibicao + " — indisponível (" + str(ultimo_erro) + ")")

    print()
    print("=" * 70)
    disponiveis = sum(1 for r in resultados.values() if r["disponivel"])
    print("Resumo: " + str(disponiveis) + " de " + str(len(ATIVOS_PARA_TESTAR)) + " ativos disponíveis no plano atual.")
    print("=" * 70)


if __name__ == "__main__":
    gerar_relatorio()
