/**
 * Antes do Sino - Consentimento de cookies
 * ============================================
 * Arquivo UNICO, incluido em toda pagina no lugar do snippet fixo do
 * GA4 - o Google Analytics so e carregado DEPOIS que o usuario aceitar
 * explicitamente. Sem escolha salva, nenhum cookie de terceiro e
 * carregado e a faixa de consentimento aparece (uma vez por
 * navegador, escolha guardada em localStorage). Recusar nunca afeta
 * nenhuma funcionalidade do site - GA4 e so estatistica de uso.
 */
(function () {
  "use strict";

  var GA_MEASUREMENT_ID = "G-KKJKKZB9QG";
  var STORAGE_KEY = "antes-do-sino-consentimento";

  function obterEscolha() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function salvarEscolha(valor) {
    try {
      localStorage.setItem(STORAGE_KEY, valor);
    } catch (e) {
      /* localStorage indisponivel (modo privado, etc) - segue sem persistir */
    }
  }

  function carregarGoogleAnalytics() {
    if (window.__antesDoSinoGACarregado) return;
    window.__antesDoSinoGACarregado = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () {
      window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", GA_MEASUREMENT_ID);
    var script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_MEASUREMENT_ID;
    document.head.appendChild(script);
  }

  function removerFaixa() {
    var faixa = document.getElementById("cookie-consent-banner");
    if (faixa) faixa.remove();
  }

  function aceitar() {
    salvarEscolha("aceito");
    carregarGoogleAnalytics();
    removerFaixa();
  }

  function recusar() {
    salvarEscolha("recusado");
    removerFaixa();
  }

  function montarFaixa() {
    if (document.getElementById("cookie-consent-banner")) return;
    var faixa = document.createElement("div");
    faixa.id = "cookie-consent-banner";
    faixa.setAttribute("role", "dialog");
    faixa.setAttribute("aria-live", "polite");
    faixa.setAttribute("aria-label", "Consentimento de cookies");
    faixa.innerHTML =
      "<p>Usamos cookies de estatística de uso (Google Analytics) só para entender quais páginas são mais acessadas — nunca para anúncio, venda de dado ou perfil de comportamento. " +
      'Recusar não tira nenhuma função do site. <a href="cookies.html">Saiba mais</a>.</p>' +
      '<div class="cookie-consent-botoes">' +
      '<button type="button" id="cookie-consent-recusar">Recusar</button>' +
      '<button type="button" id="cookie-consent-aceitar">Aceitar</button>' +
      "</div>";
    document.body.appendChild(faixa);
    document.getElementById("cookie-consent-aceitar").addEventListener("click", aceitar);
    document.getElementById("cookie-consent-recusar").addEventListener("click", recusar);
  }

  function iniciar() {
    var escolha = obterEscolha();
    if (escolha === "aceito") {
      carregarGoogleAnalytics();
    } else if (escolha === "recusado") {
      // nada a fazer - usuario ja recusou antes, nao mostra a faixa de novo
    } else {
      montarFaixa();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  // Exposto globalmente para a pagina de Cookies (docs/cookies.html)
  // permitir trocar a escolha depois de ja feita.
  window.AntesDoSinoConsentimento = {
    aceitar: aceitar,
    recusar: recusar,
    escolhaAtual: obterEscolha,
    mostrarFaixaDeNovo: montarFaixa,
  };
})();
