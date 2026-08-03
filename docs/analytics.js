/**
 * Antes do Sino - Camada de eventos GA4
 * =========================================
 * Arquivo UNICO, reaproveitado em todas as paginas (home, planos, e
 * as paginas geradas dinamicamente pelo bot). Nao duplica logica.
 *
 * O que faz:
 * 1. Preserva parametros UTM durante a navegacao interna (sem isso,
 *    o GA4 perde a origem original ao mudar de pagina no mesmo site).
 * 2. Dispara eventos padronizados via delegacao de clique - funciona
 *    automaticamente pra botoes adicionados no futuro, sem precisar
 *    editar este arquivo.
 * 3. Evita disparo duplicado do mesmo evento.
 * 4. Loga no console quando o modo debug estiver ativo.
 *
 * Como ativar o modo debug: adicionar ?ga_debug=1 na URL, ou rodar
 * no console do navegador: localStorage.setItem('ads_debug', '1')
 */
(function () {
  "use strict";

  var UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  var STORAGE_KEY = "ads_utm_params";
  var EVENTOS_JA_DISPARADOS = {};
  var JANELA_DEDUPE_MS = 800;

  function debugAtivo() {
    try {
      var urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get("ga_debug") === "1") {
        localStorage.setItem("ads_debug", "1");
      }
      return localStorage.getItem("ads_debug") === "1";
    } catch (e) {
      return false;
    }
  }

  function logDebug(mensagem, dados) {
    if (debugAtivo()) {
      console.log("[Antes do Sino - Analytics] " + mensagem, dados || "");
    }
  }

  // ---------------------------------------------------------------
  // 1) Preservacao de UTM entre paginas internas
  // ---------------------------------------------------------------

  function capturarUtmDaUrl() {
    var params = new URLSearchParams(window.location.search);
    var capturados = {};
    var encontrouAlgum = false;
    UTM_KEYS.forEach(function (chave) {
      var valor = params.get(chave);
      if (valor) {
        capturados[chave] = valor;
        encontrouAlgum = true;
      }
    });
    if (encontrouAlgum) {
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(capturados));
        logDebug("UTM capturado da URL e salvo na sessao:", capturados);
      } catch (e) {
        /* sessionStorage indisponivel (modo privado, etc) - segue sem persistir */
      }
    }
    return capturados;
  }

  function obterUtmDaSessao() {
    try {
      var salvo = sessionStorage.getItem(STORAGE_KEY);
      return salvo ? JSON.parse(salvo) : {};
    } catch (e) {
      return {};
    }
  }

  function eLinkInterno(link) {
    try {
      var url = new URL(link.href, window.location.href);
      return url.hostname === window.location.hostname;
    } catch (e) {
      return false;
    }
  }

  function propagarUtmParaLinksInternos(utm) {
    if (!utm || Object.keys(utm).length === 0) return;

    var links = document.querySelectorAll("a[href]");
    links.forEach(function (link) {
      if (!eLinkInterno(link)) return;
      try {
        var url = new URL(link.href, window.location.href);
        var mudou = false;
        UTM_KEYS.forEach(function (chave) {
          if (utm[chave] && !url.searchParams.has(chave)) {
            url.searchParams.set(chave, utm[chave]);
            mudou = true;
          }
        });
        if (mudou) {
          link.href = url.toString();
        }
      } catch (e) {
        /* href malformado ou relativo estranho - ignora esse link */
      }
    });
  }

  // ---------------------------------------------------------------
  // 2) Disparo de evento padronizado (funcao reutilizavel)
  // ---------------------------------------------------------------

  function dispararEvento(nomeEvento, parametros) {
    parametros = parametros || {};

    // Anti-duplicidade: mesmo evento + mesmo destino, disparado de
    // novo numa janela curta de tempo, e ignorado.
    var chaveDedupe = nomeEvento + "::" + (parametros.link_url || parametros.destino || "");
    var agora = Date.now();
    if (EVENTOS_JA_DISPARADOS[chaveDedupe] && (agora - EVENTOS_JA_DISPARADOS[chaveDedupe]) < JANELA_DEDUPE_MS) {
      logDebug("Evento ignorado (duplicado dentro da janela de " + JANELA_DEDUPE_MS + "ms):", nomeEvento);
      return;
    }
    EVENTOS_JA_DISPARADOS[chaveDedupe] = agora;

    var utm = obterUtmDaSessao();
    var parametrosCompletos = Object.assign({}, utm, parametros);

    if (typeof window.gtag === "function") {
      window.gtag("event", nomeEvento, parametrosCompletos);
    }

    logDebug("Evento disparado: " + nomeEvento, parametrosCompletos);
  }

  // ---------------------------------------------------------------
  // 3) Classificacao automatica de clique (delegacao - funciona pra
  //    elementos adicionados no futuro, sem precisar editar este
  //    arquivo nem marcar cada botao manualmente)
  // ---------------------------------------------------------------

  function textoNormalizado(elemento) {
    return (elemento.textContent || "").trim().toLowerCase();
  }

  function classificarEDispararClique(elementoLink) {
    var href = elementoLink.href || "";
    var texto = textoNormalizado(elementoLink);
    var parametrosBase = { link_url: href, link_text: elementoLink.textContent.trim() };

    var ehLinkTelegram = href.indexOf("t.me/") !== -1;

    if (ehLinkTelegram) {
      dispararEvento("click_telegram_link", parametrosBase);

      if (texto.indexOf("assinar") !== -1) {
        dispararEvento("click_cta_assinar", parametrosBase);
      } else if (texto.indexOf("conhecer o telegram") !== -1 || texto.indexOf("entrar no grupo") !== -1) {
        dispararEvento("click_cta_conhecer_telegram", parametrosBase);
      }
    }

    if (elementoLink.classList && elementoLink.classList.contains("btn-primary")) {
      dispararEvento("click_cta_principal", parametrosBase);
    }

    if (href.indexOf("planos.html") !== -1) {
      dispararEvento("click_nav_planos", parametrosBase);
    }
  }

  function inicializarDelegacaoDeClique() {
    document.addEventListener("click", function (evento) {
      var elementoLink = evento.target.closest ? evento.target.closest("a[href]") : null;
      if (!elementoLink) return;
      classificarEDispararClique(elementoLink);
    });
  }

  // ---------------------------------------------------------------
  // Inicializacao
  // ---------------------------------------------------------------

  function iniciar() {
    var utmDaUrl = capturarUtmDaUrl();
    var utmVigente = Object.keys(utmDaUrl).length > 0 ? utmDaUrl : obterUtmDaSessao();
    propagarUtmParaLinksInternos(utmVigente);
    inicializarDelegacaoDeClique();
    logDebug("Camada de analytics inicializada. UTM vigente:", utmVigente);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  // Exposto globalmente para permitir disparo manual de eventos
  // customizados no futuro, sem precisar editar este arquivo.
  window.AntesDoSinoAnalytics = {
    dispararEvento: dispararEvento,
  };
})();
