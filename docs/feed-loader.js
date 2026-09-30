/**
 * Carregador do feed de noticias paginado - Antes do Sino
 * ===========================================================
 * Substitui o antigo padrao de fetch("dados-terminal.html") + DOMParser
 * + querySelectorAll(".card") (usado antes por terminal.js/radar.js/
 * exposicao.js) por docs/feed/manifesto.json + docs/feed/pagina-N.json
 * (main.py::export_feed_json) - mesmo dado, So como JSON estruturado
 * em vez de HTML repetitivo (~285KB pra 150 itens antes).
 *
 * Compartilhado pelas 3 paginas que precisam do feed, pra nao
 * triplicar a logica de paginacao/timeout/erro.
 */
(function () {
  "use strict";

  function fetchComTimeout(url, timeoutMs) {
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, timeoutMs || 8000);
    return fetch(url, { signal: controller.signal }).finally(function () {
      clearTimeout(timeoutId);
    });
  }

  /**
   * Carrega o feed pagina por pagina.
   *
   * onPagina(itensDaPagina, numeroDaPagina, totalDePaginas, todosOsItensAteAgora):
   *   chamado a cada pagina que chega, na ordem (1a primeiro) - quem
   *   consome pode renderizar so com a pagina 1 pra nao esperar o
   *   universo inteiro (a pagina 1 ja traz as noticias mais recentes/
   *   prioritarias, ver export_feed_json em main.py).
   * onCompleto(todosOsItens): chamado uma vez, depois que TODAS as
   *   paginas chegaram - usado por quem precisa buscar em qualquer
   *   noticia (ex: Ctrl+K do Terminal, correlacao de ativos da Minha
   *   Exposicao), nao so nas mais recentes.
   * onErro(erro): manifesto nao encontrado/travou - feed inteiro
   *   indisponivel (nunca finge que ha dado quando nao ha).
   */
  function carregarFeedPaginado(onPagina, onCompleto, onErro) {
    fetchComTimeout("feed/manifesto.json", 8000)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (manifesto) {
        var totalPaginas = manifesto.paginas || 0;
        if (totalPaginas === 0) {
          if (onCompleto) onCompleto([]);
          return;
        }
        var todos = [];
        function carregarPagina(numero) {
          fetchComTimeout("feed/pagina-" + numero + ".json", 8000)
            .then(function (r) { return r.ok ? r.json() : []; })
            .catch(function () { return []; }) // 1 pagina especifica falhou - segue pras proximas em vez de travar tudo
            .then(function (itensDaPagina) {
              todos = todos.concat(itensDaPagina);
              if (onPagina) onPagina(itensDaPagina, numero, totalPaginas, todos);
              if (numero < totalPaginas) {
                carregarPagina(numero + 1);
              } else if (onCompleto) {
                onCompleto(todos);
              }
            });
        }
        carregarPagina(1);
      })
      .catch(function (erro) {
        if (onErro) onErro(erro);
      });
  }

  window.AntesDoSinoFeed = { carregarFeedPaginado: carregarFeedPaginado };
})();
