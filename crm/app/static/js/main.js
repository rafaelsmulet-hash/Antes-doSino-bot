// JS proprio, sem dependencia externa (nenhum CDN, nenhuma chamada de rede).

document.addEventListener("DOMContentLoaded", () => {
  const filtro = document.querySelector("[data-filtro-tabela]");
  if (filtro) {
    filtro.addEventListener("input", () => {
      const termo = filtro.value.trim().toLowerCase();
      const tabela = document.querySelector(filtro.dataset.filtroTabela);
      if (!tabela) return;
      tabela.querySelectorAll("tbody tr").forEach((linha) => {
        linha.style.display = linha.textContent.toLowerCase().includes(termo) ? "" : "none";
      });
    });
  }

  document.querySelectorAll("[data-tabs]").forEach((container) => {
    const botoes = Array.from(container.querySelectorAll("[data-tab-target]"));
    const paineis = Array.from(container.querySelectorAll("[data-tab-panel]"));
    const ativar = (alvo) => {
      botoes.forEach((b) => b.classList.toggle("ativo", b.dataset.tabTarget === alvo));
      paineis.forEach((p) => {
        p.style.display = p.dataset.tabPanel === alvo ? "" : "none";
      });
    };
    botoes.forEach((botao) => {
      botao.addEventListener("click", () => ativar(botao.dataset.tabTarget));
    });
    if (botoes.length) {
      ativar(botoes[0].dataset.tabTarget);
    }
  });
});
