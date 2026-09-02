# Antes do Sino — Auditoria do produto

_Gerado a partir de trabalho direto no repositório (não é uma inspeção
genérica de agente novo — este documento reflete o estado real do
código)._

## 1. Stack real

| Camada | Tecnologia |
|---|---|
| Pipeline/backend | Python 3.11, sem framework web |
| Agendamento | GitHub Actions (`workflow_dispatch`), disparado externamente via cron-job.org a cada poucos minutos |
| Frontend | HTML estático + CSS + JS vanilla, servido via GitHub Pages (`docs/`) |
| Design system | `docs/design-system.css` (tokens de cor/espaço/raio, tema claro/escuro) |
| Cotações/gráficos | Widgets públicos e gratuitos da TradingView (embed, sem chave) |
| Cotações BR (pipeline) | brapi.dev (plano free — 15.000 req/mês) |
| Notícias | Feeds RSS públicos |
| Distribuição | Telegram (bot próprio) |
| Segredos | GitHub Secrets — `BRAPI_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DECISOES_ENCRYPTION_KEY`, `CARTEIRA_PASSWORD_HASH` |
| Criptografia at-rest | Fernet (`cryptography`), pra dados de usuário (`decisoes_usuarios.json`, `carteira_status.json`) |

**Não há**: React/Vue/framework de UI, bundler, npm build step, suíte
de testes automatizada, banco de dados (tudo é JSON em arquivo,
versionado no próprio repo git).

## 2. Páginas existentes (`docs/`)

| Página | Função |
|---|---|
| `index.html` | Terminal — home do produto. Painéis de cotação (Índices, Moedas, Emergentes, Commodities, Ações Brasil, Cripto, VIX, Ativos em Destaque), abas por categoria, feed de notícias com leitor inline, Ctrl+K (busca + Contexto do Ativo), Contexto Macro (Fluxo Estrangeiro + curva DI até 2037), personalização (drag/hide + localStorage) |
| `calendario.html` | Calendário econômico (widget TradingView) |
| `mapa.html` | Mapa de calor (S&P 500 + Ibovespa) |
| `quant.html` | Painel quantitativo/screener |
| `sobre.html` | Sobre e Metodologia — de onde vêm os dados, o que o produto não é |
| `status.html` | Transparência de frescor dos dados por componente (pipeline, TradingView, Carteira, Diário) |
| `resumo-semanal.html` | Gerado pelo `main.py` — histórico de volume/sentimento de notícias, navegador de edições anteriores |
| `diario.html` | Diário de Decisão — login via Telegram Login Widget, mostra registros do usuário |
| `carteira.html` | Carteira de Dividendos — página privada (senha), não linkada em nav nenhuma |
| `dados-terminal.html` | **Não é página pública** — gerado pelo `main.py`, consumido via `fetch()` pelo próprio Terminal (evita expor lógica de geração client-side) |
| `template.html` | Template-fonte usado pelo `main.py` pra gerar `dados-terminal.html` |
| `fechamento-hoje.html`, `premarket-hoje.html` | Snapshots gerados pelo pipeline (digests do dia) |

## 3. Módulos Python

- **`main.py`** — pipeline central: ingestão RSS, classificação de
  materialidade/sentimento, geração de hashtags por ticker (regex com
  fronteira de palavra, corrigido nesta sessão), Giro do Mercado,
  Breaking, Briefing Matinal, Fechamento B3, Night Wrap, cotações
  (brapi + Twelve Data + FRED), Social Content Engine (Instagram,
  isolado em `social/`), export de `status.json`, `resumo_historico.json`.
- **`editorial_foundation.py`** — clustering de stories (`derive_cluster_key`),
  modo sombra de decisão editorial. Recebe tudo por parâmetro do `main.py`.
- **`diario_decisao.py`** — registro factual de compra/venda via
  Telegram, sem julgamento nem recomendação; acompanhamento pós-decisão.
- **`carteira_dividendos.py`** — estratégia mecânica de aporte mensal
  (dividend growth/yield), universo fixo de 8 tickers, roda todo dia 10.

Todas as integrações novas em `main.py::main()` seguem o padrão
isolado: `try/except` próprio, log do erro, sem derrubar o ciclo.

## 4. Princípios de produto já em vigor

- Zero redação humana — pipeline 100% automatizado.
- Zero recomendação de compra/venda — declarado explicitamente em
  `sobre.html` e reforçado em toda feature nova (Diário de Decisão,
  Carteira de Dividendos).
- Proxy só quando não há fonte gratuita melhor, e sempre identificado
  como proxy na própria tela (ex: Fluxo Estrangeiro via EWZ).
- Dados sensíveis de usuário (Diário de Decisão, Carteira) criptografados
  at-rest com Fernet, porque o repo é público (GitHub Pages free exige
  isso) e arquivos fora de `docs/` continuam acessíveis via
  `raw.githubusercontent.com`.

## 5. Riscos e limitações conhecidos

- **brapi.dev free tier (15.000 req/mês)**: o ciclo do bot roda a cada
  ~5min, 10 chamadas por ciclo (`COCKPIT_TICKERS`) só dentro da janela
  06h50–22h30 → estimativa de ~56.400 req/mês, acima do free tier.
  Falha de cota é **silenciosa** (só um `print`, cotação some sem
  travar nada) — vale monitorar via `status.html` ou considerar o
  plano Startup (150.000 req/mês, ~R$100–120/mês, preço não confirmado
  na fonte oficial).
- **Sem histórico de preço próprio**: não guardamos série histórica de
  cotação além do que os widgets da TradingView mostram ao vivo — logo
  não dá pra calcular retorno em janelas (1d/5d/20d/12m) nem
  comparação com benchmark sem uma nova fonte de dados.
- **OBM (obm.com.br)**: fonte externa promissora (dados abertos B3,
  Tesouro, fundos, FIIs), mas API sem documentação pública, acesso por
  chave sob pedido manual, uso comercial não autorizado por padrão.
  Hoje só é seguro usar como **link de saída** (confirmado:
  `obm.com.br/acoes/<ticker>` pra ações BR) — não como fonte de dado
  embutida no produto.
- **Cloudflare Worker** (`worker/diario-auth-worker.js`): código pronto
  pra verificação de login Telegram e senha da Carteira, mas o deploy
  final (URL do Worker) ainda não foi confirmado/plugado em
  `diario.html`/`carteira.html` (placeholders ainda presentes).

## 6. O que NÃO existe (evitar assumir)

- Nenhum sistema de contas/autenticação genérico (Diário de Decisão
  usa Telegram Login Widget; Carteira usa senha única, hardcoded via
  hash em secret — ambos single-purpose, não um sistema de usuários).
- Nenhuma API própria exposta publicamente (o "backend" é só o
  pipeline batch + os dois endpoints do Cloudflare Worker).
- Nenhum componente de UI reutilizável em código (é HTML/CSS repetido
  entre páginas seguindo convenção visual, não uma biblioteca de
  componentes).
