/**
 * Universo de ativos pesquisaveis (acoes BR/US + cripto + indices) -
 * extraido de terminal.js pra ser reaproveitado tambem por outras
 * paginas que precisam da mesma base (ex: Minha Exposicao), sem
 * duplicar a lista. Carregar este script ANTES de terminal.js ou de
 * qualquer pagina que use window.AntesDoSinoUniverso.
 *
 * "setor" (so em STOCK_UNIVERSE): classificacao setorial publica e
 * bem conhecida de cada empresa (o mesmo tipo de rotulo que qualquer
 * corretora/agregador financeiro publica) - usado pra permitir busca
 * por setor na busca universal (Ctrl+K), nao e um dado calculado ou
 * proprietario.
 */
(function () {
  "use strict";

  var STOCK_UNIVERSE = [
    { ticker: "VALE3", nome: "Vale", symbol: "BMFBOVESPA:VALE3", setor: "Mineração" },
    { ticker: "ITUB4", nome: "Itaú Unibanco", symbol: "BMFBOVESPA:ITUB4", setor: "Bancos" },
    { ticker: "PETR4", nome: "Petrobras PN", symbol: "BMFBOVESPA:PETR4", setor: "Petróleo e Gás" },
    { ticker: "PETR3", nome: "Petrobras ON", symbol: "BMFBOVESPA:PETR3", setor: "Petróleo e Gás" },
    { ticker: "AXIA3", nome: "Axia Energia (ex-Eletrobras)", symbol: "BMFBOVESPA:AXIA3", setor: "Energia Elétrica" },
    { ticker: "BBAS3", nome: "Banco do Brasil", symbol: "BMFBOVESPA:BBAS3", setor: "Bancos" },
    { ticker: "BBDC4", nome: "Bradesco", symbol: "BMFBOVESPA:BBDC4", setor: "Bancos" },
    { ticker: "SANB11", nome: "Santander Brasil", symbol: "BMFBOVESPA:SANB11", setor: "Bancos" },
    { ticker: "BPAC11", nome: "BTG Pactual", symbol: "BMFBOVESPA:BPAC11", setor: "Bancos" },
    { ticker: "ITSA4", nome: "Itaúsa", symbol: "BMFBOVESPA:ITSA4", setor: "Holding Financeira" },
    { ticker: "B3SA3", nome: "B3", symbol: "BMFBOVESPA:B3SA3", setor: "Serviços Financeiros" },
    { ticker: "ABEV3", nome: "Ambev", symbol: "BMFBOVESPA:ABEV3", setor: "Bebidas" },
    { ticker: "WEGE3", nome: "WEG", symbol: "BMFBOVESPA:WEGE3", setor: "Bens Industriais" },
    { ticker: "MGLU3", nome: "Magazine Luiza", symbol: "BMFBOVESPA:MGLU3", setor: "Varejo" },
    { ticker: "LREN3", nome: "Lojas Renner", symbol: "BMFBOVESPA:LREN3", setor: "Varejo" },
    { ticker: "ASAI3", nome: "Assaí", symbol: "BMFBOVESPA:ASAI3", setor: "Varejo" },
    { ticker: "CRFB3", nome: "Carrefour Brasil", symbol: "BMFBOVESPA:CRFB3", setor: "Varejo" },
    { ticker: "RADL3", nome: "Raia Drogasil", symbol: "BMFBOVESPA:RADL3", setor: "Varejo" },
    { ticker: "NTCO3", nome: "Natura &Co", symbol: "BMFBOVESPA:NTCO3", setor: "Higiene e Cosméticos" },
    { ticker: "CSNA3", nome: "CSN", symbol: "BMFBOVESPA:CSNA3", setor: "Siderurgia" },
    { ticker: "GGBR4", nome: "Gerdau", symbol: "BMFBOVESPA:GGBR4", setor: "Siderurgia" },
    { ticker: "USIM5", nome: "Usiminas", symbol: "BMFBOVESPA:USIM5", setor: "Siderurgia" },
    { ticker: "CMIN3", nome: "CSN Mineração", symbol: "BMFBOVESPA:CMIN3", setor: "Mineração" },
    { ticker: "PRIO3", nome: "PRIO", symbol: "BMFBOVESPA:PRIO3", setor: "Petróleo e Gás" },
    { ticker: "BRAV3", nome: "Brava Energia (ex-3R Petroleum)", symbol: "BMFBOVESPA:BRAV3", setor: "Petróleo e Gás" },
    { ticker: "UGPA3", nome: "Ultrapar", symbol: "BMFBOVESPA:UGPA3", setor: "Distribuição de Combustíveis" },
    { ticker: "VBBR3", nome: "Vibra Energia", symbol: "BMFBOVESPA:VBBR3", setor: "Distribuição de Combustíveis" },
    { ticker: "EQTL3", nome: "Equatorial Energia", symbol: "BMFBOVESPA:EQTL3", setor: "Energia Elétrica" },
    { ticker: "CPLE6", nome: "Copel", symbol: "BMFBOVESPA:CPLE6", setor: "Energia Elétrica" },
    { ticker: "CMIG4", nome: "Cemig", symbol: "BMFBOVESPA:CMIG4", setor: "Energia Elétrica" },
    { ticker: "EMBR3", nome: "Embraer", symbol: "BMFBOVESPA:EMBR3", setor: "Aeroespacial e Defesa" },
    { ticker: "RAIL3", nome: "Rumo", symbol: "BMFBOVESPA:RAIL3", setor: "Transporte e Logística" },
    { ticker: "CCRO3", nome: "CCR", symbol: "BMFBOVESPA:CCRO3", setor: "Infraestrutura e Concessões" },
    { ticker: "HAPV3", nome: "Hapvida", symbol: "BMFBOVESPA:HAPV3", setor: "Saúde" },
    { ticker: "RDOR3", nome: "Rede D'Or", symbol: "BMFBOVESPA:RDOR3", setor: "Saúde" },
    { ticker: "FLRY3", nome: "Fleury", symbol: "BMFBOVESPA:FLRY3", setor: "Saúde" },
    { ticker: "VIVT3", nome: "Vivo (Telefônica Brasil)", symbol: "BMFBOVESPA:VIVT3", setor: "Telecomunicações" },
    { ticker: "TIMS3", nome: "TIM", symbol: "BMFBOVESPA:TIMS3", setor: "Telecomunicações" },
    { ticker: "JBSS3", nome: "JBS", symbol: "BMFBOVESPA:JBSS3", setor: "Alimentos" },
    { ticker: "MRFG3", nome: "Marfrig", symbol: "BMFBOVESPA:MRFG3", setor: "Alimentos" },
    { ticker: "BRFS3", nome: "BRF", symbol: "BMFBOVESPA:BRFS3", setor: "Alimentos" },
    { ticker: "SLCE3", nome: "SLC Agrícola", symbol: "BMFBOVESPA:SLCE3", setor: "Agronegócio" },
    { ticker: "SUZB3", nome: "Suzano", symbol: "BMFBOVESPA:SUZB3", setor: "Papel e Celulose" },
    { ticker: "AZUL4", nome: "Azul", symbol: "BMFBOVESPA:AZUL4", setor: "Transporte Aéreo" },
    { ticker: "GOLL4", nome: "Gol", symbol: "BMFBOVESPA:GOLL4", setor: "Transporte Aéreo" },
    { ticker: "CYRE3", nome: "Cyrela", symbol: "BMFBOVESPA:CYRE3", setor: "Construção Civil" },
    { ticker: "MRVE3", nome: "MRV", symbol: "BMFBOVESPA:MRVE3", setor: "Construção Civil" },
    { ticker: "RENT3", nome: "Localiza", symbol: "BMFBOVESPA:RENT3", setor: "Locação de Veículos" },
    { ticker: "BRAP4", nome: "Bradespar", symbol: "BMFBOVESPA:BRAP4", setor: "Holding (Mineração)" },
    { ticker: "AAPL", nome: "Apple", symbol: "NASDAQ:AAPL", setor: "Tecnologia" },
    { ticker: "TSLA", nome: "Tesla", symbol: "NASDAQ:TSLA", setor: "Automotivo" },
    { ticker: "NVDA", nome: "Nvidia", symbol: "NASDAQ:NVDA", setor: "Tecnologia" },
    { ticker: "MSFT", nome: "Microsoft", symbol: "NASDAQ:MSFT", setor: "Tecnologia" },
  ];

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

  // Indices/cambio pesquisaveis pela busca universal - mesmos simbolos
  // ja usados nos paineis do Terminal (widget-indices/widget-moedas),
  // sem introduzir uma fonte nova. isIndice:true marca esses itens pra
  // quem consome a lista saber que NAO sao acoes individuais - ex: o
  // Contexto do Ativo do Terminal usa isso pra nao gerar um link OBM
  // (o padrao /acoes/<ticker> da OBM so foi confirmado pra acoes BR
  // de verdade, um indice como IBOV geraria uma URL nunca validada).
  var INDEX_UNIVERSE = [
    { ticker: "IBOV", nome: "Ibovespa", symbol: "BMFBOVESPA:IBOV", isIndice: true },
    { ticker: "SPX", nome: "S&P 500", symbol: "FOREXCOM:SPXUSD", isIndice: true },
    { ticker: "NASDAQ", nome: "Nasdaq", symbol: "FOREXCOM:NSXUSD", isIndice: true },
    { ticker: "DOWJONES", nome: "Dow Jones", symbol: "FOREXCOM:DJI", isIndice: true },
    { ticker: "USDBRL", nome: "Dólar (USD/BRL)", symbol: "FX_IDC:USDBRL", isIndice: true },
    { ticker: "VIX", nome: "VIX — Índice de Volatilidade", symbol: "AMEX:VIXY", isIndice: true },
  ];

  window.AntesDoSinoUniverso = {
    STOCK_UNIVERSE: STOCK_UNIVERSE,
    CRYPTO_UNIVERSE: CRYPTO_UNIVERSE,
    INDEX_UNIVERSE: INDEX_UNIVERSE,
  };
})();
