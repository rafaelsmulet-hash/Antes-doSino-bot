/*
 * Terminal Pré-Market — Antes do Sino
 * ======================================
 * Pagina 100% estatica/client-side, sem dependencia de backend novo:
 * - Cotacoes: widgets embutidos da TradingView (dados deles, nao nossos).
 * - Noticias e clima do dia: busca newsletter.html (mesma origem - a
 *   pagina que o main.py gera com o feed completo) e le o feed real +
 *   a worry-line ja calculada la - zero duplicacao de logica Python aqui.
 * - Personalizacao (ordem/visibilidade dos paineis): SortableJS + localStorage.
 */

(function () {
  "use strict";

  var STORAGE_KEY = "antesdosino_terminal_prefs_v1";

  var PANEL_DEFS = [
    { id: "indices", label: "Índices Mundiais & Futuros US" },
    { id: "moedas", label: "Dólar & Moedas Globais" },
    { id: "emergentes", label: "Emergentes" },
    { id: "commodities", label: "Commodities" },
    { id: "acoes", label: "Ações Brasil — Top 10 (Ibovespa)" },
    { id: "vix", label: "VIX — Índice de Volatilidade" },
    { id: "barometro", label: "Clima do dia (Risk-On/Risk-Off)" },
  ];

  // ---------------------------------------------------------------------
  // Widgets TradingView - cada painel de cotacao e um "Symbol Overview"
  // com a lista de simbolos daquela categoria. Widget publico, gratuito,
  // sem chave de API (https://www.tradingview.com/widget/).
  // ---------------------------------------------------------------------

  function montarSymbolOverview(containerId, simbolos) {
    var container = document.getElementById(containerId);
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
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js";
    script.async = true;
    script.text = JSON.stringify({
      symbols: simbolos,
      chartOnly: false,
      width: "100%",
      height: "100%",
      locale: "br",
      colorTheme: "dark",
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
      colorTheme: "dark",
      isTransparent: true,
      displayMode: "adaptive",
      locale: "br",
    });

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  function montarTodosOsWidgets() {
    montarTickerTape();

    montarSymbolOverview("widget-indices", [
      ["S&P 500", "FOREXCOM:SPXUSD|1D"],
      ["Nasdaq", "FOREXCOM:NSXUSD|1D"],
      ["Dow Jones", "FOREXCOM:DJI|1D"],
      ["Ibovespa", "BMFBOVESPA:IBOV|1D"],
      ["DAX", "XETR:DAX|1D"],
    ]);

    montarSymbolOverview("widget-moedas", [
      ["USD/JPY", "FX:USDJPY|1D"],
      ["EUR/USD", "FX:EURUSD|1D"],
      ["GBP/USD", "FX:GBPUSD|1D"],
      ["USD/BRL", "FX_IDC:USDBRL|1D"],
    ]);

    montarSymbolOverview("widget-emergentes", [
      ["USD/MXN", "FX_IDC:USDMXN|1D"],
      ["USD/ZAR", "FX_IDC:USDZAR|1D"],
      ["USD/TRY", "FX_IDC:USDTRY|1D"],
    ]);

    montarSymbolOverview("widget-commodities", [
      ["Petróleo Brent", "TVC:UKOIL|1D"],
      ["Rio Tinto (proxy minério)", "NYSE:RIO|1D"],
      ["Ouro", "TVC:GOLD|1D"],
      ["Prata", "TVC:SILVER|1D"],
    ]);

    montarSymbolOverview("widget-vix", [["VIX (via ETF VIXY)", "AMEX:VIXY|1D"]]);

    // Top 10 do Ibovespa por peso na carteira teorica (B3) - pesquisado,
    // nao de memoria. PETR3/PETR4 sao a mesma empresa (classes de acao
    // diferentes), entao mantemos so PETR4 pra nao repetir a Petrobras
    // e abrir espaco pra 10 empresas distintas. Posicoes 9-10 tem mais
    // variacao entre rebalanceamentos da B3 (a cada 4 meses) do que o
    // topo da lista.
    montarSymbolOverview("widget-acoes", [
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
    ]);
  }

  // ---------------------------------------------------------------------
  // Noticias reais + clima do dia - busca o newsletter.html publicado
  // (mesma origem, sem CORS) e reaproveita o que o main.py ja gerou: os
  // cards do feed e a worry-line (calma/alerta/info) que vira o barometro.
  // ---------------------------------------------------------------------

  function carregarDadosDoPortal() {
    fetch("newsletter.html")
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        popularFeed(doc);
        popularBarometro(doc);
      })
      .catch(function (e) {
        document.getElementById("feed-body").innerHTML =
          '<div class="feed-empty">Não foi possível carregar as notícias agora.</div>';
        document.getElementById("barometer-state").textContent = "Indisponível";
        console.log("Terminal: falha ao carregar dados do portal - " + e);
      });
  }

  function popularFeed(doc) {
    var cards = doc.querySelectorAll("#feed-grid .card");
    var body = document.getElementById("feed-body");
    if (!cards || cards.length === 0) {
      body.innerHTML = '<div class="feed-empty">Sem notícias no momento.</div>';
      return;
    }

    var html = "";
    var limite = 20;
    for (var i = 0; i < Math.min(cards.length, limite); i++) {
      var card = cards[i];
      var badge = card.querySelector(".badge");
      var titulo = card.querySelector("h3");
      var fonte = card.querySelector(".src");
      var link = card.querySelector("a.read");

      var badgeClasse = badge ? badge.className.replace("badge", "").trim() : "info";
      var badgeTexto = badge ? badge.textContent.trim() : "INFO";
      var tituloTexto = titulo ? titulo.textContent.trim() : "";
      var fonteTexto = fonte ? fonte.textContent.trim() : "";
      var href = link ? link.getAttribute("href") : "#";

      html +=
        '<div class="feed-item">' +
        '<span class="badge ' + badgeClasse + '">' + badgeTexto + "</span>" +
        '<h4><a href="' + href + '" target="_blank" rel="noopener">' + tituloTexto + "</a></h4>" +
        '<span class="src">' + fonteTexto + "</span>" +
        "</div>";
    }
    body.innerHTML = html || '<div class="feed-empty">Sem notícias no momento.</div>';
  }

  function popularBarometro(doc) {
    var worryLine = doc.querySelector(".worry-line");
    var estadoEl = document.getElementById("barometer-state");
    var markerEl = document.getElementById("barometer-marker");
    var captionEl = document.getElementById("barometer-caption");

    if (!worryLine) {
      estadoEl.textContent = "Neutro";
      estadoEl.className = "barometer-state neutro";
      markerEl.style.left = "50%";
      return;
    }

    var textoWorry = worryLine.textContent.trim();
    if (captionEl && textoWorry) {
      captionEl.textContent = textoWorry;
    }

    // A classe "alert" (main.py: build_worry_line_html) cobre TANTO
    // destaque de baixa quanto de alta - so o texto distingue qual e
    // qual ("sinal de baixa" vs "sinal de alta"). Nunca tratar "alert"
    // como sinonimo de Risk-Off sem checar a polaridade real.
    var textoLower = textoWorry.toLowerCase();
    if (worryLine.classList.contains("alert") && textoLower.indexOf("sinal de baixa") !== -1) {
      estadoEl.textContent = "Risk-Off";
      estadoEl.className = "barometer-state risk-off";
      markerEl.style.left = "12%";
    } else if (worryLine.classList.contains("alert") && textoLower.indexOf("sinal de alta") !== -1) {
      estadoEl.textContent = "Risk-On";
      estadoEl.className = "barometer-state risk-on";
      markerEl.style.left = "88%";
    } else if (worryLine.classList.contains("calm")) {
      estadoEl.textContent = "Risk-On";
      estadoEl.className = "barometer-state risk-on";
      markerEl.style.left = "88%";
    } else {
      estadoEl.textContent = "Neutro";
      estadoEl.className = "barometer-state neutro";
      markerEl.style.left = "50%";
    }
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

    // Drag-and-drop dos paineis de cotacao (grid 2x2). VIX/barometro
    // ficam numa linha fixa por design (sentimento sempre por ultimo).
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
  document.addEventListener("DOMContentLoaded", function () {
    montarTodosOsWidgets();
    carregarDadosDoPortal();
    inicializarPersonalizacao();
  });
})();
