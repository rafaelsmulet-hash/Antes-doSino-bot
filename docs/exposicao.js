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
  var universo = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.STOCK_UNIVERSE) || [];
  var universoCripto = (window.AntesDoSinoUniverso && window.AntesDoSinoUniverso.CRYPTO_UNIVERSE) || [];
  var TODOS_ATIVOS = universo.concat(universoCripto);

  var NOTICIAS = []; // preenchido pelo fetch de dados-terminal.html

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

  function renderizarLista() {
    var container = document.getElementById("exp-list-container");
    if (!container) return;
    var lista = carregarLista();

    if (!lista.length) {
      container.innerHTML = '<div class="exp-empty">Você ainda não adicionou nenhum ativo. Busque acima pra começar a acompanhar.</div>';
      return;
    }

    container.innerHTML =
      '<div class="exp-list">' +
      lista.map(function (item) {
        var relacionadas = noticiasRelacionadas(item);
        var tagsHtml = (item.tags || []).map(function (tag) {
          return '<span class="exp-tag">' + escapeHtml(tag) + '<button type="button" data-remover-tag="' + escapeHtml(tag) + '" data-ticker="' + escapeHtml(item.ticker) + '">✕</button></span>';
        }).join("");

        var noticiasHtml = relacionadas.length
          ? relacionadas.map(function (n) {
              return '<div class="exp-noticia-item"><a href="' + escapeHtml(n.href) + '" target="_blank" rel="noopener">' + escapeHtml(n.titulo) + '</a><span class="src">' + escapeHtml(n.fonte) + "</span></div>";
            }).join("")
          : '<p class="exp-sem-noticias">Nenhuma notícia recente do nosso feed menciona esse ativo.</p>';

        var tvUrl = "https://www.tradingview.com/symbols/" + item.symbol.replace(":", "-") + "/";
        var obmUrl = item.symbol.indexOf("BMFBOVESPA:") === 0 ? "https://obm.com.br/acoes/" + item.ticker.toLowerCase() : null;

        return (
          '<div class="exp-card" data-ticker="' + escapeHtml(item.ticker) + '">' +
          '<div class="exp-card-head">' +
          "<div><span class=\"ticker\">" + escapeHtml(item.ticker) + '</span><span class="nome">' + escapeHtml(item.nome) + "</span></div>" +
          '<button type="button" class="exp-remove-btn" data-remover="' + escapeHtml(item.ticker) + '" title="Remover da lista">✕ Remover</button>' +
          "</div>" +
          '<div class="exp-tags">' + tagsHtml + '<button type="button" class="exp-tag-add" data-add-tag="' + escapeHtml(item.ticker) + '">+ tag</button></div>' +
          '<textarea class="exp-obs" data-observacao="' + escapeHtml(item.ticker) + '" placeholder="Sua observação sobre esse ativo (tese, motivo de acompanhar, etc.)">' + escapeHtml(item.observacao || "") + "</textarea>" +
          '<div class="exp-noticias"><h5>Notícias relacionadas</h5>' + noticiasHtml + "</div>" +
          '<div class="exp-links">' +
          '<a href="' + tvUrl + '" target="_blank" rel="noopener">Ver gráfico na TradingView →</a>' +
          (obmUrl ? '<a href="' + obmUrl + '" target="_blank" rel="noopener">Ver no OBM →</a>' : "") +
          "</div>" +
          "</div>"
        );
      }).join("") +
      "</div>";

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

  document.addEventListener("DOMContentLoaded", function () {
    inicializarBusca();
    renderizarLista();
    carregarNoticias();
  });
})();
