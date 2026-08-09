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
 */
(function () {
  var CHAVE = 'antes-do-sino-tema';

  function temaAtual() {
    var explicito = document.documentElement.getAttribute('data-theme');
    return explicito === 'light' ? 'light' : 'dark';
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute('data-theme', tema);
    try {
      localStorage.setItem(CHAVE, tema);
    } catch (e) {
      // localStorage indisponivel (modo anonimo, etc) - tema ainda
      // funciona nesta visita, so nao persiste pra proxima.
    }
  }

  function inicializar() {
    var botao = document.getElementById('theme-toggle');
    if (!botao) return;
    botao.addEventListener('click', function () {
      var novoTema = temaAtual() === 'light' ? 'dark' : 'light';
      aplicarTema(novoTema);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inicializar);
  } else {
    inicializar();
  }
})();
