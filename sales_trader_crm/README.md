# Mesa — Monitoramento de Estruturas (multiusuário)

Sistema web para a mesa de sales trading acompanhar estruturas de derivativos
(barreiras, fixing, resultado) a partir do CSV diário do Orbit, mais o
cadastro de clientes/operações/carteira que cada operador já usava. Cada
operador só vê os próprios dados — nada de contato/CRM (isso já é feito pelo
CRM da corretora) nem telefone/WhatsApp (isso passa pelo Tuvis).

**Hospedagem ainda não foi decidida.** Por enquanto isto roda localmente,
para validar que o sistema funciona bem antes de decidir onde ele mora.

## Como rodar localmente

```bash
cd sales_trader_crm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# cria a primeira conta (admin — só o admin pode importar o CSV do Orbit)
python seed_admin.py rafael "uma-senha-forte" "Rafael"

python app.py
```

Abra http://localhost:5000 — entre com o usuário/senha criado no `seed_admin.py`.

Os dados ficam em `mesa.db` (SQLite, criado automaticamente, ignorado pelo
git). Para recomeçar do zero, apague `mesa.db` e rode `seed_admin.py` de novo.

## Cadastrando os outros operadores

Só o admin faz isso, em **Operadores** (menu do topo, visível só pra admin):
usuário, nome de exibição e senha. **O "usuário" precisa ser exatamente o
mesmo valor que aparece na coluna de operador do CSV do Orbit** — é assim que
o sistema sabe de quem é cada estrutura importada.

## Import diário do CSV do Orbit (admin)

Menu **Importar Orbit**. O arquivo precisa ter, além das colunas de sempre
(Nome Cliente, Estrutura, Ativo, Data operação, Fixing, Notional, Barreira
Down, Barreira up, Dis. Barreira(%), Barreira acionada em, Resultado (%),
Resultado (R$)), uma **coluna de operador** identificando o dono de cada
linha pelo usuário cadastrado no sistema. As colunas são identificadas
automaticamente pelo nome do cabeçalho — não precisa mapear manualmente.

Regras do import:
- Chave de cada estrutura: Cliente + Ativo + Estrutura + Data operação,
  dentro do escopo de cada operador.
- Estrutura ativa que não aparece mais no arquivo é encerrada automaticamente
  — **mas só para operadores que tiveram pelo menos uma linha no arquivo
  daquele dia**. Se um operador inteiro sumir do CSV (ex.: erro na exportação
  do Orbit), os dados dele ficam intocados e isso aparece destacado no
  resultado da importação, em vez de fechar tudo por engano.
- Linhas cujo valor de operador não bate com nenhum usuário cadastrado são
  ignoradas e listadas no resultado, pra você notar e corrigir (typo no nome
  de usuário, ou operador ainda não cadastrado).

## Status da barreira e alertas

O status vem direto dos campos que o Orbit já calcula, sem recalcular nada:

- **Atingida**: "Barreira acionada em" preenchida.
- **Próxima**: "Dis. Barreira(%)" ≤ limiar configurável (padrão 5%).
- **Normal**: caso contrário.

Alertas em **Atenção hoje** (dashboard de Monitoramento): barreira atingida,
barreira próxima, fixing próximo (dias configuráveis, padrão 5/2/1/0) e perda
relevante (Resultado(%) ≤ limiar configurável, padrão -10%). Cada operador
ajusta os próprios limiares em **Configurações**.

## Rascunho de comunicação

Botão "Rascunho" em qualquer alerta/estrutura gera um texto a partir dos
dados da estrutura, com aviso de revisão manual. **Nada é enviado
automaticamente** — o operador copia e cola onde for mandar de fato (ex.:
Tuvis/Salesforce).

## Clientes, operações e carteira

Cada operador mantém a própria lista de clientes (Código, Nome, Produtos) e
importa suas próprias planilhas de operações e carteira (identificando o
cliente pelo Código). Cada import **substitui** os dados anteriores daquele
cliente; na carteira, linhas repetidas do mesmo ativo têm as quantidades
somadas.

## Estrutura do projeto

- `db.py` — schema SQLite (`users`, `clients`, `operations`, `carteira_items`,
  `estruturas`, `settings`, `import_log`) e conexão. Tudo escopado por
  `user_id`, sempre filtrado nas queries — nunca confiar no cliente.
- `auth.py` — login por sessão (usuário/senha com hash), decorators
  `login_required`/`admin_required`.
- `monitor.py` — status de barreira, alertas, parsing de data dd/mm/aaaa,
  geração do texto de rascunho.
- `csv_import.py` — parsing do CSV do Orbit e upsert por operador.
- `io_import.py` — leitura de planilhas .csv/.xlsx para clientes/operações/carteira.
- `app.py` — rotas Flask.
- `templates/`, `static/` — telas e estilo (mesma paleta do protótipo local
  em HTML único).
- `seed_admin.py` — cria/reseta a primeira conta admin.
- `test_app.py` — testes de ponta a ponta (isolamento entre operadores,
  import do Orbit com a salvaguarda, alertas, clientes/operações/carteira).
  Rodar com `python test_app.py` (usa um banco temporário, não mexe no `mesa.db`).

## O que ainda falta decidir (fora do código)

- Onde hospedar (servidor interno vs. nuvem) e como os operadores vão
  acessar — combinado que isso fica para depois.
- Login continua sendo usuário/senha local por enquanto; dá pra trocar depois
  por login corporativo sem precisar redesenhar o resto do sistema.
