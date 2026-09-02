# Antes do Sino — Auditoria visual (Fase 0)

_Baseada em trabalho direto no código desta sessão — não é uma
inspeção às cegas. O redesign "Apple" (tipografia, espaçamento,
navegação) e os passes de polimento subsequentes já resolveram parte
da lista de sintomas comuns de "site gerado por IA". Este documento
separa o que já foi endereçado do que é problema real hoje._

## O que foi verificado, sintoma por sintoma

| Sintoma | Aplica hoje? | Nota |
|---|---|---|
| Cards visualmente semelhantes | **Sim** | Os 4 painéis do grid principal do Terminal (Índices/Moedas/Emergentes/Commodities) têm exatamente o mesmo tamanho, borda e peso tipográfico, independente de importância editorial |
| Muitos blocos com o mesmo peso visual | **Sim**, mesmo ponto | Não existe hoje uma distinção visual entre "o que importa agora" (ex: alerta de alta materialidade) e "o que é exploratório" (ex: curva DI de 11 pontos) |
| Excesso de cantos arredondados | Parcial | `--r-md`/`--r-lg` usados de forma uniforme quase em tudo, sem variação de tratamento por importância |
| Aparência de dashboard genérico | Parcial | O grid de cotação tem DNA de template; a Home como um todo é densa (não é uma landing esparsa), mas falta hierarquia dentro da densidade |
| Ausência de indicador de estado do mercado | **Sim, gap real** | Não existe hoje nenhum indicador de "mercado aberto/fechado" — informação básica de um terminal financeiro |
| Metadados de fonte/frescor inconsistentes | **Sim, gap real** | Cada página que mostra proxy/fonte faz isso com um texto solto e estilo próprio (ex: disclaimer do Fluxo Estrangeiro, badges "Tempo real" do Status) — sem um padrão visual único reutilizável |
| Tom de texto artificial/marketing | **Não** | Copy já auditado (heros, `sobre.html`, `status.html`): direto, sóbrio, sem "descubra o futuro" ou frases de vendedor — já era princípio antes deste pedido |
| Gradientes/glassmorphism sem função | **Não** | O blur existente (drawer de personalização, modal Ctrl+K, Contexto do Ativo) separa camada sobreposta do conteúdo por baixo — funcional, não decorativo |
| Ícone dentro de quadrado colorido em todo card | **Não** | Painéis do Terminal não usam esse padrão; ícones aparecem em contexto (nav, badges de status) |
| Gráficos falsos/ornamentais | **Não** | Todo gráfico do produto é um widget real da TradingView com dado ao vivo — nunca um SVG decorativo fingindo ser gráfico |
| Componentes "perfeitos demais", sem densidade | **Não** | O Terminal já é denso (múltiplos painéis + sidebar de feed simultâneos), oposto do problema descrito |
| Texto centralizado em excesso | Parcial | Heros das páginas estáticas (Sobre, Status, Calendário etc.) são centralizados — aceitável nesse contexto de página institucional, mas o Terminal em si não sofre disso |

## Diagnóstico

O problema real **não é** "estética de IA" de forma genérica — boa
parte da lista (tom de marketing, decoração vazia, gráficos falsos,
mascote de IA) já não existe neste produto. Os dois problemas
concretos e que valem esforço de redesign são:

1. **Hierarquia plana**: todo painel do Terminal pesa igual. Não há
   como o olho identificar em 2 segundos "o que é essencial agora" vs
   "o que é pra explorar depois".
2. **Metadados sem padrão**: fonte, frescor, proxy e status de mercado
   aparecem de formas diferentes em cada tela, quando aparecem.

## Escopo do redesign

**Fase 1 — Fundação**: tokens que faltam (estado de mercado, aviso,
info, dado obsoleto) + um punhado de padrões de metadado reutilizáveis
(fonte, frescor, proxy, status de mercado) em `design-system.css`,
documentados em `DESIGN_SYSTEM.md`.

**Fase 2 — Terminal**: reorganizar os painéis em 3 níveis de
prioridade visual (agora / atenção / aprofundar), adicionar indicador
de sessão de mercado no header, aplicar os metadados da Fase 1 onde já
existiam informalmente (Contexto Macro, VIX, Ativos em Destaque).

**Fase 3 — Feed de notícias**: diferenciar visualmente alerta
principal, destaques e radar dentro da coluna de notícias — hoje todo
item tem o mesmo peso.

**Fase 4 — Páginas secundárias**: aplicar os componentes de metadado
da Fase 1 em Calendário, Mapa de Calor, Quant, Sobre e Status, sem
redesenhar a estrutura de cada uma (elas não têm o problema de
hierarquia do Terminal).

**Fase 5 — Refinamento**: validar mobile, tema claro/escuro, estados
vazio/erro/carregando.

## O que NÃO entra no escopo

- Trocar a paleta de cor (navy + dourado já é uma assinatura própria,
  já pedida e validada em sessões anteriores — não é o padrão genérico
  "navy + azul + verde neon" que o pedido original alertava contra).
- Trocar a tipografia (sans-serif de sistema + mono pra números já
  está estabelecido e funciona).
- Reescrever copy — já auditado, já está no tom certo.
- Diário de Decisão — removido do produto a pedido do usuário antes
  deste redesign; não será recriado nem redesenhado.
