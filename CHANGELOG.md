# Antes do Sino — Changelog

## Redesign editorial (5 fases)

Resposta ao pedido de redesenhar a identidade visual pra sair do
padrão "genérico de IA". Auditado primeiro (`DESIGN_AUDIT.md`) — boa
parte da lista de sintomas comuns já não se aplicava a este produto,
resolvido em passes anteriores da mesma sessão. Dois problemas reais
guiaram o trabalho: hierarquia plana (todo painel/notícia pesava
igual) e metadados de fonte/frescor sem padrão único.

- **Fase 0** — `DESIGN_AUDIT.md`: auditoria sintoma-a-sintoma.
- **Fase 1** — Fundação: tokens semânticos novos (`--warning`,
  `--info`, `--market-open`, `--market-closed`, `--stale-data`) e
  componentes de metadado reutilizáveis (`.data-badge`,
  `.meta-source`, `.meta-freshness`, `.proxy-notice`, `.source-link`,
  `.market-status`), documentados em `DESIGN_SYSTEM.md`. Indicador de
  sessão B3 (`theme.js::statusMercado()`). `status.html` refatorado
  pra usar o componente compartilhado em vez de CSS local duplicado.
- **Fase 2** — Terminal: Índices Mundiais vira painel "hero" (banner
  largo no topo, borda dourada); VIX ganha mais peso que Ativos em
  Destaque; badge de sessão de mercado no header; disclaimer do Fluxo
  Estrangeiro migrado pro componente `.proxy-notice`.
- **Fase 3** — Feed de notícias: 3 faixas editoriais reaproveitando a
  ordem que o feed já vem — Alerta principal (resumo sempre visível),
  Destaques (padrão atual), Radar (lista compacta, ponto colorido em
  vez de badge cheio).
- **Fase 4** — Calendário, Mapa de Calor e Quant ganham nota de fonte
  padronizada (`.meta-source`) — antes inexistente ou com estilo
  inline duplicado por página.
- **Fase 5** — Refinamento: varredura completa em todas as páginas
  (tema claro/escuro, sem erro de console) e nos casos-limite do feed
  (0, 1, 3, 6 notícias — nenhuma seção vazia aparece, estado vazio
  correto com 0 itens).

Nada foi removido: personalização, abas, Contexto do Ativo, busca
Ctrl+K, todos os painéis e páginas continuam funcionando exatamente
como antes — só a apresentação mudou.

## Antes deste redesign

- Remoção completa de Carteira de Dividendos e Diário de Decisão
  (módulos, páginas, dados salvos, Cloudflare Worker) a pedido do
  usuário.
- Contexto do Ativo: drawer no Terminal com cotação, notícias
  relacionadas e links de saída (TradingView, OBM).
- Botão de feedback flutuante + página de Status (frescor dos dados).
- Correção de bug de hashtag/ticker por substring simples (matching
  por fronteira de palavra em 4 pontos do pipeline + no Ctrl+K).
- Abas por categoria + leitor de notícia inline no Terminal.
- Curva de juros futuros (DI) estendida até 2037 no Contexto Macro.
