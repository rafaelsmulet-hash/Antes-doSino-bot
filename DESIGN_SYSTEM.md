# Antes do Sino — Design System

Fonte única: `docs/design-system.css` (tokens + componentes
compartilhados) e `docs/theme.js` (interação: tema, status de
mercado, botão de feedback). Toda página nova deve consumir os dois,
nunca redefinir cor/espaço/raio localmente.

## Tokens

### Superfície
| Token | Uso |
|---|---|
| `--navy-deep` | Fundo mais escuro (header, drawers) |
| `--navy` / `--navy-light` | Gradiente de fundo da página |
| `--surface-1` / `--surface-2` | Fundo de painel/card, elevação sutil |
| `--line` / `--line-strong` | Bordas — `strong` só quando a borda precisa se destacar (foco, hover) |
| `--backdrop` | Overlay atrás de modais/drawers |

### Acento (assinatura visual)
| Token | Uso |
|---|---|
| `--gold` / `--gold-soft` / `--bronze` | A cor proprietária do produto — CTA principal, links de fonte, títulos de painel. Não usar em todo componente; ela precisa continuar rara pra funcionar como assinatura |
| `--shadow-gold` | Sombra do CTA principal, só nele |

### Texto
| Token | Uso |
|---|---|
| `--cream` | Texto principal (não é branco puro — leve tom quente) |
| `--slate` | Texto secundário |
| `--slate-dim` | Texto terciário/metadado |

### Semântico
| Token | Uso |
|---|---|
| `--up` / `--down` | Alta/baixa de mercado — **só** pra isso |
| `--warning` | Proxy, estimativa, aviso — nunca pra decoração |
| `--info` | Dado neutro/informativo (não é alta nem baixa) |
| `--market-open` / `--market-closed` | Estado de sessão de mercado (alias de `--up`/`--slate-dim`) |
| `--stale-data` | Dado potencialmente desatualizado |

### Espaço, raio, tipografia, movimento
Escala de espaço em base 4px (`--sp-1` a `--sp-10`), raios `--r-sm`
a `--r-pill`, fontes do sistema (`--font-display`/`--font-body`) +
mono pra número (`--font-mono`, sempre com `font-variant-numeric:
tabular-nums` via `.mono`), easing único `--ease-out`. Sem mudança
nesta fase — já eram consistentes.

## Componentes de metadado (novos nesta fase)

Antes de existirem, cada página que precisava mostrar fonte/frescor/
proxy inventava seu próprio estilo. Agora é um padrão único:

- **`.data-badge`** (+ `.live` / `.proxy` / `.stale` / `.closed` /
  `.neutral`) — badge com ponto colorido, pra qualquer indicador de
  estado de dado. Substitui o `.status-badge` que `status.html` tinha
  criado localmente.
- **`.meta-source`** — `<span class="meta-source">Fonte: <strong>TradingView</strong></span>`.
- **`.meta-freshness`** — texto mono discreto pra "atualizado às HH:MM".
- **`.proxy-notice`** — aviso de proxy/estimativa, sempre com o mesmo
  símbolo (⚠) e cor (`--warning`), nunca escondido.
- **`.source-link`** — link de saída pra fonte original, estilo único
  em vez de cada página escolher uma cor.
- **`.market-status`** (+ `.open`/`.closed`) — indicador de sessão B3
  aberta/fechada. Lógica em `theme.js::statusMercado()` (10h–17h BRT,
  seg-sex — simplificado, não cobre feriado/after-market). Montar via
  `window.AntesDoSinoTema.montarMarketStatus('id-do-container')`.

## Regra de ouro

Se um elemento não comunica hierarquia, status, fonte ou ação, ele não
entra. Cor de destaque (`--gold`) continua rara de propósito — se
aparecer em todo componente, deixa de ser assinatura e vira ruído.
