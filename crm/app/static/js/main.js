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
});
