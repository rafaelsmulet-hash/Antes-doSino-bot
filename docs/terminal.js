/*
 * Terminal Pré-Market — Antes do Sino
 * ======================================
 * Pagina 100% estatica/client-side, sem dependencia de backend novo:
 * - Cotacoes: widgets embutidos da TradingView (dados deles, nao nossos).
 * - Noticias: busca dados-terminal.html (mesma origem - o arquivo interno
 *   que o main.py gera com o feed completo, nao e uma pagina do site) e
 *   le o feed real - zero duplicacao de logica Python aqui.
 * - Personalizacao (ordem/visibilidade dos paineis): SortableJS + localStorage.
 */

(function () {
  "use strict";

  var STORAGE_KEY = "antesdosino_terminal_prefs_v1";

  // Os widgets da TradingView tem cor propria (parametro colorTheme)
  // que nao segue o CSS da pagina - por isso le o tema atual do site
  // (ver theme.js) toda vez que um widget e (re)criado, em vez de
  // fixar "dark" direto no JSON de configuracao.
  function temaWidgetAtual() {
    return window.AntesDoSinoTema && window.AntesDoSinoTema.atual() === "light" ? "light" : "dark";
  }

  var PANEL_DEFS = [
    { id: "indices", label: "Índices Mundiais & Futuros US" },
    { id: "moedas", label: "Dólar & Moedas Globais" },
    { id: "emergentes", label: "Emergentes" },
    { id: "commodities", label: "Commodities" },
    { id: "acoes", label: "Ações Brasil" },
    { id: "cripto", label: "Criptomoedas" },
    { id: "vix", label: "VIX — Índice de Volatilidade" },
    { id: "market-movers", label: "Ativos em Destaque (B3)" },
  ];

  // ---------------------------------------------------------------------
  // Widgets TradingView - cada painel de cotacao e um "Symbol Overview"
  // com a lista de simbolos daquela categoria. Widget publico, gratuito,
  // sem chave de API (https://www.tradingview.com/widget/).
  // ---------------------------------------------------------------------

  // Skeleton (placeholder pulsante, ver .loading no CSS) enquanto o
  // widget carrega - a TradingView nao expoe um evento de "terminei de
  // renderizar" pra iframe de terceiro (cross-origin), entao usa um
  // tempo fixo como aproximacao pratica (mesmo padrao usado por vários
  // apps de produção pra widgets externos sem callback de load).
  var SKELETON_DURACAO_MS = 1300;

  function aplicarSkeleton(container) {
    if (!container) return;
    container.classList.add("loading");
    setTimeout(function () {
      container.classList.remove("loading");
    }, SKELETON_DURACAO_MS);
  }

  // Estado de erro (ver .widget-error-state no design-system.css) -
  // usado quando o <script> de embed da TradingView falha de verdade
  // (bloqueador de anuncio, rede, CDN deles fora do ar). E o unico
  // sinal de falha que da pra detectar - nao ha como saber se um
  // iframe cross-origin carregou "vazio" por dentro, so se o script
  // sequer rodou. "tentarNovamente" reexecuta a mesma funcao de
  // montagem, do zero.
  function montarEstadoErro(container, tentarNovamente) {
    if (!container) return;
    container.classList.remove("loading");
    container.innerHTML =
      '<div class="widget-error-state">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>' +
      "<p>Não foi possível carregar este painel agora. Pode ser um bloqueador de anúncios, instabilidade de rede, ou a TradingView fora do ar.</p>" +
      '<button type="button" class="widget-retry-btn">Tentar novamente</button>' +
      "</div>";
    var botao = container.querySelector(".widget-retry-btn");
    if (botao) botao.addEventListener("click", tentarNovamente);
  }

  function montarSymbolOverview(containerId, simbolos) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = ""; // permite re-renderizar (troca de aba/lista) sem acumular widgets
    aplicarSkeleton(container);

    var wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";

    var widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    wrapper.appendChild(widgetDiv);

    var script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js";
    script.async = true;
    script.text = JSON.stringify({
      symbols: simbolos,
      chartOnly: false,
      width: "100%",
      height: "100%",
      locale: "br",
      colorTheme: temaWidgetAtual(),
      autosize: true,
      showVolume: false,
      showMA: false,
      hideDateRanges: true,
      hideMarketStatus: false,
      hideSymbolLogo: false,
      scalePosition: "right",
      scaleMode: "Normal",
      fontFamily: "Inter, -apple-system, sans-serif",
      fontSize: "11",
      noTimeScale: false,
      valuesTracking: "1",
      changeMode: "price-and-percent",
      chartType: "area",
      backgroundColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      lineType: 0,
      dateRanges: ["1d|1"],
    });
    script.onerror = function () {
      montarEstadoErro(container, function () { montarSymbolOverview(containerId, simbolos); });
    };

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  // Lista compacta (widget "Market Overview" da TradingView, sem
  // grafico - so nome + preco + variacao, 1 linha por ativo). Usada
  // nos paineis com varios ativos (Indices, Moedas, Emergentes,
  // Commodities, Acoes Brasil, Criptomoedas) pra evitar o problema do
  // Symbol Overview: 1 grafico grande (as vezes quase vazio, sem
  // muita variacao no dia) por vez, escondendo os outros ativos atras
  // de abas. Mesma assinatura de montarSymbolOverview (mesmos pares
  // [label, "EXCHANGE:TICKER|intervalo"]) pra poder trocar so a
  // chamada, sem mexer em quem chama.
  function montarListaAtivos(containerId, simbolos) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = "";
    aplicarSkeleton(container);

    var wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";

    var widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    wrapper.appendChild(widgetDiv);

    var symbolsFormatados = simbolos.map(function (par) {
      var label = par[0];
      var symbol = par[1].split("|")[0];
      return { s: symbol, d: label };
    });

    var script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js";
    script.async = true;
    script.text = JSON.stringify({
      colorTheme: temaWidgetAtual(),
      dateRange: "1D",
      showChart: false,
      locale: "br",
      isTransparent: true,
      showSymbolLogo: true,
      showFloatingTooltip: false,
      width: "100%",
      height: "100%",
      tabs: [
        {
          title: "Ativos",
          symbols: symbolsFormatados,
          originalTitle: "Ativos",
        },
      ],
    });
    script.onerror = function () {
      montarEstadoErro(container, function () { montarListaAtivos(containerId, simbolos); });
    };

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  function montarTickerTape() {
    var container = document.getElementById("ticker-tape-container");
    if (!container) return;

    var wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";

    var widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    wrapper.appendChild(widgetDiv);

    var script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    script.async = true;
    script.text = JSON.stringify({
      symbols: [
        { proName: "FOREXCOM:SPXUSD", title: "S&P 500" },
        { proName: "FX_IDC:USDBRL", title: "Dólar (USD/BRL)" },
        { proName: "TVC:GOLD", title: "Ouro" },
        { proName: "BITSTAMP:BTCUSD", title: "Bitcoin" },
        { proName: "BMFBOVESPA:IBOV", title: "Ibovespa" },
      ],
      showSymbolLogo: true,
      colorTheme: temaWidgetAtual(),
      isTransparent: true,
      displayMode: "adaptive",
      locale: "br",
    });
    script.onerror = function () {
      montarEstadoErro(container, montarTickerTape);
    };

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  function montarMarketMovers() {
    var container = document.getElementById("widget-market-movers");
    if (!container) return;
    container.innerHTML = "";
    aplicarSkeleton(container);

    // O widget Hotlists da TradingView so renderiza as linhas que cabem
    // na altura pedida, sem scroll interno proprio - com height:100%
    // (limitado ao espaco pequeno do painel) boa parte da lista de
    // "Maiores Altas/Baixas/Volume Incomum" ficava cortada, sem jeito
    // de ver o resto. Altura fixa maior que o painel visivel + o
    // container pai com overflow-y:auto (ver #widget-market-movers no
    // CSS) da acesso real ao resto da lista via rolagem.
    var wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    wrapper.style.height = "600px";
    wrapper.style.width = "100%";

    var widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    wrapper.appendChild(widgetDiv);

    var script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-hotlists.js";
    script.async = true;
    script.text = JSON.stringify({
      colorTheme: temaWidgetAtual(),
      dateRange: "1D",
      exchange: "BMFBOVESPA",
      showChart: false,
      locale: "br",
      width: "100%",
      height: "600",
      isTransparent: true,
    });
    script.onerror = function () {
      montarEstadoErro(container, montarMarketMovers);
    };

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  function montarTodosOsWidgets() {
    montarTickerTape();

    montarListaAtivos("widget-indices", [
      ["S&P 500", "FOREXCOM:SPXUSD|1D"],
      ["Nasdaq", "FOREXCOM:NSXUSD|1D"],
      ["Dow Jones", "FOREXCOM:DJI|1D"],
      ["Ibovespa", "BMFBOVESPA:IBOV|1D"],
      ["DAX", "XETR:DAX|1D"],
    ]);

    montarListaAtivos("widget-moedas", [
      ["USD/JPY", "FX:USDJPY|1D"],
      ["EUR/USD", "FX:EURUSD|1D"],
      ["GBP/USD", "FX:GBPUSD|1D"],
      ["USD/BRL", "FX_IDC:USDBRL|1D"],
    ]);

    montarListaAtivos("widget-emergentes", [
      ["USD/MXN", "FX_IDC:USDMXN|1D"],
      ["USD/ZAR", "FX_IDC:USDZAR|1D"],
      ["USD/TRY", "FX_IDC:USDTRY|1D"],
    ]);

    montarListaAtivos("widget-commodities", [
      ["Petróleo (WTI)", "TVC:USOIL|1D"],
      ["Ouro", "TVC:GOLD|1D"],
      ["Prata", "TVC:SILVER|1D"],
      ["Milho", "FOREXCOM:CORN|1D"],
    ]);

    montarSymbolOverview("widget-vix", [["VIX (via ETF VIXY)", "AMEX:VIXY|1D"]]);
    montarMarketMovers();

    // Fluxo Estrangeiro (proxy via EWZ - nao ha fonte gratuita do dado
    // oficial de fluxo cambial da B3) + Curva DI (contratos futuros
    // BMFBOVESPA, disponiveis de graca na TradingView) - ver aba
    // "Contexto Macro" na sidebar.
    montarListaAtivos("widget-macro", [
      ["Fluxo Estrangeiro (proxy: EWZ)", "AMEX:EWZ|1D"],
      ["DI Jan/27", "BMFBOVESPA:DI1F2027|1D"],
      ["DI Jan/28", "BMFBOVESPA:DI1F2028|1D"],
      ["DI Jan/29", "BMFBOVESPA:DI1F2029|1D"],
      ["DI Jan/30", "BMFBOVESPA:DI1F2030|1D"],
      ["DI Jan/31", "BMFBOVESPA:DI1F2031|1D"],
      ["DI Jan/32", "BMFBOVESPA:DI1F2032|1D"],
      ["DI Jan/33", "BMFBOVESPA:DI1F2033|1D"],
      ["DI Jan/34", "BMFBOVESPA:DI1F2034|1D"],
      ["DI Jan/35", "BMFBOVESPA:DI1F2035|1D"],
      ["DI Jan/36", "BMFBOVESPA:DI1F2036|1D"],
      ["DI Jan/37", "BMFBOVESPA:DI1F2037|1D"],
    ]);

    montarWidgetAcoes(); // Top 10 / Minha lista - ver secao "Bloco picker" abaixo
    montarWidgetCripto(); // idem, para criptomoedas
  }

  // ---------------------------------------------------------------------
  // Blocos "picker" (Ações Brasil e Criptomoedas): aba "Top 10" (fixa) e
  // aba "Minha lista" (busca + selecao propria do usuario, persistida em
  // localStorage). O widget TradingView e recriado do zero a cada troca
  // de aba/lista. Logica generica em criarBlocoPicker() mais abaixo.
  // ---------------------------------------------------------------------

  // Top 10 do Ibovespa por peso na carteira teorica (B3) - pesquisado,
  // nao de memoria. PETR3/PETR4 sao a mesma empresa (classes de acao
  // diferentes), entao mantemos so PETR4 pra nao repetir a Petrobras e
  // abrir espaco pra 10 empresas distintas. Posicoes 9-10 tem mais
  // variacao entre rebalanceamentos da B3 (a cada 4 meses) do que o
  // topo da lista.
  var TOP10_ACOES = [
    ["Vale", "BMFBOVESPA:VALE3|1D"],
    ["Itaú Unibanco", "BMFBOVESPA:ITUB4|1D"],
    ["Petrobras", "BMFBOVESPA:PETR4|1D"],
    ["Axia Energia (ex-Eletrobras)", "BMFBOVESPA:AXIA3|1D"],
    ["Banco do Brasil", "BMFBOVESPA:BBAS3|1D"],
    ["Bradesco", "BMFBOVESPA:BBDC4|1D"],
    ["B3", "BMFBOVESPA:B3SA3|1D"],
    ["Ambev", "BMFBOVESPA:ABEV3|1D"],
    ["WEG", "BMFBOVESPA:WEGE3|1D"],
    ["BTG Pactual", "BMFBOVESPA:BPAC11|1D"],
  ];

  // Universo pesquisavel pra aba "Minha lista" - nao e a lista completa
  // do Ibovespa (~85 papeis), e uma selecao curada dos nomes mais
  // liquidos/conhecidos por setor, pesquisada (nao de memoria, pelo
  // mesmo motivo do Top 10 - tickers mudam por fusao/rebranding, ex:
  // Eletrobras->Axia, 3R Petroleum->Brava Energia).
  var STOCK_UNIVERSE = [
    { ticker: "VALE3", nome: "Vale", symbol: "BMFBOVESPA:VALE3" },
    { ticker: "ITUB4", nome: "Itaú Unibanco", symbol: "BMFBOVESPA:ITUB4" },
    { ticker: "PETR4", nome: "Petrobras PN", symbol: "BMFBOVESPA:PETR4" },
    { ticker: "PETR3", nome: "Petrobras ON", symbol: "BMFBOVESPA:PETR3" },
    { ticker: "AXIA3", nome: "Axia Energia (ex-Eletrobras)", symbol: "BMFBOVESPA:AXIA3" },
    { ticker: "BBAS3", nome: "Banco do Brasil", symbol: "BMFBOVESPA:BBAS3" },
    { ticker: "BBDC4", nome: "Bradesco", symbol: "BMFBOVESPA:BBDC4" },
    { ticker: "SANB11", nome: "Santander Brasil", symbol: "BMFBOVESPA:SANB11" },
    { ticker: "BPAC11", nome: "BTG Pactual", symbol: "BMFBOVESPA:BPAC11" },
    { ticker: "ITSA4", nome: "Itaúsa", symbol: "BMFBOVESPA:ITSA4" },
    { ticker: "B3SA3", nome: "B3", symbol: "BMFBOVESPA:B3SA3" },
    { ticker: "ABEV3", nome: "Ambev", symbol: "BMFBOVESPA:ABEV3" },
    { ticker: "WEGE3", nome: "WEG", symbol: "BMFBOVESPA:WEGE3" },
    { ticker: "MGLU3", nome: "Magazine Luiza", symbol: "BMFBOVESPA:MGLU3" },
    { ticker: "LREN3", nome: "Lojas Renner", symbol: "BMFBOVESPA:LREN3" },
    { ticker: "ASAI3", nome: "Assaí", symbol: "BMFBOVESPA:ASAI3" },
    { ticker: "CRFB3", nome: "Carrefour Brasil", symbol: "BMFBOVESPA:CRFB3" },
    { ticker: "RADL3", nome: "Raia Drogasil", symbol: "BMFBOVESPA:RADL3" },
    { ticker: "NTCO3", nome: "Natura &Co", symbol: "BMFBOVESPA:NTCO3" },
    { ticker: "CSNA3", nome: "CSN", symbol: "BMFBOVESPA:CSNA3" },
    { ticker: "GGBR4", nome: "Gerdau", symbol: "BMFBOVESPA:GGBR4" },
    { ticker: "USIM5", nome: "Usiminas", symbol: "BMFBOVESPA:USIM5" },
    { ticker: "CMIN3", nome: "CSN Mineração", symbol: "BMFBOVESPA:CMIN3" },
    { ticker: "PRIO3", nome: "PRIO", symbol: "BMFBOVESPA:PRIO3" },
    { ticker: "BRAV3", nome: "Brava Energia (ex-3R Petroleum)", symbol: "BMFBOVESPA:BRAV3" },
    { ticker: "UGPA3", nome: "Ultrapar", symbol: "BMFBOVESPA:UGPA3" },
    { ticker: "VBBR3", nome: "Vibra Energia", symbol: "BMFBOVESPA:VBBR3" },
    { ticker: "EQTL3", nome: "Equatorial Energia", symbol: "BMFBOVESPA:EQTL3" },
    { ticker: "CPLE6", nome: "Copel", symbol: "BMFBOVESPA:CPLE6" },
    { ticker: "CMIG4", nome: "Cemig", symbol: "BMFBOVESPA:CMIG4" },
    { ticker: "EMBR3", nome: "Embraer", symbol: "BMFBOVESPA:EMBR3" },
    { ticker: "RAIL3", nome: "Rumo", symbol: "BMFBOVESPA:RAIL3" },
    { ticker: "CCRO3", nome: "CCR", symbol: "BMFBOVESPA:CCRO3" },
    { ticker: "HAPV3", nome: "Hapvida", symbol: "BMFBOVESPA:HAPV3" },
    { ticker: "RDOR3", nome: "Rede D'Or", symbol: "BMFBOVESPA:RDOR3" },
    { ticker: "FLRY3", nome: "Fleury", symbol: "BMFBOVESPA:FLRY3" },
    { ticker: "VIVT3", nome: "Vivo (Telefônica Brasil)", symbol: "BMFBOVESPA:VIVT3" },
    { ticker: "TIMS3", nome: "TIM", symbol: "BMFBOVESPA:TIMS3" },
    { ticker: "JBSS3", nome: "JBS", symbol: "BMFBOVESPA:JBSS3" },
    { ticker: "MRFG3", nome: "Marfrig", symbol: "BMFBOVESPA:MRFG3" },
    { ticker: "BRFS3", nome: "BRF", symbol: "BMFBOVESPA:BRFS3" },
    { ticker: "SLCE3", nome: "SLC Agrícola", symbol: "BMFBOVESPA:SLCE3" },
    { ticker: "SUZB3", nome: "Suzano", symbol: "BMFBOVESPA:SUZB3" },
    { ticker: "AZUL4", nome: "Azul", symbol: "BMFBOVESPA:AZUL4" },
    { ticker: "GOLL4", nome: "Gol", symbol: "BMFBOVESPA:GOLL4" },
    { ticker: "CYRE3", nome: "Cyrela", symbol: "BMFBOVESPA:CYRE3" },
    { ticker: "MRVE3", nome: "MRV", symbol: "BMFBOVESPA:MRVE3" },
    { ticker: "RENT3", nome: "Localiza", symbol: "BMFBOVESPA:RENT3" },
    { ticker: "BRAP4", nome: "Bradespar", symbol: "BMFBOVESPA:BRAP4" },
    { ticker: "AAPL", nome: "Apple", symbol: "NASDAQ:AAPL" },
    { ticker: "TSLA", nome: "Tesla", symbol: "NASDAQ:TSLA" },
    { ticker: "NVDA", nome: "Nvidia", symbol: "NASDAQ:NVDA" },
    { ticker: "MSFT", nome: "Microsoft", symbol: "NASDAQ:MSFT" },
  ];

  // Top 10 criptomoedas por capitalizacao de mercado (pesquisado, nao de
  // memoria - ranking muda com frequencia). Pares em USD/USDT na Coinbase
  // e Binance, os mesmos provedores ja usados na ticker tape (BITSTAMP/
  // COINBASE), que a TradingView deixa embutir de graca sem bloqueio.
  var TOP10_CRIPTO = [
    ["Bitcoin", "COINBASE:BTCUSD|1D"],
    ["Ethereum", "COINBASE:ETHUSD|1D"],
    ["BNB", "BINANCE:BNBUSDT|1D"],
    ["Solana", "COINBASE:SOLUSD|1D"],
    ["XRP", "COINBASE:XRPUSD|1D"],
    ["Cardano", "COINBASE:ADAUSD|1D"],
    ["Dogecoin", "COINBASE:DOGEUSD|1D"],
    ["Avalanche", "COINBASE:AVAXUSD|1D"],
    ["Chainlink", "COINBASE:LINKUSD|1D"],
    ["Polkadot", "COINBASE:DOTUSD|1D"],
  ];

  // Universo pesquisavel pra aba "Minha lista" das criptos - mesma logica
  // curada do STOCK_UNIVERSE, cobrindo as moedas mais liquidas/conhecidas.
  var CRYPTO_UNIVERSE = [
    { ticker: "BTC", nome: "Bitcoin", symbol: "COINBASE:BTCUSD" },
    { ticker: "ETH", nome: "Ethereum", symbol: "COINBASE:ETHUSD" },
    { ticker: "BNB", nome: "BNB", symbol: "BINANCE:BNBUSDT" },
    { ticker: "SOL", nome: "Solana", symbol: "COINBASE:SOLUSD" },
    { ticker: "XRP", nome: "XRP", symbol: "COINBASE:XRPUSD" },
    { ticker: "ADA", nome: "Cardano", symbol: "COINBASE:ADAUSD" },
    { ticker: "DOGE", nome: "Dogecoin", symbol: "COINBASE:DOGEUSD" },
    { ticker: "AVAX", nome: "Avalanche", symbol: "COINBASE:AVAXUSD" },
    { ticker: "LINK", nome: "Chainlink", symbol: "COINBASE:LINKUSD" },
    { ticker: "DOT", nome: "Polkadot", symbol: "COINBASE:DOTUSD" },
    { ticker: "LTC", nome: "Litecoin", symbol: "COINBASE:LTCUSD" },
    { ticker: "BCH", nome: "Bitcoin Cash", symbol: "COINBASE:BCHUSD" },
    { ticker: "TRX", nome: "Tron", symbol: "BINANCE:TRXUSDT" },
    { ticker: "MATIC", nome: "Polygon", symbol: "COINBASE:MATICUSD" },
    { ticker: "SHIB", nome: "Shiba Inu", symbol: "COINBASE:SHIBUSD" },
    { ticker: "UNI", nome: "Uniswap", symbol: "COINBASE:UNIUSD" },
    { ticker: "ATOM", nome: "Cosmos", symbol: "COINBASE:ATOMUSD" },
    { ticker: "ETC", nome: "Ethereum Classic", symbol: "COINBASE:ETCUSD" },
    { ticker: "XLM", nome: "Stellar", symbol: "COINBASE:XLMUSD" },
    { ticker: "NEAR", nome: "Near Protocol", symbol: "COINBASE:NEARUSD" },
  ];
  var LIMITE_MINHA_LISTA = 15;

  // Bloco "picker" generico: abas Top 10 / Minha lista com busca e
  // persistencia em localStorage. Usado hoje por Ações Brasil e
  // Criptomoedas - cada instancia tem seu proprio estado, elementos
  // (via os ids prefixados por blockId) e chave de storage.
  function criarBlocoPicker(config) {
    var abaAtiva = "top10";
    var listaCustom = [];

    function elId(sufixo) {
      return config.blockId + "-" + sufixo;
    }

    function carregarListaCustom() {
      try {
        var raw = localStorage.getItem(config.storageKey);
        if (!raw) return { aba: "top10", tickers: [] };
        var parsed = JSON.parse(raw);
        return {
          aba: parsed.aba === "custom" ? "custom" : "top10",
          tickers: Array.isArray(parsed.tickers) ? parsed.tickers : [],
        };
      } catch (e) {
        return { aba: "top10", tickers: [] };
      }
    }

    function salvarListaCustom() {
      try {
        localStorage.setItem(
          config.storageKey,
          JSON.stringify({ aba: abaAtiva, tickers: listaCustom })
        );
      } catch (e) {
        console.log("Terminal: não foi possível salvar a lista de " + config.blockId + " (localStorage indisponível).");
      }
    }

    function buscarNoUniverso(termo) {
      var termoLower = termo.trim().toLowerCase();
      if (!termoLower) return [];
      return config.universe.filter(function (ativo) {
        return (
          ativo.ticker.toLowerCase().indexOf(termoLower) !== -1 ||
          ativo.nome.toLowerCase().indexOf(termoLower) !== -1
        );
      }).slice(0, 8);
    }

    function renderResultadosBusca(resultados) {
      var container = document.getElementById(elId("search-results"));
      if (!resultados.length) {
        container.style.display = "none";
        container.innerHTML = "";
        return;
      }
      var html = "";
      resultados.forEach(function (ativo) {
        var jaAdicionado = listaCustom.indexOf(ativo.ticker) !== -1;
        html +=
          '<div class="picker-search-result" data-ticker="' + ativo.ticker + '" style="' +
          (jaAdicionado ? "opacity:0.4;" : "") + '">' +
          '<span><span class="ticker">' + ativo.ticker + "</span> <span class=\"nome\">" + ativo.nome + "</span></span>" +
          (jaAdicionado ? "<span class=\"nome\">já na lista</span>" : "") +
          "</div>";
      });
      container.innerHTML = html;
      container.style.display = "block";

      container.querySelectorAll(".picker-search-result").forEach(function (el) {
        el.addEventListener("click", function () {
          adicionarNaListaCustom(el.getAttribute("data-ticker"));
        });
      });
    }

    function adicionarNaListaCustom(ticker) {
      if (listaCustom.indexOf(ticker) !== -1) return;
      if (listaCustom.length >= LIMITE_MINHA_LISTA) {
        alert("Sua lista já tem " + LIMITE_MINHA_LISTA + " " + config.itemPlural + " (limite). Remova um pra adicionar outro.");
        return;
      }
      listaCustom.push(ticker);
      document.getElementById(elId("search-input")).value = "";
      renderResultadosBusca([]);
      salvarListaCustom();
      renderChips();
      if (abaAtiva === "custom") renderWidgetCustom();
    }

    function removerDaListaCustom(ticker) {
      listaCustom = listaCustom.filter(function (t) {
        return t !== ticker;
      });
      salvarListaCustom();
      renderChips();
      if (abaAtiva === "custom") renderWidgetCustom();
    }

    function renderChips() {
      var container = document.getElementById(elId("chips"));
      if (abaAtiva !== "custom") {
        container.classList.remove("visible");
        return;
      }
      container.classList.add("visible");
      if (!listaCustom.length) {
        container.innerHTML = "";
        return;
      }
      var html = "";
      listaCustom.forEach(function (ticker) {
        html += '<span class="picker-chip">' + ticker + '<button data-remover="' + ticker + '" title="Remover">✕</button></span>';
      });
      container.innerHTML = html;
      container.querySelectorAll("[data-remover]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          removerDaListaCustom(btn.getAttribute("data-remover"));
        });
      });
    }

    function renderWidgetCustom() {
      if (!listaCustom.length) {
        var container = document.getElementById(config.widgetId);
        container.innerHTML = '<div class="picker-empty-hint">' + config.emptyHint + '</div>';
        return;
      }
      var simbolos = listaCustom.map(function (ticker) {
        var ativo = config.universe.filter(function (a) { return a.ticker === ticker; })[0];
        var label = ativo ? ativo.ticker : ticker;
        var symbol = ativo ? ativo.symbol : config.symbolFallbackPrefix + ticker;
        return [label, symbol + "|1D"];
      });
      montarListaAtivos(config.widgetId, simbolos);
    }

    function trocarAba(aba) {
      abaAtiva = aba;
      document.querySelectorAll('.picker-tabs[data-block="' + config.blockId + '"] .picker-tab').forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-picker-tab") === aba);
      });
      document.getElementById(elId("search-row")).classList.toggle("visible", aba === "custom");
      salvarListaCustom();
      renderChips();

      if (aba === "top10") {
        montarListaAtivos(config.widgetId, config.top10);
      } else {
        renderWidgetCustom();
      }
    }

    function montar() {
      var salvo = carregarListaCustom();
      listaCustom = salvo.tickers;

      document.querySelectorAll('.picker-tabs[data-block="' + config.blockId + '"] .picker-tab').forEach(function (btn) {
        btn.addEventListener("click", function () {
          trocarAba(btn.getAttribute("data-picker-tab"));
        });
      });

      var input = document.getElementById(elId("search-input"));
      input.addEventListener("input", function () {
        renderResultadosBusca(buscarNoUniverso(input.value));
      });
      document.addEventListener("click", function (e) {
        if (e.target !== input) {
          document.getElementById(elId("search-results")).style.display = "none";
        }
      });

      trocarAba(salvo.aba);
    }

    return { montar: montar };
  }

  function montarWidgetAcoes() {
    criarBlocoPicker({
      blockId: "acoes",
      widgetId: "widget-acoes",
      universe: STOCK_UNIVERSE,
      top10: TOP10_ACOES,
      storageKey: "antesdosino_terminal_acoes_custom_v1",
      itemPlural: "ações",
      emptyHint: "Busque acima e adicione as ações que você quer acompanhar.",
      symbolFallbackPrefix: "BMFBOVESPA:",
    }).montar();
  }

  function montarWidgetCripto() {
    criarBlocoPicker({
      blockId: "cripto",
      widgetId: "widget-cripto",
      universe: CRYPTO_UNIVERSE,
      top10: TOP10_CRIPTO,
      storageKey: "antesdosino_terminal_cripto_custom_v1",
      itemPlural: "criptomoedas",
      emptyHint: "Busque acima e adicione as criptomoedas que você quer acompanhar.",
      symbolFallbackPrefix: "COINBASE:",
    }).montar();
  }

  // ---------------------------------------------------------------------
  // Noticias reais - busca o dados-terminal.html interno (mesma origem,
  // sem CORS - nao e uma pagina navegavel do site) e reaproveita os
  // cards do feed que o main.py ja gerou.
  // ---------------------------------------------------------------------

  function carregarDadosDoPortal() {
    fetch("dados-terminal.html")
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        popularFeed(doc);
      })
      .catch(function (e) {
        document.getElementById("feed-body").innerHTML =
          '<div class="feed-empty">Não foi possível carregar as notícias agora.</div>';
        console.log("Terminal: falha ao carregar dados do portal - " + e);
      });
  }

  // Guarda o feed completo (nao so os 20 exibidos na coluna lateral)
  // pra busca universal (Ctrl+K) conseguir filtrar noticias por ticker
  // ou palavra-chave sem precisar buscar dados-terminal.html de novo.
  var TODAS_NOTICIAS = [];

  function popularFeed(doc) {
    var cards = doc.querySelectorAll("#feed-grid .card");
    var body = document.getElementById("feed-body");
    if (!cards || cards.length === 0) {
      body.innerHTML = '<div class="feed-empty">Sem notícias no momento.</div>';
      TODAS_NOTICIAS = [];
      return;
    }

    var todas = [];
    var itens = [];
    var limite = 20;
    for (var i = 0; i < cards.length && i < limite; i++) {
      var card = cards[i];
      var badge = card.querySelector(".badge");
      var titulo = card.querySelector("h3");
      var resumo = card.querySelector("p");
      var fonte = card.querySelector(".src");
      var link = card.querySelector("a.read");

      var badgeClasse = badge ? badge.className.replace("badge", "").trim() : "info";
      var badgeTexto = badge ? badge.textContent.trim() : "INFO";
      var tituloTexto = titulo ? titulo.textContent.trim() : "";
      var resumoTexto = resumo ? resumo.textContent.trim() : "";
      var fonteTexto = fonte ? fonte.textContent.trim() : "";
      var href = link ? link.getAttribute("href") : "#";

      todas.push({ titulo: tituloTexto, fonte: fonteTexto, href: href, badgeClasse: badgeClasse, badgeTexto: badgeTexto });
      itens.push({ tituloTexto: tituloTexto, resumoTexto: resumoTexto, fonteTexto: fonteTexto, href: href, badgeClasse: badgeClasse, badgeTexto: badgeTexto });
    }

    // Hierarquia editorial: o 1o item vira "alerta principal" (maior,
    // resumo sempre visivel), os proximos 4 ficam como "destaques"
    // (cards normais), o resto vira uma lista compacta de "radar" -
    // mesma ordem que ja vem do feed (main.py ja prioriza por
    // materialidade), so a apresentacao muda por faixa.
    function montarItem(item, extraClasse) {
      return (
        '<div class="feed-item' + (extraClasse ? " " + extraClasse : "") + '">' +
        '<span class="badge ' + item.badgeClasse + '">' + item.badgeTexto + "</span>" +
        '<h4 class="feed-item-title" role="button" tabindex="0">' + item.tituloTexto + "</h4>" +
        '<span class="src">' + item.fonteTexto + "</span>" +
        (item.resumoTexto
          ? '<div class="feed-item-resumo"><p>' + item.resumoTexto + "</p>" +
            '<a href="' + item.href + '" target="_blank" rel="noopener" class="feed-item-link">Leia a matéria completa &rarr;</a></div>'
          : "") +
        "</div>"
      );
    }

    var html = "";
    if (itens.length) {
      html += '<div class="feed-section-label">Alerta principal</div>';
      html += montarItem(itens[0], "feed-alert");
    }
    if (itens.length > 1) {
      html += '<div class="feed-section-label">Destaques</div>';
      for (var d = 1; d < Math.min(itens.length, 5); d++) {
        html += montarItem(itens[d]);
      }
    }
    if (itens.length > 5) {
      html += '<div class="feed-section-label">Radar</div>';
      for (var r = 5; r < itens.length; r++) {
        html += montarItem(itens[r], "feed-radar-item");
      }
    }

    body.innerHTML = html || '<div class="feed-empty">Sem notícias no momento.</div>';
    TODAS_NOTICIAS = todas;
  }

  // Leitor inline: clicar no titulo expande o resumo (ja vem no card
  // gerado pelo main.py, so nao era exibido na coluna lateral) em vez
  // de abrir a fonte externa direto - "accordion" (so um aberto por
  // vez, pra caber na largura estreita da sidebar). Delegado no
  // container porque os itens sao recriados a cada fetch do feed.
  function inicializarLeitorDeNoticias() {
    var body = document.getElementById("feed-body");
    if (!body) return;
    function alternar(item) {
      var jaAberto = item.classList.contains("expanded");
      body.querySelectorAll(".feed-item.expanded").forEach(function (el) {
        el.classList.remove("expanded");
      });
      if (!jaAberto) item.classList.add("expanded");
    }
    body.addEventListener("click", function (e) {
      var titulo = e.target.closest(".feed-item-title");
      if (!titulo) return;
      var item = titulo.closest(".feed-item");
      if (item) alternar(item);
    });
    body.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var titulo = e.target.closest(".feed-item-title");
      if (!titulo) return;
      e.preventDefault();
      var item = titulo.closest(".feed-item");
      if (item) alternar(item);
    });
  }

  // ---------------------------------------------------------------------
  // Personalizacao: ordem (drag-and-drop) + visibilidade dos paineis,
  // persistidos em localStorage. Nunca quebra se localStorage falhar
  // (modo anonimo, navegador antigo etc) - so nao salva/restaura.
  // ---------------------------------------------------------------------

  function carregarPrefs() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.ordem) || typeof parsed.ocultos !== "object") return null;
      return parsed;
    } catch (e) {
      return null;
    }
  }

  function salvarPrefs(ordem, ocultos) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ordem: ordem, ocultos: ocultos }));
    } catch (e) {
      console.log("Terminal: não foi possível salvar preferências (localStorage indisponível).");
    }
  }

  function ordemAtualDoDom() {
    var ids = [];
    document.querySelectorAll("#panels-grid .panel").forEach(function (p) {
      ids.push(p.getAttribute("data-panel-id"));
    });
    return ids;
  }

  function aplicarOrdem(ordem) {
    var grid = document.getElementById("panels-grid");
    if (!grid || !ordem) return;
    ordem.forEach(function (id) {
      var el = grid.querySelector('[data-panel-id="' + id + '"]');
      if (el) grid.appendChild(el);
    });
  }

  function aplicarVisibilidade(ocultos) {
    PANEL_DEFS.forEach(function (def) {
      var oculto = !!(ocultos && ocultos[def.id]);
      var el = document.querySelector('[data-panel-id="' + def.id + '"]');
      if (el) el.setAttribute("data-hidden", oculto ? "true" : "false");
      var checkbox = document.querySelector('#customize-list input[data-panel="' + def.id + '"]');
      if (checkbox) checkbox.checked = !oculto;
    });
  }

  var estadoOcultos = {};

  function persistirEstadoAtual() {
    salvarPrefs(ordemAtualDoDom(), estadoOcultos);
  }

  function montarListaDePersonalizacao() {
    var lista = document.getElementById("customize-list");
    var html = "";
    PANEL_DEFS.forEach(function (def) {
      html +=
        '<label class="customize-item">' +
        '<input type="checkbox" data-panel="' + def.id + '" checked>' +
        "<span>" + def.label + "</span>" +
        "</label>";
    });
    lista.innerHTML = html;

    lista.querySelectorAll("input[type=checkbox]").forEach(function (chk) {
      chk.addEventListener("change", function () {
        var id = chk.getAttribute("data-panel");
        estadoOcultos[id] = !chk.checked;
        aplicarVisibilidade(estadoOcultos);
        persistirEstadoAtual();
      });
    });
  }

  function inicializarPersonalizacao() {
    montarListaDePersonalizacao();

    var prefsSalvas = carregarPrefs();
    if (prefsSalvas) {
      estadoOcultos = prefsSalvas.ocultos || {};
      aplicarOrdem(prefsSalvas.ordem);
      aplicarVisibilidade(estadoOcultos);
    }

    // Drag-and-drop dos paineis de cotacao (grid 2x2). VIX/Ativos em Destaque ficam
    // numa linha fixa por design (sempre por ultimo).
    if (window.Sortable) {
      Sortable.create(document.getElementById("panels-grid"), {
        handle: ".panel-head",
        animation: 150,
        ghostClass: "dragging",
        onEnd: function () {
          persistirEstadoAtual();
        },
      });
    }

    document.querySelectorAll(".panel-hide-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-hide");
        estadoOcultos[id] = true;
        aplicarVisibilidade(estadoOcultos);
        persistirEstadoAtual();
      });
    });

    document.getElementById("customize-reset").addEventListener("click", function () {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch (e) {}
      window.location.reload();
    });

    var drawer = document.getElementById("customize-drawer");
    var backdrop = document.getElementById("drawer-backdrop");
    function abrirDrawer() {
      drawer.classList.add("open");
      backdrop.classList.add("open");
    }
    function fecharDrawer() {
      drawer.classList.remove("open");
      backdrop.classList.remove("open");
    }
    document.getElementById("btn-customize").addEventListener("click", abrirDrawer);
    document.getElementById("customize-close").addEventListener("click", fecharDrawer);
    backdrop.addEventListener("click", fecharDrawer);
  }

  // ---------------------------------------------------------------------
  // Busca universal (Ctrl+K / Cmd+K): abre um modal com busca de ticker
  // (preco + noticias relacionadas) e atalhos de navegacao (agenda,
  // mapa, quant). Reaproveita STOCK_UNIVERSE/CRYPTO_UNIVERSE (mesmos
  // dados da aba "Minha lista") e TODAS_NOTICIAS (feed ja carregado) -
  // nao busca nada novo, so filtra o que a pagina ja tem.
  // ---------------------------------------------------------------------

  var CMDK_COMANDOS = [
    { chaves: ["agenda", "calendario", "calendário"], label: "Calendário Econômico", href: "calendario.html" },
    { chaves: ["mapa", "heatmap", "calor"], label: "Mapa de Calor", href: "mapa.html" },
    { chaves: ["quant", "screener"], label: "Painel Quantitativo", href: "quant.html" },
  ];

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Fronteira de palavra na busca por ticker/nome dentro de titulos de
  // noticia - sem isso, termos curtos batem como pedaco de palavra sem
  // relacao (ex: "gol" dentro de "Goldman") - mesmo bug de substring
  // que foi corrigido no pipeline em Python (main.py), agora tambem
  // aqui no cliente, que tinha a mesma logica ingenua (indexOf).
  function bateTermoNoTitulo(titulo, termo) {
    if (!termo) return false;
    var regex = new RegExp("\\b" + termo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i");
    return regex.test(titulo);
  }

  // ---------------------------------------------------------------------
  // Contexto do Ativo (drawer): abre ao clicar num ativo no Ctrl+K, no
  // lugar de ir direto pra TradingView numa aba nova. Mostra cotacao
  // (mesmo widget publico ja usado em outros paineis), noticias do
  // nosso proprio feed que mencionam o ativo, e links de saida pra
  // TradingView (grafico completo) e OBM (dados estruturados, quando
  // for uma acao BR - o padrao de URL /acoes/<ticker> so foi
  // confirmado pra esse universo, entao cripto nao mostra esse link
  // pra nao arriscar um link errado).
  // ---------------------------------------------------------------------

  function inicializarContextoAtivo() {
    var drawer = document.getElementById("contexto-drawer");
    var backdrop = document.getElementById("contexto-backdrop");
    if (!drawer || !backdrop) return;

    function fechar() {
      drawer.classList.remove("open");
      backdrop.classList.remove("open");
    }

    document.getElementById("contexto-close").addEventListener("click", fechar);
    backdrop.addEventListener("click", fechar);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && drawer.classList.contains("open")) fechar();
    });

    window.AntesDoSinoContexto = { abrir: abrirContextoAtivo, fechar: fechar };
  }

  function abrirContextoAtivo(item) {
    var drawer = document.getElementById("contexto-drawer");
    var backdrop = document.getElementById("contexto-backdrop");
    if (!drawer || !backdrop) return;

    document.getElementById("contexto-ticker").textContent = item.ticker;
    document.getElementById("contexto-nome").textContent = item.nome;

    montarSymbolOverview("contexto-widget", [[item.nome, item.symbol + "|1D"]]);

    var linkTv = document.getElementById("contexto-link-tv");
    linkTv.href = "https://www.tradingview.com/symbols/" + item.symbol.replace(":", "-") + "/";

    // Padrao /acoes/<ticker> so confirmado pro universo de acoes BR
    // (STOCK_UNIVERSE usa simbolos BMFBOVESPA:) - cripto (COINBASE:)
    // nao mostra esse link, pra nao arriscar uma URL nunca validada.
    var linkObm = document.getElementById("contexto-link-obm");
    if (item.symbol.indexOf("BMFBOVESPA:") === 0) {
      linkObm.href = "https://obm.com.br/acoes/" + item.ticker.toLowerCase();
      linkObm.style.display = "";
    } else {
      linkObm.style.display = "none";
    }

    var lista = document.getElementById("contexto-noticias-lista");
    var relacionadas = TODAS_NOTICIAS.filter(function (n) {
      return bateTermoNoTitulo(n.titulo, item.ticker) || bateTermoNoTitulo(n.titulo, item.nome);
    }).slice(0, 6);

    if (relacionadas.length) {
      lista.innerHTML = relacionadas.map(function (n) {
        return (
          '<div class="contexto-noticia-item">' +
          '<a href="' + escapeHtml(n.href) + '" target="_blank" rel="noopener">' + escapeHtml(n.titulo) + "</a>" +
          '<span class="src">' + escapeHtml(n.fonte) + "</span></div>"
        );
      }).join("");
    } else {
      lista.innerHTML = '<p class="contexto-noticias-vazio">Nenhuma notícia recente do nosso feed menciona esse ativo.</p>';
    }

    drawer.classList.add("open");
    backdrop.classList.add("open");
  }

  function inicializarCmdk() {
    var botao = document.getElementById("btn-cmdk");
    var backdrop = document.getElementById("cmdk-backdrop");
    var modal = document.getElementById("cmdk-modal");
    var input = document.getElementById("cmdk-input");
    var body = document.getElementById("cmdk-body");
    if (!botao || !modal || !input || !body) return;

    var TICKERS_BUSCA = STOCK_UNIVERSE.concat(CRYPTO_UNIVERSE);

    function abrir() {
      modal.classList.add("open");
      backdrop.classList.add("open");
      input.value = "";
      renderResultados("");
      input.focus();
    }

    function fechar() {
      modal.classList.remove("open");
      backdrop.classList.remove("open");
      body.innerHTML = "";
    }

    function estaAberto() {
      return modal.classList.contains("open");
    }

    function renderResultados(query) {
      var q = query.trim().toLowerCase();
      if (!q) {
        body.innerHTML = '<div class="cmdk-empty">Digite um ticker (ex: PETR4) ou comando (agenda, mapa, quant)…</div>';
        return;
      }

      var comandos = CMDK_COMANDOS.filter(function (c) {
        return c.chaves.some(function (k) { return k.indexOf(q) === 0; });
      });

      var tickers = TICKERS_BUSCA.filter(function (t) {
        return t.ticker.toLowerCase().indexOf(q) === 0 || t.nome.toLowerCase().indexOf(q) !== -1;
      }).slice(0, 5);

      // "q" e o texto que o usuario esta digitando agora mesmo (pode ser
      // parcial, tipo "pet" pra "Petrobras") - continua usando substring
      // simples de proposito, senao quebraria a busca-enquanto-digita.
      // Ja ticker/nome do primeiro resultado sao termos COMPLETOS, entao
      // usam fronteira de palavra (ver bateTermoNoTitulo) pra nao bater
      // como pedaco de outra palavra (mesmo cuidado do main.py).
      var noticias = TODAS_NOTICIAS.filter(function (n) {
        var t = n.titulo.toLowerCase();
        if (t.indexOf(q) !== -1) return true;
        if (!tickers.length) return false;
        return bateTermoNoTitulo(n.titulo, tickers[0].ticker) || bateTermoNoTitulo(n.titulo, tickers[0].nome);
      }).slice(0, 5);

      var html = "";
      if (comandos.length) {
        html += '<div class="cmdk-section-label">Ir para</div>';
        comandos.forEach(function (c) {
          html +=
            '<div class="cmdk-row" data-cmdk-nav="' + escapeHtml(c.href) + '">' +
            '<span class="nome">' + escapeHtml(c.label) + "</span>" +
            '<span class="cmdk-arrow">→</span></div>';
        });
      }

      if (tickers.length) {
        html += '<div class="cmdk-section-label">Ativos</div>';
        tickers.forEach(function (t, i) {
          html +=
            '<div class="cmdk-row' + (i === 0 ? " active" : "") + '" data-cmdk-symbol="' + escapeHtml(t.symbol) + '">' +
            '<span class="ticker">' + escapeHtml(t.ticker) + "</span>" +
            '<span class="nome">' + escapeHtml(t.nome) + "</span></div>";
        });
        html += '<div class="cmdk-preview" id="cmdk-preview"></div>';
      }

      if (noticias.length) {
        html += '<div class="cmdk-section-label">Notícias</div>';
        noticias.forEach(function (n) {
          html +=
            '<a class="cmdk-row cmdk-news-item" href="' + escapeHtml(n.href) + '" target="_blank" rel="noopener">' +
            "<div><h4>" + escapeHtml(n.titulo) + "</h4>" +
            '<span class="src">' + escapeHtml(n.fonte) + "</span></div></a>";
        });
      }

      if (!html) {
        html = '<div class="cmdk-empty">Nenhum resultado para "' + escapeHtml(query) + '"</div>';
      }
      body.innerHTML = html;

      body.querySelectorAll("[data-cmdk-nav]").forEach(function (el) {
        el.addEventListener("click", function () {
          window.location.href = el.getAttribute("data-cmdk-nav");
        });
      });
      body.querySelectorAll("[data-cmdk-symbol]").forEach(function (el) {
        el.addEventListener("click", function () {
          var symbol = el.getAttribute("data-cmdk-symbol");
          var item = TICKERS_BUSCA.filter(function (t) { return t.symbol === symbol; })[0];
          fechar();
          if (item) abrirContextoAtivo(item);
        });
      });

      // Preview compacto (cotacao + variacao) do primeiro ativo encontrado -
      // mesmo widget "Symbol Overview" ja usado no painel do VIX.
      if (tickers.length) {
        montarSymbolOverview("cmdk-preview", [[tickers[0].nome, tickers[0].symbol + "|1D"]]);
      }
    }

    botao.addEventListener("click", abrir);
    backdrop.addEventListener("click", fechar);
    input.addEventListener("input", function () { renderResultados(input.value); });

    document.addEventListener("keydown", function (e) {
      var teclaK = e.key === "k" || e.key === "K";
      if ((e.ctrlKey || e.metaKey) && teclaK) {
        e.preventDefault();
        if (estaAberto()) { fechar(); } else { abrir(); }
        return;
      }
      if (e.key === "Escape" && estaAberto()) {
        fechar();
      }
    });

    // Enter ativa a primeira linha da lista (comando, ativo ou noticia) -
    // sem precisar navegar com o mouse.
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var primeira = body.querySelector(".cmdk-row");
      if (primeira) primeira.click();
    });
  }

  // ---------------------------------------------------------------------
  // Abas do conteudo principal (Visao Geral / Mercado / Acoes & Cripto /
  // Volatilidade). Nao remonta nada nem mexe nos widgets - so mostra/
  // oculta as 3 secoes (panels-grid / picker-pair-row / sentiment-row)
  // via data-tab-section, independente da personalizacao (drag/hide),
  // que continua funcionando normalmente dentro de cada secao.
  // ---------------------------------------------------------------------

  var TERM_TAB_STORAGE_KEY = "antesdosino_terminal_tab_v1";

  function ativarTermTab(alvo) {
    document.querySelectorAll(".term-tab").forEach(function (botao) {
      botao.classList.toggle("active", botao.getAttribute("data-term-tab") === alvo);
    });
    document.querySelectorAll("[data-tab-section]").forEach(function (secao) {
      secao.style.display = (alvo === "geral" || secao.getAttribute("data-tab-section") === alvo) ? "" : "none";
    });
    try {
      localStorage.setItem(TERM_TAB_STORAGE_KEY, alvo);
    } catch (e) {
      // localStorage indisponivel (modo anonimo etc) - so nao persiste a aba.
    }
  }

  function inicializarTermTabs() {
    var botoes = document.querySelectorAll(".term-tab");
    if (!botoes.length) return;
    botoes.forEach(function (botao) {
      botao.addEventListener("click", function () {
        ativarTermTab(botao.getAttribute("data-term-tab"));
      });
    });
    var salva = null;
    try {
      salva = localStorage.getItem(TERM_TAB_STORAGE_KEY);
    } catch (e) {
      salva = null;
    }
    if (salva && document.querySelector('.term-tab[data-term-tab="' + salva + '"]')) {
      ativarTermTab(salva);
    }
  }

  // ---------------------------------------------------------------------
  // Abas da sidebar: Noticias / Contexto Macro. So troca visibilidade -
  // os dois paineis ja estao montados (widget-macro entra junto com os
  // outros em montarTodosOsWidgets), sem custo de remontar nada.
  // ---------------------------------------------------------------------

  function inicializarAbasSidebar() {
    var botoes = document.querySelectorAll(".sidebar-tab");
    if (!botoes.length) return;
    botoes.forEach(function (botao) {
      botao.addEventListener("click", function () {
        var alvo = botao.getAttribute("data-sidebar-tab");
        document.querySelectorAll(".sidebar-tab").forEach(function (b) {
          b.classList.toggle("active", b === botao);
        });
        document.querySelectorAll(".sidebar-panel").forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-sidebar-panel") === alvo);
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    montarTodosOsWidgets();
    carregarDadosDoPortal();
    inicializarPersonalizacao();
    inicializarCmdk();
    inicializarAbasSidebar();
    inicializarTermTabs();
    inicializarLeitorDeNoticias();
    inicializarContextoAtivo();
    if (window.AntesDoSinoTema) window.AntesDoSinoTema.montarMarketStatus("market-status-container");
  });

  // Troca de tema (ver theme.js): reconstroi os widgets no colorTheme
  // certo. montarWidgetAcoes/montarWidgetCripto releem a aba/lista
  // salva no localStorage, entao a selecao do usuario nao se perde.
  document.addEventListener("ads:tema-mudou", montarTodosOsWidgets);
})();
