/**
 * Alternador de tema claro/escuro - compartilhado por todas as
 * paginas do site (Terminal, Calendario, Mapa de Calor, Quant).
 *
 * O tema NAO segue prefers-color-scheme automaticamente de proposito
 * - o produto e escuro por padrao (identidade visual estabelecida) e
 * so muda quando o usuario clica no botao, exatamente como foi
 * pedido. A escolha fica salva no localStorage e e reaplicada em
 * visitas futuras.
 *
 * A deteccao/aplicacao do tema salvo roda ANTES deste arquivo, num
 * script inline sincrono no <head> de cada pagina (evita o "flash" de
 * tema errado antes do CSS carregar) - este arquivo so cuida da
 * interacao (clique no botao) depois que a pagina carrega.
 *
 * Expoe window.AntesDoSinoTema.atual() e dispara o evento
 * 'ads:tema-mudou' no document a cada troca - os widgets da
 * TradingView tem cor propria (colorTheme "dark"/"light") que nao
 * segue o CSS da pagina, entao cada pagina escuta esse evento pra
 * reconstruir os widgets no tema certo (ver terminal.js e os scripts
 * de calendario/mapa/quant.html).
 *
 * window.AntesDoSinoTema.montarWidgetTV(...) monta um widget publico
 * da TradingView (mesmo padrao usado no Terminal) a partir do tema
 * atual - helper compartilhado pra nao duplicar esse bloco de HTML/JS
 * em calendario.html, mapa.html e quant.html.
 */
(function () {
  var CHAVE = 'antes-do-sino-tema';
  var EVENTO = 'ads:tema-mudou';

  function temaAtual() {
    var explicito = document.documentElement.getAttribute('data-theme');
    return explicito === 'light' ? 'light' : 'dark';
  }

  // Sessao regular da B3: seg-sex, 10h-17h horario de Brasilia. Usa
  // Intl com timeZone explicito em vez de confiar no fuso do
  // navegador (visitante pode estar em qualquer lugar do mundo).
  // Simplificado de proposito - nao cobre feriados nem after-market;
  // e um indicador visual rapido, nao uma fonte de horario de
  // negociacao (isso continua sendo responsabilidade da B3/corretora).
  function statusMercado() {
    var partes = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Sao_Paulo', hour12: false,
      weekday: 'short', hour: '2-digit', minute: '2-digit',
    }).formatToParts(new Date());
    var mapa = {};
    partes.forEach(function (p) { mapa[p.type] = p.value; });
    var diaUtil = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].indexOf(mapa.weekday) !== -1;
    var minutos = parseInt(mapa.hour, 10) * 60 + parseInt(mapa.minute, 10);
    var aberto = diaUtil && minutos >= 10 * 60 && minutos < 17 * 60;
    return { aberto: aberto, texto: aberto ? 'B3 aberta' : 'B3 fechada' };
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute('data-theme', tema);
    try {
      localStorage.setItem(CHAVE, tema);
    } catch (e) {
      // localStorage indisponivel (modo anonimo, etc) - tema ainda
      // funciona nesta visita, so nao persiste pra proxima.
    }
    document.dispatchEvent(new CustomEvent(EVENTO, { detail: { tema: tema } }));
  }

  function inicializar() {
    var botao = document.getElementById('theme-toggle');
    if (botao) {
      botao.addEventListener('click', function () {
        var novoTema = temaAtual() === 'light' ? 'dark' : 'light';
        aplicarTema(novoTema);
      });
    }
    criarBotaoFeedback();
  }

  // Botao flutuante de feedback (ver .feedback-float no design-system.css)
  // - inspirado no obm.com.br. Injetado aqui, uma vez so, em vez de
  // duplicar o HTML em cada pagina que carrega theme.js.
  function criarBotaoFeedback() {
    if (document.querySelector('.feedback-float')) return;
    var link = document.createElement('a');
    link.href = 'https://t.me/+TobMzw-WnQhmZmIx';
    link.target = '_blank';
    link.rel = 'noopener';
    link.className = 'feedback-float';
    link.title = 'Sugestões e feedback';
    link.setAttribute('aria-label', 'Sugestões e feedback');
    link.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>' +
      '</svg><span>Sugestões e feedback</span>';
    document.body.appendChild(link);
  }

  // Estado de erro (ver .widget-error-state no design-system.css) -
  // mesmo padrao usado em terminal.js::montarEstadoErro, duplicado
  // aqui de proposito (theme.js roda em mais paginas que nao carregam
  // terminal.js - Calendario, Mapa, Quant - entao nao da pra
  // reaproveitar a funcao de la sem criar uma dependencia entre os
  // dois arquivos so por causa disso).
  function montarEstadoErroWidget(container, tentarNovamente) {
    if (!container) return;
    container.innerHTML =
      '<div class="widget-error-state">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>' +
      '<p>Não foi possível carregar este painel agora. Pode ser um bloqueador de anúncios, instabilidade de rede, ou a TradingView fora do ar.</p>' +
      '<button type="button" class="widget-retry-btn">Tentar novamente</button>' +
      '</div>';
    var botao = container.querySelector('.widget-retry-btn');
    if (botao) botao.addEventListener('click', tentarNovamente);
  }

  // containerId: id do elemento onde o widget entra. src: URL do
  // script de embed da TradingView. configBuilder: funcao que recebe
  // o tema atual ("dark"/"light") e devolve o objeto de configuracao
  // do widget (mesmo JSON que iria dentro do <script>...</script> no
  // embed estatico da TradingView).
  function montarWidgetTV(containerId, src, configBuilder) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    var wrapper = document.createElement('div');
    wrapper.className = 'tradingview-widget-container';
    wrapper.style.height = '100%';
    wrapper.style.width = '100%';

    var widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    wrapper.appendChild(widgetDiv);

    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = src;
    script.async = true;
    script.text = JSON.stringify(configBuilder(temaAtual()));
    script.onerror = function () {
      montarEstadoErroWidget(container, function () { montarWidgetTV(containerId, src, configBuilder); });
    };

    wrapper.appendChild(script);
    container.appendChild(wrapper);
  }

  // Monta o badge de status de mercado (.market-status, ver
  // design-system.css) num container - helper compartilhado pra nao
  // duplicar o HTML/logica em cada pagina que quiser mostrar isso.
  // Reatualiza a cada minuto (sem custo real - so calculo de horario).
  function montarMarketStatus(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;
    function render() {
      var status = statusMercado();
      container.innerHTML =
        '<span class="market-status ' + (status.aberto ? 'open' : 'closed') + '">' +
        '<span class="dot"></span>' + status.texto + '</span>';
    }
    render();
    setInterval(render, 60000);
  }

  window.AntesDoSinoTema = {
    atual: temaAtual, EVENTO: EVENTO, montarWidgetTV: montarWidgetTV,
    statusMercado: statusMercado, montarMarketStatus: montarMarketStatus,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inicializar);
  } else {
    inicializar();
  }
})();
