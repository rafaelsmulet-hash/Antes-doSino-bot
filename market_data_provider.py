"""
Market Data Provider - camada de abstracao pra fonte de cotacao (Antes do Sino)
================================================================================

Modulo auxiliar ISOLADO (mesmo padrao de editorial_foundation.py): recebe
tudo por parametro, nunca importa main.py de volta. Nenhuma funcao daqui e
chamada pelo pipeline real ainda - existe pra dar um formato comum a
"buscar cotacao" caso uma segunda fonte vire viavel no futuro, sem forcar
uma reescrita do que ja funciona hoje (main.py::fetch_brapi_results segue
sendo a chamada real usada em producao, sem nenhuma mudanca).

Por que um adapter OBM que nao faz nada:
  O usuario confirmou que a OBM (Open Brazil Market) tem endpoints REST em
  /v1/* protegidos por X-API-Key, mas a documentacao formal "vira quando
  for prioridade" - ou seja, NAO EXISTE hoje. CLAUDE.md regra 5 e explicita:
  sem API documentada, nao adivinhamos endpoint nem fazemos scraping de
  chamada interna do site deles. Por isso OBMProvider.cotacao() nao faz
  nenhuma chamada de rede - levanta NotImplementedError sempre, e o adapter
  fica desligado por padrao (OBM_API_ENABLED != "true"). Quando a OBM
  publicar documentacao real, a implementacao entra aqui, isolada, sem
  precisar tocar no restante do pipeline.
"""

import os


class MarketDataProvider:
    """Interface comum: qualquer fonte de cotacao implementa `cotacao`."""

    nome = "abstrato"

    def cotacao(self, ticker):
        """Retorna um dict {symbol, price, change} ou None se indisponivel.
        Implementacoes NUNCA inventam numero - None significa 'sem dado
        agora', nunca um valor estimado ou de outro ticker."""
        raise NotImplementedError


class BrapiProvider(MarketDataProvider):
    """Envolve a chamada real ja usada em producao (main.py::
    fetch_brapi_results), injetada por parametro - este modulo nao duplica
    a logica HTTP nem o token, so da a ela o formato comum da interface."""

    nome = "brapi"

    def __init__(self, fetch_brapi_results_fn):
        self._fetch = fetch_brapi_results_fn

    def cotacao(self, ticker):
        resultados = self._fetch(ticker)
        if not resultados:
            return None
        r = resultados[0]
        return {
            "symbol": r.get("symbol", ticker),
            "price": r.get("regularMarketPrice"),
            "change": r.get("regularMarketChangePercent"),
        }


class OBMProvider(MarketDataProvider):
    """Desabilitado por padrao (OBM_API_ENABLED precisa ser exatamente
    "true"). Mesmo habilitado, cotacao() levanta NotImplementedError - a
    OBM nao tem endpoint documentado publicamente pra cotacao hoje (ver
    docstring do modulo). Isso NAO e um placeholder esquecido: e a
    barreira deliberada contra inventar endpoint (CLAUDE.md regra 5)."""

    nome = "obm"

    def __init__(self):
        self.habilitado = os.environ.get("OBM_API_ENABLED", "false").strip().lower() == "true"

    def cotacao(self, ticker):
        raise NotImplementedError(
            "OBMProvider.cotacao() nao implementado: a OBM nao publica "
            "documentacao formal de API ainda (ver CLAUDE.md regra 5). "
            "Nao adivinhamos endpoint nem fazemos scraping - implementar "
            "aqui so quando houver doc oficial."
        )


def obter_provider(nome, fetch_brapi_results_fn=None):
    """Fabrica simples: 'brapi' (padrao, precisa da funcao de fetch real
    injetada) ou 'obm' (sempre desabilitado hoje, ver OBMProvider)."""
    if nome == "obm":
        return OBMProvider()
    if nome == "brapi":
        if fetch_brapi_results_fn is None:
            raise ValueError("BrapiProvider precisa de fetch_brapi_results_fn")
        return BrapiProvider(fetch_brapi_results_fn)
    raise ValueError("Provider desconhecido: " + str(nome))
