/**
 * Universo de ativos pesquisaveis (acoes BR/US + cripto) - extraido de
 * terminal.js pra ser reaproveitado tambem por outras paginas que
 * precisam da mesma base (ex: Minha Exposicao), sem duplicar a lista.
 * Carregar este script ANTES de terminal.js ou de qualquer pagina que
 * use window.AntesDoSinoUniverso.
 */
(function () {
  "use strict";

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

  window.AntesDoSinoUniverso = { STOCK_UNIVERSE: STOCK_UNIVERSE, CRYPTO_UNIVERSE: CRYPTO_UNIVERSE };
})();
