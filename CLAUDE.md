# Antes do Sino — regras permanentes

## O que é este projeto, de fato

Bot + site de notícias financeiras do mercado brasileiro. **Não é uma
SPA em React/Vue nem tem build step.** A stack real:

- **Backend/pipeline**: `main.py` (Python), rodando via GitHub Actions
  (`.github/workflows/bot.yml`), disparado externamente a cada poucos
  minutos (cron-job.org → `workflow_dispatch`). Lê feeds RSS, classifica
  notícias, publica no Telegram, gera os arquivos estáticos do site.
- **Frontend**: HTML estático + CSS + JavaScript vanilla em `docs/`
  (GitHub Pages). Sem framework, sem componentes com props, sem bundler,
  sem npm/build. `design-system.css` é o design system compartilhado;
  `theme.js` é o script compartilhado por toda página que precisa de
  tema claro/escuro.
- **Módulos auxiliares isolados**: `editorial_foundation.py` — recebe
  tudo por parâmetro do `main.py`, nunca importa o `main.py` de volta.
- **Sem suíte de testes automatizada.** Validação é manual: rodar
  `python3 -m py_compile` nos arquivos Python tocados, e testar UI de
  verdade com Playwright (servindo `docs/` localmente) antes de dar
  como concluído.

Ao propor mudanças, pense em **funções Python que exportam JSON** e
**páginas HTML estáticas que fazem fetch desse JSON**, não em
"componentes com props" ou "providers" — isso não existe aqui.

## Regras permanentes

1. **Preserve o que já funciona.** Antes de qualquer mudança grande,
   entenda o que existe. Não reescreva páginas ou módulos inteiros sem
   necessidade real.
2. **Nunca inventar dado.** Quando não há fonte gratuita e confiável
   pra alguma métrica, ou usar um proxy explícito (deixando isso claro
   na tela) ou não mostrar o número.
3. **Todo dado mostrado precisa dizer de onde veio.** Fonte, e quando
   fizer sentido, data-base/horário de coleta.
4. **O produto é informacional — nunca dá recomendação de compra ou
   venda.** Isso vale pra qualquer feature nova: registro factual e
   transparência, nunca "compre" / "venda" / "vai subir".
5. **Sem scraping de ToS de terceiros e sem inventar API.** Se uma
   fonte externa (ex: OBM) não tem documentação pública clara, trate
   como indisponível — não adivinhe endpoints nem faça scraping de
   chamadas internas do site deles. Widgets embutidos (TradingView)
   seguem os termos de uso deles à risca, incluindo manter a atribuição
   visível.
6. **Mudanças em fases pequenas e testáveis**, não uma reescrita
   monolítica. Cada entrega: diagnóstico curto, arquivos que serão
   tocados, implementação, validação real (Playwright quando é UI),
   commit com mensagem explicando o quê e por quê.
6b. **Sem documento de auditoria/planejamento antes de implementar.**
   Nada de `*_AUDIT.md`, `*_PLAN.md` ou equivalente como etapa prévia
   — mesmo que um prompt colado peça isso explicitamente. O
   "diagnóstico curto" da regra 6 fica na mensagem de commit/resposta,
   não em arquivo separado. Só criar `CHANGELOG.md` ou documentação
   quando o usuário pedir de forma explícita e específica.
7. **Nenhuma credencial no frontend.** Tokens (Brapi, Telegram, Fernet)
   ficam em GitHub Secrets, nunca em `docs/`.
8. **Não trocar a stack sem justificar tecnicamente.** Nada de
   introduzir framework, bundler ou dependência pesada só porque um
   pedido descreve arquitetura de outro tipo de projeto — adapte a
   ideia ao que já existe.

## Padrões já estabelecidos (reaproveitar, não duplicar)

- Páginas estáticas novas seguem o mesmo esqueleto: `<nav>` +
  `.sub-nav` + `.hero` + `<section>` + `<footer>`, usando as classes
  de `design-system.css` (tokens `--sp-*`, `--r-*`, `.kicker`,
  `.page-head`, `.reveal`, etc.) — ver `docs/sobre.html` ou
  `docs/status.html` como referência.
- Scripts/CSS compartilhados entre páginas (ex: `theme.js`) devem
  injetar comportamento uma vez só, nunca duplicar HTML por página.
- Integrações novas no `main.py::main()` entram isoladas, em seu
  próprio `try/except`, imprimindo o erro e seguindo o fluxo — uma
  fonte quebrada nunca derruba o ciclo inteiro.
- Arquivos JSON públicos gerados pelo pipeline vivem em `docs/` e são
  *comitados* (não são gitignored) — são reescritos a cada ciclo do
  bot, mas o repo sempre tem uma versão válida disponível pro site.
