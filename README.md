# Antes do Sino — bot

Bot de notícias financeiras do mercado brasileiro. Lê feeds RSS, classifica e traduz notícias via IA (Groq), publica no Telegram e gera os arquivos estáticos do site (`docs/`, GitHub Pages).

Não é uma SPA nem tem build step — veja `CLAUDE.md` para as regras permanentes do projeto (stack real, o que pode e não pode mudar).

## Como o bot roda

`main.py` é executado pela GitHub Action `.github/workflows/bot.yml`, disparada externamente (cron-job.org → `workflow_dispatch`) a cada poucos minutos. Não há `schedule:` no workflow — a cadência real vem do disparo externo, não do GitHub Actions.

Dentro de cada execução, o bot só processa algo se estiver dentro da **janela de operação** (`dentro_da_janela_de_operacao()`): **06h40 às 22h30**, horário de Brasília (`America/Sao_Paulo`). Fora dessa janela o ciclo é ignorado sem consumir nenhuma API.

## Variáveis de ambiente

Configuradas como *secrets* do repositório e repassadas pelo workflow:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sim | Token do bot no Telegram. Sem isso o bot não roda. |
| `TELEGRAM_CHAT_ID` | sim | Chat/canal onde as mensagens reais são publicadas. |
| `TELEGRAM_ADMIN_CHAT_ID` | não | Chat separado para aprovações do motor de conteúdo social e para notificações de revisão manual (temas sensíveis de alto impacto). Sem essa variável, essas notificações são um no-op silencioso — não afeta o canal principal. |
| `GROQ_API_KEY` | não | Habilita classificação/tradução/síntese via IA (`USE_AI`). Sem ela, o bot continua publicando (título/corpo originais, sem tradução nem score de materialidade). |
| `BRAPI_TOKEN` | não | Cotações de ações brasileiras (Brapi). |
| `TWELVEDATA_API_KEY` | não | Cotações de câmbio/cripto (TwelveData). |
| `FRED_API_KEY` | não | Séries do Federal Reserve (FRED) — **não configurada hoje**; sem ela, esses dados ficam indisponíveis. |
| `DRY_RUN` | não | `true`/`1`/`yes` gera as mensagens completas no log **sem enviar** ao Telegram. Default `false` (produção normal). |
| `FORCE_MORNING_BRIEFING` | não | `true`/`1`/`yes` força o envio do Briefing de Abertura mesmo fora da janela, fora de dia útil ou já enviado hoje. Default `false`. |
| `MORNING_BRIEFING_HORA` / `MORNING_BRIEFING_MINUTO` | não | Horário alvo do Briefing de Abertura. Default `6`/`50` (06h50). A janela de tolerância (-10min/+20min) é calculada a partir desse alvo. |

## Agendamento das publicações

Todas usam o mesmo padrão: estado persistido em `docs/*.json` (comitado pelo próprio bot a cada ciclo), envio no máximo 1x por dia útil da B3 (feriados nacionais excluídos, `eh_dia_util_b3()`).

| Publicação | Janela (BR_TZ) | Estado |
|---|---|---|
| **Briefing de Abertura** (`tipo="abertura"`) | 06h40–07h10 (alvo 06h50, configurável) | `docs/morning_briefing_state.json` |
| Snapshot de mercado | 12h00–12h15 | `docs/snapshot_state.json` |
| Fechamento B3 (Evening Briefing) | 18h15–18h45 | `docs/briefings_state.json` |
| Fechamento noturno (Night Wrap) | 22h20–22h30 (sempre a última mensagem do dia) | `docs/night_wrap_state.json` |
| Giro do Mercado | a cada 4h, só publica se houver algo na fila | `docs/giro_state.json` |
| Alertas essenciais (breaking) | imediato, máx. 3/dia | `docs/breaking_state.json` |

### Briefing de Abertura — detalhes

- **Lock contra execução simultânea**: `docs/morning_briefing.lock`, arquivo criado atomicamente (`os.open` com `O_CREAT|O_EXCL`). Lock mais velho que 10 minutos é considerado órfão (execução anterior travou) e é destravado sozinho.
- **Retry no envio**: até 3 tentativas com 5s de espera entre elas. Se todas falharem, o estado não é marcado como enviado — a próxima execução dentro da janela tenta de novo.
- **Conteúdo**: reaproveita cálculos já existentes no pipeline — `compute_market_temperature` (Temperatura do Mercado, mesma função usada pelo Radar de Abertura do site), `compute_news_clusters` e `build_sellside_synopsis` (Ativos para acompanhar / Riscos, mesmas funções do Fechamento B3). Nunca inventa leitura sem dado suficiente — cada seção mostra uma frase honesta ("Aguardando dados", "Sem eventos previstos para hoje" etc.) quando não há informação real disponível.

## Como testar

Sem suíte automatizada (pytest) — validação é manual, conforme `CLAUDE.md`:

```bash
# 1. Sintaxe
python3 -m py_compile main.py

# 2. Dry-run local (gera as mensagens no console, sem enviar nada)
DRY_RUN=true python3 main.py

# 3. Forçar o Briefing de Abertura fora da janela/dia (combine com DRY_RUN
#    pra nunca publicar de verdade durante teste manual)
DRY_RUN=true FORCE_MORNING_BRIEFING=true python3 main.py
```

Local (fora do GitHub Actions) é preciso instalar as dependências primeiro: `pip install -r requirements.txt`.

### Pelo GitHub Actions

Aba **Actions** → workflow "Antes do Sino - Bot de Notícias" → **Run workflow** → marcar `dry_run` e/ou `force_morning_briefing` conforme o teste desejado. O disparo externo (cron-job.org) nunca passa esses inputs, então a produção real nunca é afetada por eles.

## Estrutura do pipeline

`main.py` roda em sequência (cada bloco isolado em seu próprio `try/except` — uma fonte quebrada nunca derruba o ciclo inteiro):

1. Coleta RSS (`FEEDS`) + encaminhador de canais do Telegram.
2. Limpeza de texto (`strip_html_tags`, `fix_mojibake`, `sanitize_message_text`, `strip_boilerplate`).
3. Classificação via IA (`classify_news_ai`): relevância, sentimento, tradução, score de materialidade, "por que importa", tipo de conteúdo (fato/opinião/entrevista), tema sensível.
4. Deduplicação (hash de URL/título + similaridade textual).
5. Decisão de despacho (`decide_dispatch_tier`): breaking / round (Giro) / discard, com tetos diários e rebaixamento por fonte não confirmada.
6. Publicações agendadas (ver tabela acima).
7. Geração do site estático (`docs/`).

`editorial_foundation.py` é um módulo isolado (nunca importa `main.py` de volta) com a camada de "modo sombra" — logging/métricas que não afetam a publicação real.
