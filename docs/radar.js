/**
 * Radar de Abertura - home do Antes do Sino.
 *
 * Pagina 100% estatica/client-side. Fontes reais, nenhuma inventada:
 * - Feed de noticias + agenda: dados-terminal.html e eventos_radar.json
 *   (mesmos arquivos gerados por main.py, ja usados no Terminal e no
 *   Calendario - nenhuma duplicacao de logica Python aqui).
 * - Temperatura do Mercado: radar_temperatura.json, calculado em
 *   main.py::compute_market_temperature (Ibovespa/Dolar/Bitcoin
 *   reais via Brapi/TwelveData + tom das noticias do dia).
 * - 5 indicadores essenciais e Ativos em movimento: widgets publicos
 *   da TradingView (mesmos simbolos ja usados no Terminal) - dado ao
 *   vivo, so que visual (nao da pra ler o numero em texto de um
 *   iframe cross-origin), por isso nao entram na Temperatura.
 */
(function () {
  "use strict";

  var STOCK_UNIVERSE = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.STOCK_UNIVERSE) || [];
  var CRYPTO_UNIVERSE = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.CRYPTO_UNIVERSE) || [];
  var TODOS_ATIVOS = STOCK_UNIVERSE.concat(CRYPTO_UNIVERSE);

  function temaWidgetAtual() {
    return window.AntesDoSinoTema && window.AntesDoSinoTema.atual() === "light" ? "light" : "dark";
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---------------------------------------------------------------------
  // Menu mobile (mesmo padrao do Terminal)
  // ---------------------------------------------------------------------
  function inicializarMenuMobile() {
    var botao = document.getElementById("radar-nav-toggle");
    var menu = document.getElementById("radar-nav-links");
    if (!botao || !menu) return;
    function fechar() {
      menu.classList.remove("open");
      botao.setAttribute("aria-expanded", "false");
    }
    botao.addEventListener("click", function () {
      var abrindo = !menu.classList.contains("open");
      menu.classList.toggle("open", abrindo);
      botao.setAttribute("aria-expanded", abrindo ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.classList.contains("open")) fechar();
    });
    document.addEventListener("click", function (e) {
      if (!menu.classList.contains("open")) return;
      if (menu.contains(e.target) || botao.contains(e.target)) return;
      fechar();
    });
  }

  // ---------------------------------------------------------------------
  // Data/hora + status de mercado com 4 estados (fechada/pre-abertura/
  // aberta/pos-mercado) - versao mais detalhada do que o badge simples
  // (aberto/fechado) ja usado no resto do site, especifica pro hero do
  // Radar. Simplificado de proposito (nao cobre feriados), mesmo
  // disclaimer ja usado em theme.js::statusMercado.
  // ---------------------------------------------------------------------
  function statusB3Detalhado() {
    var partes = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Sao_Paulo", hour12: false,
      weekday: "short", hour: "2-digit", minute: "2-digit",
    }).formatToParts(new Date());
    var mapa = {};
    partes.forEach(function (p) { mapa[p.type] = p.value; });
    var diaUtil = ["Mon", "Tue", "Wed", "Thu", "Fri"].indexOf(mapa.weekday) !== -1;
    var minutos = parseInt(mapa.hour, 10) * 60 + parseInt(mapa.minute, 10);

    if (!diaUtil) return "B3 fechada";
    if (minutos < 9 * 60 + 45) return "B3 fechada";
    if (minutos < 10 * 60) return "Pré-abertura";
    if (minutos < 17 * 60) return "Mercado aberto";
    if (minutos < 18 * 60) return "Pós-mercado";
    return "B3 fechada";
  }

  function montarDataHora() {
    var el = document.getElementById("radar-data-hora");
    if (!el) return;
    function render() {
      var agora = new Date();
      var dataTexto = agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "long" });
      var horaTexto = agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
      el.textContent = dataTexto + " · " + horaTexto + " · " + statusB3Detalhado();
    }
    render();
    setInterval(render, 60000);
  }

  // ---------------------------------------------------------------------
  // Onboarding (1a visita, mesmo padrao do Terminal)
  // ---------------------------------------------------------------------
  var ONBOARDING_KEY = "antesdosino_radar_onboarding_v1";
  function inicializarOnboarding() {
    var card = document.getElementById("onboarding-card");
    var fechar = document.getElementById("onboarding-close");
    if (!card || !fechar) return;
    var jaViu = true;
    try {
      jaViu = localStorage.getItem(ONBOARDING_KEY) === "true";
    } catch (e) {
      jaViu = true;
    }
    if (jaViu) return;
    card.classList.add("visible");
    setTimeout(function () { card.classList.add("in"); }, 50);
    fechar.addEventListener("click", function () {
      card.classList.remove("in");
      setTimeout(function () { card.classList.remove("visible"); }, 300);
      try {
        localStorage.setItem(ONBOARDING_KEY, "true");
      } catch (e) {}
    });
  }

  // ---------------------------------------------------------------------
  // Temperatura do Mercado
  // ---------------------------------------------------------------------
  function montarTemperatura() {
    var selo = document.getElementById("temperatura-selo");
    var label = document.getElementById("temperatura-label");
    var frase = document.getElementById("temperatura-frase");
    var fatoresEl = document.getElementById("temperatura-fatores");
    var motivoEl = document.getElementById("temperatura-motivo");
    if (!selo || !label || !frase) return;

    fetch("radar_temperatura.json")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (dado) {
        if (!dado) throw new Error("sem dado");
        selo.className = "temperatura-selo " + dado.classificacao;
        label.textContent = dado.label;
        frase.textContent = dado.frase;

        if (dado.fatores && dado.fatores.length) {
          fatoresEl.innerHTML = dado.fatores.map(function (f) {
            if (f.valor_pct === null || f.valor_pct === undefined) {
              return '<span class="temperatura-fator">' + escapeHtml(f.nome) + ": " + escapeHtml(f.extra || "") + "</span>";
            }
            var pos = f.valor_pct >= 0;
            var cls = pos ? "up" : "down";
            var sinal = pos ? "+" : "";
            return '<span class="temperatura-fator">' + escapeHtml(f.nome) + ': <span class="' + cls + '">' + sinal + f.valor_pct.toFixed(2) + "%</span></span>";
          }).join("");
          fatoresEl.hidden = false;
        }
        if (dado.motivo) {
          motivoEl.textContent = dado.motivo;
          motivoEl.hidden = false;
        }
      })
      .catch(function () {
        selo.className = "temperatura-selo sem_leitura";
        label.textContent = "Sem leitura disponível";
        frase.textContent = "Não foi possível carregar a leitura do dia agora.";
        motivoEl.textContent = "Fonte de dados indisponível no momento. Tente novamente mais tarde.";
        motivoEl.hidden = false;
      });
  }

  // ---------------------------------------------------------------------
  // 5 indicadores essenciais (widgets reais da TradingView, mesmos
  // simbolos ja usados no Terminal - Ibovespa a vista como proxy de
  // "futuro" ja que nao ha codigo de contrato futuro estavel pra
  // hardcodar, dolar, S&P 500 (CFD continuo FOREXCOM), petroleo WTI e
  // VIX via proxy VIXY, todos ja estabelecidos no resto do site).
  // ---------------------------------------------------------------------
  var INDICADORES = [
    { id: "ibov", nome: "Ibovespa", symbol: "BMFBOVESPA:IBOV", nota: "à vista (proxy)" },
    { id: "usd", nome: "Dólar (USD/BRL)", symbol: "FX_IDC:USDBRL", nota: null },
    { id: "sp500", nome: "S&P 500 fut.", symbol: "FOREXCOM:SPXUSD", nota: null },
    { id: "wti", nome: "Petróleo (WTI)", symbol: "TVC:USOIL", nota: null },
    { id: "vix", nome: "VIX", symbol: "AMEX:VIXY", nota: "proxy (ETF VIXY)" },
  ];

  function montarIndicadores() {
    var grid = document.getElementById("indicadores-grid");
    if (!grid) return;
    grid.innerHTML = INDICADORES.map(function (ind) {
      return (
        '<div class="indicador-card">' +
        "<h3>" + escapeHtml(ind.nome) + (ind.nota ? ' <span style="color:var(--slate-dim);font-weight:400;font-size:0.7rem;">(' + escapeHtml(ind.nota) + ")</span>" : "") + "</h3>" +
        '<div class="indicador-widget" id="indicador-widget-' + ind.id + '"></div>' +
        '<div class="indicador-meta"><span>Fonte: TradingView</span><span>Ao vivo</span></div>' +
        "</div>"
      );
    }).join("");

    // Mini Symbol Overview (nome + preco + variacao + minigrafico) em
    // vez do Symbol Info usado antes: o Symbol Info desenha varias
    // colunas lado a lado (anterior/abertura/volume) pensadas pra um
    // painel largo, e como o widget roda dentro de um iframe da
    // TradingView, o CSS daqui nao alcanca o conteudo interno pra
    // diminuir fonte ou reorganizar colunas - em telas menores o card
    // inteiro ficava com texto cortado (reportado pelo usuario com
    // foto da tela). O Mini Symbol Overview mostra so nome/preco/
    // variacao (exatamente o que o card pede) e foi desenhado pra
    // caber num espaco estreito, sem a densidade que nao cabia.
    INDICADORES.forEach(function (ind) {
      window.AntesDoSinoTema.montarWidgetTV(
        "indicador-widget-" + ind.id,
        "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js",
        function (tema) {
          return {
            symbol: ind.symbol,
            width: "100%",
            height: "100%",
            locale: "br",
            dateRange: "1D",
            colorTheme: tema,
            isTransparent: true,
            autosize: true,
          };
        },
        "Carregando " + ind.nome + "..."
      );
    });
  }

  // ---------------------------------------------------------------------
  // Ativos em movimento (widgets reais, mesmo padrao ja usado no
  // Terminal - Hotlists da TradingView)
  // ---------------------------------------------------------------------
  function montarMovimento() {
    window.AntesDoSinoTema.montarWidgetTV(
      "widget-movimento-altas-baixas",
      "https://s3.tradingview.com/external-embedding/embed-widget-hotlists.js",
      function (tema) {
        return {
          colorTheme: tema, dateRange: "1D", exchange: "BMFBOVESPA",
          showChart: false, locale: "br", width: "100%", height: "260", isTransparent: true,
        };
      },
      "Carregando maiores altas e baixas..."
    );
    window.AntesDoSinoTema.montarWidgetTV(
      "widget-movimento-volume",
      "https://s3.tradingview.com/external-embedding/embed-widget-screener.js",
      function (tema) {
        return {
          width: "100%", height: "100%", defaultColumn: "overview", defaultScreen: "volume_leaders",
          market: "brazil", showToolbar: false, colorTheme: tema, locale: "br", isTransparent: true,
        };
      },
      "Carregando maior volume..."
    );
  }

  // ---------------------------------------------------------------------
  // Noticias curadas: reaproveita dados-terminal.html (mesma fonte do
  // Terminal), reagrupa a categoria ja calculada por main.py (ver
  // classify_news_category) num vocabulario editorial diferente
  // (Mercados/Macro/Empresas/Politica economica/Radar global) e numa
  // etiqueta de relevancia (Essencial/Importante/Monitorar) - tudo
  // client-side, sem chamada nova.
  // ---------------------------------------------------------------------
  var CATEGORIA_PARA_SECAO = {
    urgente: "mercados", importante: "mercados", macro: "macro", empresas: "empresas",
    mercados: "mercados", agenda: "politica", contexto: "global", fechamento: "mercados",
    educacional: null, // fora do Radar - conteudo generico, nao factual do dia
  };
  var SECAO_LABEL = { mercados: "MERCADOS", macro: "MACRO", empresas: "EMPRESAS", politica: "POLÍTICA ECONÔMICA", global: "RADAR GLOBAL" };
  var CATEGORIA_PARA_RELEVANCIA = {
    urgente: "essencial", importante: "essencial", macro: "importante", empresas: "importante",
    agenda: "importante", mercados: "monitorar", contexto: "monitorar", fechamento: "monitorar",
  };
  var RELEVANCIA_LABEL = { essencial: "ESSENCIAL", importante: "IMPORTANTE", monitorar: "MONITORAR" };
  var PORQUE_IMPORTA = {
    macro: "Indicadores macroeconômicos como este costumam influenciar juros, câmbio e o apetite por risco no mercado como um todo.",
    empresas: "Notícias sobre empresas específicas podem mover o preço das ações envolvidas e de seus pares no mesmo setor.",
    politica: "Decisões e eventos da agenda econômica costumam ser observados de perto por afetarem expectativas de juros e câmbio.",
    global: "Contexto internacional que pode influenciar o apetite por risco em mercados emergentes, incluindo o Brasil.",
    mercados: "Fato relevante para o comportamento do mercado no curto prazo.",
  };

  // Deteccao simples de titulo em ingles - sem tradução automática
  // (exigiria uma chamada de API que este projeto nao tem no cliente,
  // e nao vamos expor credencial nenhuma no frontend). So sinaliza,
  // pra pessoa saber o que esperar antes de abrir o link.
  var PALAVRAS_EN = /\b(the|and|with|from|says|after|market|stocks|shares|president|will|has|its|new|amid|over|into)\b/i;
  var ACENTOS_PT = /[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]/;
  function pareceIngles(titulo) {
    return PALAVRAS_EN.test(titulo) && !ACENTOS_PT.test(titulo);
  }

  // Dedupe simples: normaliza (minusculo, sem pontuacao) e compara os
  // 6 primeiros termos significativos - noticias sobre o mesmo fato
  // (ex: mesma manchete replicada por 2 fontes) tendem a compartilhar
  // esse prefixo quase igual.
  function assinaturaTitulo(titulo) {
    return titulo.toLowerCase().replace(/[^\wà-ú\s]/gi, "").split(/\s+/).filter(Boolean).slice(0, 6).join(" ");
  }

  var TODAS_NOTICIAS_RADAR = [];

  function carregarNoticias() {
    fetch("dados-terminal.html")
      .then(function (resp) { return resp.ok ? resp.text() : ""; })
      .then(function (html) {
        if (!html) throw new Error("vazio");
        var doc = new DOMParser().parseFromString(html, "text/html");
        var cards = doc.querySelectorAll("#feed-grid .card");
        var vistos = {};
        var itens = [];

        cards.forEach(function (card) {
          var categoria = card.getAttribute("data-categoria") || "mercados";
          var secao = CATEGORIA_PARA_SECAO.hasOwnProperty(categoria) ? CATEGORIA_PARA_SECAO[categoria] : "mercados";
          if (!secao) return; // educacional etc. - fora do Radar

          var tituloEl = card.querySelector("h3");
          var resumoEl = card.querySelector("p");
          var fonteEl = card.querySelector(".src");
          var horaEl = card.querySelector(".time");
          var linkEl = card.querySelector("a.read");

          var titulo = tituloEl ? tituloEl.textContent.trim() : "";
          if (!titulo) return;
          var assinatura = assinaturaTitulo(titulo);
          if (vistos[assinatura]) return; // duplicata (mesmo fato, outra fonte)
          vistos[assinatura] = true;

          itens.push({
            titulo: titulo,
            resumo: resumoEl ? resumoEl.textContent.trim() : "",
            fonte: fonteEl ? fonteEl.textContent.trim() : "",
            hora: horaEl ? horaEl.textContent.trim() : "",
            href: linkEl ? linkEl.getAttribute("href") : "#",
            categoria: categoria,
            secao: secao,
            relevancia: CATEGORIA_PARA_RELEVANCIA[categoria] || "monitorar",
            ingles: pareceIngles(titulo),
          });
        });

        TODAS_NOTICIAS_RADAR = itens;
        renderizarNoticias("todas");
        montarResumo60(itens);
      })
      .catch(function () {
        var grid = document.getElementById("noticias-grid");
        if (grid) {
          grid.innerHTML =
            '<div class="noticias-vazio">Não foi possível carregar as notícias agora. ' +
            '<button type="button" class="widget-retry-btn" id="noticias-retry" style="margin-left:8px;">Tentar novamente</button></div>';
          var botao = document.getElementById("noticias-retry");
          if (botao) botao.addEventListener("click", carregarNoticias);
        }
        var resumo = document.getElementById("resumo60-list");
        if (resumo) resumo.innerHTML = '<div class="resumo60-item"><span class="rotulo">Indisponível</span><p>Não foi possível montar o resumo agora - as notícias não carregaram.</p></div>';
      });
  }

  function renderizarNoticias(filtroSecao) {
    var grid = document.getElementById("noticias-grid");
    if (!grid) return;
    var itens = TODAS_NOTICIAS_RADAR.filter(function (n) { return filtroSecao === "todas" || n.secao === filtroSecao; });

    // Prioriza essencial > importante > monitorar, limitado pra nao
    // afogar a home (feed completo continua no Terminal).
    var ordemRelevancia = { essencial: 0, importante: 1, monitorar: 2 };
    itens.sort(function (a, b) { return ordemRelevancia[a.relevancia] - ordemRelevancia[b.relevancia]; });
    itens = itens.slice(0, 12);

    if (!itens.length) {
      grid.innerHTML = '<div class="noticias-vazio">Nenhuma notícia nesta categoria no momento.</div>';
      return;
    }

    grid.innerHTML = itens.map(function (n) {
      var porque = PORQUE_IMPORTA[n.secao] || PORQUE_IMPORTA.mercados;
      return (
        '<article class="noticia-card">' +
        '<div class="noticia-card-meta">' +
        '<span class="relevancia-selo ' + n.relevancia + '">' + RELEVANCIA_LABEL[n.relevancia] + "</span>" +
        '<span class="categoria-tag">' + (SECAO_LABEL[n.secao] || "") + "</span>" +
        (n.ingles ? '<span class="en-flag">EN</span>' : "") +
        '<span class="src-time">' + escapeHtml(n.fonte) + " · " + escapeHtml(n.hora) + "</span>" +
        "</div>" +
        "<h3>" + escapeHtml(n.titulo) + "</h3>" +
        (n.resumo ? '<p class="resumo">' + escapeHtml(n.resumo) + "</p>" : "") +
        '<p class="porque-importa"><strong>Por que isso importa?</strong> ' + porque + "</p>" +
        '<a href="' + escapeHtml(n.href) + '" target="_blank" rel="noopener" class="ler-mais">Leia a matéria original →</a>' +
        "</article>"
      );
    }).join("");
  }

  function inicializarTabsNoticias() {
    var tabs = document.querySelectorAll(".noticias-tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) {
          t.classList.toggle("active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        renderizarNoticias(tab.getAttribute("data-secao"));
      });
    });
  }

  // ---------------------------------------------------------------------
  // Resumo em 60 segundos - 3 a 5 frases reais, uma por secao com
  // noticia disponivel hoje, usando a MANCHETE de fato mais relevante
  // de cada secao (nao um texto generico nem gerado por IA) - ordem de
  // prioridade: mercados globais -> Brasil (aqui simplificado como
  // "mercados") -> macro -> cambio/commodities (dentro de macro hoje,
  // ver nota) -> empresas.
  // ---------------------------------------------------------------------
  function montarResumo60(itens) {
    var lista = document.getElementById("resumo60-list");
    if (!lista) return;

    var ordem = [
      { secao: "mercados", rotulo: "Mercados" },
      { secao: "macro", rotulo: "Juros & Macro" },
      { secao: "politica", rotulo: "Política Econômica" },
      { secao: "empresas", rotulo: "Empresas" },
      { secao: "global", rotulo: "Radar Global" },
    ];

    var linhas = [];
    ordem.forEach(function (o) {
      var top = itens.filter(function (n) { return n.secao === o.secao; })[0];
      if (top) linhas.push({ rotulo: o.rotulo, titulo: top.titulo, fonte: top.fonte, hora: top.hora });
    });
    linhas = linhas.slice(0, 5);

    if (!linhas.length) {
      lista.innerHTML = '<div class="resumo60-item"><span class="rotulo">Sem dados</span><p>Ainda não há notícias suficientes hoje para montar o resumo.</p></div>';
      return;
    }

    lista.innerHTML = linhas.map(function (l) {
      return (
        '<div class="resumo60-item">' +
        '<span class="rotulo">' + escapeHtml(l.rotulo) + "</span>" +
        "<p>" + escapeHtml(l.titulo) + '<span class="fonte">' + escapeHtml(l.fonte) + " · " + escapeHtml(l.hora) + "</span></p>" +
        "</div>"
      );
    }).join("");
  }

  // ---------------------------------------------------------------------
  // Agenda do dia - reaproveita eventos_radar.json (mesma fonte real
  // do Calendario), mostra os 3 mais proximos.
  // ---------------------------------------------------------------------
  function carregarAgenda() {
    fetch("eventos_radar.json")
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (eventos) {
        var lista = document.getElementById("agenda-list");
        if (!lista) return;
        if (!eventos || !eventos.length) {
          lista.innerHTML = '<div class="agenda-vazio">Nosso radar não identificou eventos com data marcada nos próximos dias.</div>';
          return;
        }
        var top3 = eventos.slice().sort(function (a, b) { return a.days_away - b.days_away; }).slice(0, 3);
        lista.innerHTML = top3.map(function (ev) {
          var quando = ev.days_away === 0 ? "Hoje" : (ev.days_away === 1 ? "Amanhã" : "Em " + ev.days_away + " dias");
          return (
            '<div class="agenda-item">' +
            '<span class="agenda-quando">' + quando + "</span>" +
            '<div class="agenda-body"><h3>' + escapeHtml(ev.label || "") + "</h3>" +
            (ev.why ? "<p>" + escapeHtml(ev.why) + "</p>" : "") +
            "</div></div>"
          );
        }).join("");
      })
      .catch(function () {
        var lista = document.getElementById("agenda-list");
        if (lista) lista.innerHTML = '<div class="agenda-vazio">Não foi possível carregar a agenda agora.</div>';
      });
  }

  // ---------------------------------------------------------------------
  // Minha Atencao - mesma chave de localStorage da Exposicao completa
  // (antesdosino_exposicao_v1), sem duplicar logica de adicionar/
  // remover aqui - so mostra um resumo e linka pra pagina completa.
  // ---------------------------------------------------------------------
  var EXPOSICAO_STORAGE_KEY = "antesdosino_exposicao_v1";

  function carregarExposicao() {
    try {
      var raw = localStorage.getItem(EXPOSICAO_STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function adicionarAExposicao(ticker) {
    var ativo = TODOS_ATIVOS.filter(function (a) { return a.ticker === ticker; })[0];
    if (!ativo) return;
    var lista = carregarExposicao();
    if (lista.some(function (item) { return item.ticker === ticker; })) {
      montarAtencao();
      return;
    }
    lista.push({ ticker: ativo.ticker, nome: ativo.nome, symbol: ativo.symbol, tags: [], observacao: "", addedAt: new Date().toISOString() });
    try {
      localStorage.setItem(EXPOSICAO_STORAGE_KEY, JSON.stringify(lista));
    } catch (e) {}
    montarAtencao();
  }

  function montarAtencao() {
    var vazio = document.getElementById("atencao-vazio");
    var listaEl = document.getElementById("atencao-lista");
    if (!vazio || !listaEl) return;
    var lista = carregarExposicao();

    if (!lista.length) {
      vazio.hidden = false;
      listaEl.hidden = true;
      return;
    }

    vazio.hidden = true;
    listaEl.hidden = false;
    var top3 = lista.slice().sort(function (a, b) { return (b.addedAt || "").localeCompare(a.addedAt || ""); }).slice(0, 3);
    listaEl.innerHTML = top3.map(function (item) {
      var tvUrl = "https://www.tradingview.com/symbols/" + item.symbol.replace(":", "-") + "/";
      return (
        '<div class="atencao-item">' +
        '<div><span class="ticker">' + escapeHtml(item.ticker) + '</span><span class="nome">' + escapeHtml(item.nome) + "</span></div>" +
        '<a href="' + tvUrl + '" target="_blank" rel="noopener">Ver cotação →</a>' +
        "</div>"
      );
    }).join("");
  }

  function inicializarAtencao() {
    document.querySelectorAll(".atencao-exemplo").forEach(function (btn) {
      btn.addEventListener("click", function () { adicionarAExposicao(btn.getAttribute("data-exemplo")); });
    });
    montarAtencao();
  }

  // ---------------------------------------------------------------------
  // Busca universal (Ctrl+K) - versao enxuta do Radar: comandos
  // navegam pras paginas, ticker abre a cotacao na TradingView (o
  // Radar nao tem o drawer "Contexto do Ativo" do Terminal, entao nao
  // finge ter - o link externo e uma alternativa honesta).
  // ---------------------------------------------------------------------
  var CMDK_COMANDOS_RADAR = [
    { chaves: ["terminal"], label: "Terminal completo", href: "terminal.html" },
    { chaves: ["agenda", "calendario", "calendário"], label: "Calendário Econômico", href: "calendario.html" },
    { chaves: ["mapa", "heatmap", "calor"], label: "Mapa de Calor", href: "mapa.html" },
    { chaves: ["quant", "screener"], label: "Painel Quantitativo", href: "quant.html" },
    { chaves: ["exposição", "exposicao", "watchlist"], label: "Minha Exposição", href: "exposicao.html" },
  ];

  function inicializarCmdk() {
    var botao = document.getElementById("btn-cmdk");
    var backdrop = document.getElementById("cmdk-backdrop");
    var modal = document.getElementById("cmdk-modal");
    var input = document.getElementById("cmdk-input");
    var body = document.getElementById("cmdk-body");
    if (!botao || !modal || !input || !body) return;

    function abrir() {
      modal.classList.add("open");
      backdrop.classList.add("open");
      modal.removeAttribute("aria-hidden");
      input.value = "";
      renderResultados("");
      input.focus();
    }
    function fechar() {
      modal.classList.remove("open");
      backdrop.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
      body.innerHTML = "";
      botao.focus();
    }
    function estaAberto() { return modal.classList.contains("open"); }

    function renderResultados(query) {
      var q = query.trim().toLowerCase();
      if (!q) {
        body.innerHTML = '<div class="cmdk-empty">Digite um ticker (ex: PETR4, VALE3, AAPL), cripto (ex: Bitcoin) ou comando (agenda, mapa, quant, exposição, terminal)…</div>';
        return;
      }
      var comandos = CMDK_COMANDOS_RADAR.filter(function (c) {
        return c.chaves.some(function (k) { return k.indexOf(q) === 0; });
      });
      var tickers = TODOS_ATIVOS.filter(function (t) {
        return t.ticker.toLowerCase().indexOf(q) === 0 || t.nome.toLowerCase().indexOf(q) !== -1;
      }).slice(0, 6);

      var html = "";
      if (comandos.length) {
        html += '<div class="cmdk-section-label">Ir para</div>';
        comandos.forEach(function (c) {
          html += '<div class="cmdk-row" data-cmdk-nav="' + escapeHtml(c.href) + '"><span class="nome">' + escapeHtml(c.label) + '</span><span class="cmdk-arrow">→</span></div>';
        });
      }
      if (tickers.length) {
        html += '<div class="cmdk-section-label">Ativos (abre na TradingView)</div>';
        tickers.forEach(function (t, i) {
          html += '<div class="cmdk-row' + (i === 0 ? " active" : "") + '" data-cmdk-symbol="' + escapeHtml(t.symbol) + '"><span class="ticker">' + escapeHtml(t.ticker) + '</span><span class="nome">' + escapeHtml(t.nome) + "</span></div>";
        });
      }
      if (!html) html = '<div class="cmdk-empty">Nenhum resultado para "' + escapeHtml(query) + '"</div>';
      body.innerHTML = html;

      body.querySelectorAll("[data-cmdk-nav]").forEach(function (el) {
        el.addEventListener("click", function () { window.location.href = el.getAttribute("data-cmdk-nav"); });
      });
      body.querySelectorAll("[data-cmdk-symbol]").forEach(function (el) {
        el.addEventListener("click", function () {
          var symbol = el.getAttribute("data-cmdk-symbol");
          window.open("https://www.tradingview.com/symbols/" + symbol.replace(":", "-") + "/", "_blank", "noopener");
          fechar();
        });
      });
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
      if (e.key === "Escape" && estaAberto()) fechar();
    });
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var primeira = body.querySelector(".cmdk-row");
      if (primeira) primeira.click();
    });
  }

  // ---------------------------------------------------------------------
  // Personalizacao: mostrar/ocultar secoes do Radar, persistido em
  // localStorage - mesmo padrao ja usado no Terminal (paineis), so que
  // aplicado a secoes inteiras da home em vez de widgets individuais.
  // ---------------------------------------------------------------------
  var SECOES_PERSONALIZAVEIS = [
    { id: "temperatura-secao", label: "Temperatura do Mercado" },
    { id: "indicadores-secao", label: "5 indicadores essenciais" },
    { id: "resumo60-secao", label: "Resumo em 60 segundos" },
    { id: "noticias-secao", label: "Notícias que importam" },
    { id: "agenda-secao", label: "Agenda do dia" },
    { id: "movimento-secao", label: "Ativos em movimento" },
    { id: "atencao-secao", label: "Minha Atenção" },
  ];
  var RADAR_PREFS_KEY = "antesdosino_radar_secoes_v1";

  function marcarIdsDasSecoes() {
    // A maioria das <section> nao tem id proprio no HTML (usam
    // aria-labelledby) - atribui um id estavel por ordem, casando com
    // SECOES_PERSONALIZAVEIS (a secao de Temperatura ja tem o id certo
    // fixo no HTML, reatribuir o mesmo valor aqui e inofensivo).
    var lista = document.querySelectorAll(".radar-section");
    SECOES_PERSONALIZAVEIS.forEach(function (def, i) {
      if (lista[i]) lista[i].id = def.id;
    });
  }

  function carregarPrefsSecoes() {
    try {
      var raw = localStorage.getItem(RADAR_PREFS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }
  function salvarPrefsSecoes(ocultos) {
    try {
      localStorage.setItem(RADAR_PREFS_KEY, JSON.stringify(ocultos));
    } catch (e) {}
  }

  function inicializarPersonalizacao() {
    marcarIdsDasSecoes();
    var lista = document.getElementById("customize-list");
    var ocultos = carregarPrefsSecoes();
    if (!lista) return;

    lista.innerHTML = SECOES_PERSONALIZAVEIS.map(function (def) {
      return '<label class="customize-item"><input type="checkbox" data-secao="' + def.id + '" ' + (ocultos[def.id] ? "" : "checked") + '><span>' + escapeHtml(def.label) + "</span></label>";
    }).join("");

    function aplicar() {
      SECOES_PERSONALIZAVEIS.forEach(function (def) {
        var el = document.getElementById(def.id);
        if (el) el.style.display = ocultos[def.id] ? "none" : "";
      });
    }
    aplicar();

    lista.querySelectorAll("input[type=checkbox]").forEach(function (chk) {
      chk.addEventListener("change", function () {
        var id = chk.getAttribute("data-secao");
        ocultos[id] = !chk.checked;
        salvarPrefsSecoes(ocultos);
        aplicar();
      });
    });

    var drawer = document.getElementById("customize-drawer");
    var backdrop = document.getElementById("drawer-backdrop");
    var botaoAbrir = document.getElementById("btn-customize");
    function abrirDrawer() {
      drawer.classList.add("open");
      backdrop.classList.add("open");
      drawer.removeAttribute("aria-hidden");
      document.getElementById("customize-close").focus();
    }
    function fecharDrawer() {
      drawer.classList.remove("open");
      backdrop.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
      botaoAbrir.focus();
    }
    botaoAbrir.addEventListener("click", abrirDrawer);
    document.getElementById("customize-close").addEventListener("click", fecharDrawer);
    backdrop.addEventListener("click", fecharDrawer);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && drawer.classList.contains("open")) fecharDrawer();
    });
    document.getElementById("customize-reset").addEventListener("click", function () {
      try {
        localStorage.removeItem(RADAR_PREFS_KEY);
      } catch (e) {}
      window.location.reload();
    });
  }

  // ---------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    inicializarMenuMobile();
    montarDataHora();
    inicializarOnboarding();
    montarTemperatura();
    montarIndicadores();
    montarMovimento();
    carregarNoticias();
    inicializarTabsNoticias();
    carregarAgenda();
    inicializarAtencao();
    inicializarCmdk();
    inicializarPersonalizacao();
    if (window.AntesDoSinoTema) window.AntesDoSinoTema.montarMarketStatus("market-status-container");
  });

  document.addEventListener(window.AntesDoSinoTema ? window.AntesDoSinoTema.EVENTO : "antesdosino-tema-trocado", function () {
    montarIndicadores();
    montarMovimento();
  });
})();
