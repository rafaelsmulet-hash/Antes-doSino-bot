/**
 * Minha Exposicao (watchlist) - primeira versao.
 *
 * Sem backend: tudo salvo em localStorage, por navegador (o proprio
 * pedido original permite isso explicitamente pra uma primeira fase).
 * Reaproveita ticker-universe.js (mesma base de ativos do Ctrl+K do
 * Terminal) e o mesmo feed que dados-terminal.html ja expoe - nenhuma
 * fonte de dado nova, nenhum dado inventado.
 *
 * Deliberadamente NAO mostra retorno contra benchmark nem historico de
 * preco: exigiria uma serie historica propria que o projeto nao tem
 * hoje (mesma limitacao ja documentada no Contexto do Ativo do
 * Terminal) - fabricar esse numero violaria o principio de nao
 * inventar dado.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "antesdosino_exposicao_v1";
  var ORDENAR_STORAGE_KEY = "antesdosino_exposicao_ordenar_v1";
  var universo = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.STOCK_UNIVERSE) || [];
  var universoCripto = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.CRYPTO_UNIVERSE) || [];
  var TODOS_ATIVOS = universo.concat(universoCripto);

  var NOTICIAS = []; // preenchido pelo fetch de dados-terminal.html
  var EVENTOS_CALENDARIO = []; // preenchido pelo fetch de eventos_radar.json (mesma fonte do Calendário)

  var EXEMPLOS_VAZIO = ["PETR4", "VALE3", "AAPL", "BTC"];

  function carregarLista() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function salvarLista(lista) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(lista));
    } catch (e) {
      // localStorage indisponivel (modo anonimo, cota cheia) - a lista
      // continua funcionando nesta visita, so nao persiste.
    }
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function bateTermoNoTitulo(titulo, termo) {
    if (!termo) return false;
    var regex = new RegExp("\\b" + termo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i");
    return regex.test(titulo);
  }

  // ---------------------------------------------------------------------
  // Busca/adicionar ativo
  // ---------------------------------------------------------------------

  function inicializarBusca() {
    var input = document.getElementById("exp-add-input");
    var resultados = document.getElementById("exp-add-results");
    if (!input || !resultados) return;

    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      if (!q) {
        resultados.classList.remove("visible");
        resultados.innerHTML = "";
        return;
      }
      var lista = carregarLista();
      var jaAdicionados = {};
      lista.forEach(function (item) { jaAdicionados[item.ticker] = true; });

      var achados = TODOS_ATIVOS.filter(function (a) {
        return !jaAdicionados[a.ticker] &&
          (a.ticker.toLowerCase().indexOf(q) === 0 || a.nome.toLowerCase().indexOf(q) !== -1);
      }).slice(0, 8);

      if (!achados.length) {
        resultados.innerHTML = '<div class="exp-add-result" style="cursor:default;color:var(--slate-dim);">Nenhum ativo encontrado (ou já está na sua lista)</div>';
        resultados.classList.add("visible");
        return;
      }

      resultados.innerHTML = achados.map(function (a) {
        return '<div class="exp-add-result" data-ticker="' + escapeHtml(a.ticker) + '">' +
          '<span class="ticker">' + escapeHtml(a.ticker) + "</span>" +
          '<span class="nome">' + escapeHtml(a.nome) + "</span></div>";
      }).join("");
      resultados.classList.add("visible");

      resultados.querySelectorAll("[data-ticker]").forEach(function (el) {
        el.addEventListener("click", function () {
          adicionarAtivo(el.getAttribute("data-ticker"));
          input.value = "";
          resultados.classList.remove("visible");
        });
      });
    });

    document.addEventListener("click", function (e) {
      if (!resultados.contains(e.target) && e.target !== input) {
        resultados.classList.remove("visible");
      }
    });
  }

  function adicionarAtivo(ticker) {
    var ativo = TODOS_ATIVOS.filter(function (a) { return a.ticker === ticker; })[0];
    if (!ativo) return;
    var lista = carregarLista();
    if (lista.some(function (item) { return item.ticker === ticker; })) return;
    lista.push({ ticker: ativo.ticker, nome: ativo.nome, symbol: ativo.symbol, tags: [], observacao: "", addedAt: new Date().toISOString() });
    salvarLista(lista);
    renderizarLista();
    // CTA do Telegram so depois que a pessoa de fato usou a
    // ferramenta (adicionou um ativo) - nunca antes disso.
    if (window.AntesDoSinoTema) window.AntesDoSinoTema.mostrarCtaTelegramUmaVez("vip-banner");
  }

  function removerAtivo(ticker) {
    var lista = carregarLista().filter(function (item) { return item.ticker !== ticker; });
    salvarLista(lista);
    renderizarLista();
  }

  // ---------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------

  function noticiasRelacionadas(item) {
    return NOTICIAS.filter(function (n) {
      return bateTermoNoTitulo(n.titulo, item.ticker) || bateTermoNoTitulo(n.titulo, item.nome);
    }).slice(0, 3);
  }

  // Eventos do calendario relacionados ao ativo - mesma fonte real do
  // Calendario (eventos_radar.json, gerado por main.py a partir de
  // mencoes nas proprias noticias), casado por palavra-chave contra
  // ticker/nome/setor do ativo (mesmo padrao de bateTermoNoTitulo). So
  // mostra a secao quando ha pelo menos 1 evento relacionado de
  // verdade - nao inventa "nenhum evento" pra todo card, o que so
  // adicionaria ruido visual sem informacao nova.
  function eventosRelacionados(item) {
    var ativo = TODOS_ATIVOS.filter(function (a) { return a.ticker === item.ticker; })[0];
    var setor = ativo && ativo.setor;
    // Primeira palavra do nome (ex: "Petrobras" de "Petrobras PN") -
    // o nome completo raramente aparece por extenso num texto de
    // evento, mas o nome "de marca" da empresa costuma aparecer.
    var primeiraPalavraNome = (item.nome || "").split(" ")[0];
    return EVENTOS_CALENDARIO.filter(function (ev) {
      var texto = (ev.label || "") + " " + (ev.why || "");
      return bateTermoNoTitulo(texto, item.ticker) ||
        (primeiraPalavraNome && bateTermoNoTitulo(texto, primeiraPalavraNome)) ||
        (setor && bateTermoNoTitulo(texto, setor));
    }).slice(0, 2);
  }

  function ordenarLista(lista) {
    var modo = "recentes";
    try {
      modo = localStorage.getItem(ORDENAR_STORAGE_KEY) || "recentes";
    } catch (e) {
      modo = "recentes";
    }
    var copia = lista.slice();
    if (modo === "ticker") {
      copia.sort(function (a, b) { return a.ticker.localeCompare(b.ticker); });
    } else {
      copia.sort(function (a, b) { return (b.addedAt || "").localeCompare(a.addedAt || ""); });
    }
    return copia;
  }

  // Mini cotacao (preco + variacao + mini-historico de 1 mes) via
  // widget real da TradingView, montado DEPOIS do innerHTML - mesmo
  // helper compartilhado usado no resto do site (loading/erro/retry de
  // graca, ver theme.js::montarWidgetTV).
  function montarCotacoes(lista) {
    if (!window.AntesDoSinoTema) return;
    lista.forEach(function (item) {
      window.AntesDoSinoTema.montarWidgetTV(
        "exp-cotacao-" + item.ticker,
        "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js",
        function (tema) {
          return {
            symbol: item.symbol,
            width: "100%",
            height: "100%",
            locale: "br",
            dateRange: "1M",
            colorTheme: tema,
            isTransparent: false,
            autosize: true,
            noTimeScale: true,
          };
        },
        "Carregando cotação..."
      );
    });
  }

  function renderizarLista() {
    var container = document.getElementById("exp-list-container");
    var toolbar = document.getElementById("exp-toolbar");
    if (!container) return;
    var listaBruta = carregarLista();

    if (toolbar) toolbar.style.display = listaBruta.length ? "" : "none";

    if (!listaBruta.length) {
      container.innerHTML =
        '<div class="exp-empty">Você ainda não adicionou nenhum ativo. Busque acima pra começar a acompanhar, ou use um dos exemplos:' +
        '<div class="exp-empty-exemplos">' +
        EXEMPLOS_VAZIO.map(function (t) {
          return '<button type="button" class="exp-empty-exemplo" data-exemplo="' + escapeHtml(t) + '">' + escapeHtml(t) + "</button>";
        }).join("") +
        "</div></div>";
      container.querySelectorAll("[data-exemplo]").forEach(function (btn) {
        btn.addEventListener("click", function () { adicionarAtivo(btn.getAttribute("data-exemplo")); });
      });
      return;
    }

    var lista = ordenarLista(listaBruta);

    container.innerHTML =
      '<div class="exp-list">' +
      lista.map(function (item) {
        var relacionadas = noticiasRelacionadas(item);
        var eventos = eventosRelacionados(item);
        var tagsHtml = (item.tags || []).map(function (tag) {
          return '<span class="exp-tag">' + escapeHtml(tag) + '<button type="button" data-remover-tag="' + escapeHtml(tag) + '" data-ticker="' + escapeHtml(item.ticker) + '">✕</button></span>';
        }).join("");

        var noticiasHtml = relacionadas.length
          ? relacionadas.map(function (n) {
              return '<div class="exp-noticia-item"><a href="' + escapeHtml(n.href) + '" target="_blank" rel="noopener">' + escapeHtml(n.titulo) + '</a><span class="src">' + escapeHtml(n.fonte) + "</span></div>";
            }).join("")
          : '<p class="exp-sem-noticias">Nenhuma notícia recente do nosso feed menciona esse ativo.</p>';

        var eventosHtml = eventos.length
          ? '<div class="exp-eventos"><h5>Próximos eventos do calendário</h5>' +
            eventos.map(function (ev) {
              var d = new Date(ev.date + "T00:00:00");
              var dataTexto = String(d.getDate()).padStart(2, "0") + "/" + String(d.getMonth() + 1).padStart(2, "0");
              return '<div class="exp-evento-item"><span class="data">' + dataTexto + "</span>" + escapeHtml(ev.label || "") + "</div>";
            }).join("") +
            "</div>"
          : "";

        var tvUrl = "https://www.tradingview.com/symbols/" + item.symbol.replace(":", "-") + "/";
        var obmUrl = item.symbol.indexOf("BMFBOVESPA:") === 0 ? "https://obm.com.br/acoes/" + item.ticker.toLowerCase() : null;

        return (
          '<div class="exp-card" data-ticker="' + escapeHtml(item.ticker) + '">' +
          '<div class="exp-card-head">' +
          "<div><span class=\"ticker\">" + escapeHtml(item.ticker) + '</span><span class="nome">' + escapeHtml(item.nome) + "</span></div>" +
          '<button type="button" class="exp-remove-btn" data-remover="' + escapeHtml(item.ticker) + '" title="Remover da lista">✕ Remover</button>' +
          "</div>" +
          '<div class="exp-cotacao" id="exp-cotacao-' + escapeHtml(item.ticker) + '"></div>' +
          '<div class="exp-tags">' + tagsHtml + '<button type="button" class="exp-tag-add" data-add-tag="' + escapeHtml(item.ticker) + '">+ tag</button></div>' +
          '<textarea class="exp-obs" data-observacao="' + escapeHtml(item.ticker) + '" placeholder="Sua observação sobre esse ativo (tese, motivo de acompanhar, etc.)">' + escapeHtml(item.observacao || "") + "</textarea>" +
          '<div class="exp-noticias"><h5>Notícias relacionadas</h5>' + noticiasHtml + "</div>" +
          eventosHtml +
          '<div class="exp-links">' +
          '<a href="' + tvUrl + '" target="_blank" rel="noopener">Ver gráfico na TradingView →</a>' +
          (obmUrl ? '<a href="' + obmUrl + '" target="_blank" rel="noopener">Ver no OBM →</a>' : "") +
          "</div>" +
          "</div>"
        );
      }).join("") +
      "</div>";

    montarCotacoes(lista);

    container.querySelectorAll("[data-remover]").forEach(function (btn) {
      btn.addEventListener("click", function () { removerAtivo(btn.getAttribute("data-remover")); });
    });
    container.querySelectorAll("[data-remover-tag]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ticker = btn.getAttribute("data-ticker");
        var tag = btn.getAttribute("data-remover-tag");
        var lista = carregarLista();
        var item = lista.filter(function (i) { return i.ticker === ticker; })[0];
        if (!item) return;
        item.tags = (item.tags || []).filter(function (t) { return t !== tag; });
        salvarLista(lista);
        renderizarLista();
      });
    });
    container.querySelectorAll("[data-add-tag]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ticker = btn.getAttribute("data-add-tag");
        var tag = window.prompt("Nome da tag (ex: tese longa, especulativo, dividendos):");
        if (!tag) return;
        tag = tag.trim();
        if (!tag) return;
        var lista = carregarLista();
        var item = lista.filter(function (i) { return i.ticker === ticker; })[0];
        if (!item) return;
        item.tags = item.tags || [];
        if (item.tags.indexOf(tag) === -1) item.tags.push(tag);
        salvarLista(lista);
        renderizarLista();
      });
    });
    container.querySelectorAll("[data-observacao]").forEach(function (textarea) {
      textarea.addEventListener("blur", function () {
        var ticker = textarea.getAttribute("data-observacao");
        var lista = carregarLista();
        var item = lista.filter(function (i) { return i.ticker === ticker; })[0];
        if (!item) return;
        item.observacao = textarea.value;
        salvarLista(lista);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Noticias (mesmo feed que o Terminal usa)
  // ---------------------------------------------------------------------

  function carregarNoticias() {
    fetch("dados-terminal.html")
      .then(function (resp) { return resp.ok ? resp.text() : ""; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var cards = doc.querySelectorAll("#feed-grid .card");
        var todas = [];
        cards.forEach(function (card) {
          var titulo = card.querySelector("h3");
          var fonte = card.querySelector(".src");
          var link = card.querySelector("a.read");
          todas.push({
            titulo: titulo ? titulo.textContent.trim() : "",
            fonte: fonte ? fonte.textContent.trim() : "",
            href: link ? link.getAttribute("href") : "#",
          });
        });
        NOTICIAS = todas;
        renderizarLista();
      })
      .catch(function () {
        // Sem noticias disponiveis agora - a lista ainda funciona, so
        // sem a secao de noticias relacionadas populada.
      });
  }

  // Eventos do calendario (mesma fonte real do Calendario) - ver
  // eventosRelacionados() acima.
  function carregarEventosCalendario() {
    fetch("eventos_radar.json")
      .then(function (resp) { return resp.ok ? resp.json() : []; })
      .then(function (eventos) {
        EVENTOS_CALENDARIO = Array.isArray(eventos) ? eventos : [];
        renderizarLista();
      })
      .catch(function () {
        // Sem eventos_radar.json disponivel agora - a lista ainda
        // funciona, so sem a secao de eventos relacionados populada.
      });
  }

  function inicializarOrdenacao() {
    var select = document.getElementById("exp-ordenar");
    if (!select) return;
    try {
      select.value = localStorage.getItem(ORDENAR_STORAGE_KEY) || "recentes";
    } catch (e) {
      select.value = "recentes";
    }
    select.addEventListener("change", function () {
      try {
        localStorage.setItem(ORDENAR_STORAGE_KEY, select.value);
      } catch (e) {
        // localStorage indisponivel - ordenacao ainda funciona nesta visita
      }
      renderizarLista();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    inicializarBusca();
    inicializarOrdenacao();
    renderizarLista();
    carregarNoticias();
    carregarEventosCalendario();
  });
})();
