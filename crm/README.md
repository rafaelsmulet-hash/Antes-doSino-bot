# CRM offline -- Mesa de Sales Trading (Renda Variavel)

Sistema de CRM 100% offline / air-gapped para uma mesa de sales traders de
renda variavel. Roda inteiramente dentro da rede interna da instituicao;
nao existe nenhuma chamada de rede externa em nenhum ponto do codigo.

## O que ja esta implementado

**Fase 1 -- nucleo de relacionamento (completa):**
- Autenticacao local (usuario/senha com hash bcrypt), papeis `trader`,
  `head_mesa`, `compliance`.
- Cadastro de clientes (PF/PJ/fundo, book, perfil de risco, produtos
  habilitados, tags/setores, trader titular, compartilhamento explicito
  com outros traders).
- Log de interacao **append-only**: nao existe rota de editar/apagar uma
  interacao ja salva. Correcoes criam uma nova linha ligada ao registro
  original via `corrige_interacao_id`.
- Dashboard do dia: clientes sem contato ha mais de N dias, follow-ups
  pendentes, feed de interacoes recentes da mesa (respeitando
  visibilidade por papel).
- Trilha de auditoria (`AccessLog`): toda vez que `head_mesa` ou
  `compliance` abre a ficha de um cliente, fica registrado quem viu o
  que e quando.

**Fase 2 -- posicao e derivativos (fundacao pronta, ainda nao integrada a interface):**
- Modelos de dados (`Posicao`, `PosicaoHistorico`, `PosicaoDerivativo`,
  `PosicaoAluguel`) em `app/models.py`.
- Parser flexivel de importacao de posicao (`domain/position_import.py`):
  mapeamento de colunas configuravel (o formato do arquivo do backoffice
  pode variar entre custodiantes), com testes cobrindo formatos
  diferentes, colunas ausentes, valores invalidos e linhas vazias.
- **Motor de classificacao de estruturas de opcoes**
  (`domain/options_engine.py`): funcao pura, deterministica (regras
  explicitas, sem heuristica probabilistica ou LLM), que reconhece trava
  de alta/baixa com CALL, trava de alta/baixa com PUT, straddle
  comprado, strangle comprado e collar, na ordem definida na
  especificacao. Quantidades desiguais viram estrutura parcial + sobra
  (nunca descarta a identificacao nem forca pareamento errado). 20 testes
  unitarios cobrindo cada padrao e os casos de borda.

Este motor e o parser sao modulos **isolados e testaveis**, sem
dependencia de banco de dados ou do FastAPI -- propositalmente, para
permitir revisao por compliance linha a linha e testes rapidos, antes de
serem conectados as telas do cliente (abas de posicao, alertas de
vencimento etc. -- proximo passo da Fase 2, ainda nao implementado).

**Fase 3** (handoff de cobertura, notas internas, mural, relatorio de
auditoria exportavel) nao foi implementada neste momento -- fica como
proximo passo, conforme prioridade indicada na especificacao ("se houver
tempo/necessidade").

Todo texto de interface deste sistema deixa explicito: **visao
informativa para uso interno da mesa** -- nada aqui gera recomendacao de
hedge ou qualquer output endereçado a cliente final.

## Isto NUNCA se conecta a internet

Para reforcar com o time: nenhuma das pecas abaixo faz ou deve fazer
qualquer chamada de rede externa.

- O backend (FastAPI/uvicorn) so escuta em `127.0.0.1` ou no IP interno
  da mesa que voce configurar -- nunca deve ser exposto publicamente.
- O banco (SQLite local, ou PostgreSQL se migrar para o cenario
  multiusuario) fica dentro da rede interna.
- O frontend e HTML/CSS/JS proprio, servido pelo proprio backend. Nao ha
  nenhum `<script src="https://...">` de CDN em nenhum template -- todo
  CSS e JS estao em `app/static/` e sao versionados junto com o codigo.
- Autenticacao e local (bcrypt + sessao assinada por cookie). Nao ha
  integracao obrigatoria com nenhum servico externo de identidade.
- A importacao de posicao (Fase 2) le arquivos de uma pasta de rede
  interna (`CRM_IMPORT_DIR`) gerados pelo backoffice/custodia -- nunca
  busca dados de uma API externa.
- O backup (`scripts/backup.py`) grava em uma pasta de rede interna
  (`CRM_BACKUP_DIR`) -- nunca em nuvem pessoal ou servico externo.
- Nenhuma dependencia deste projeto (ver `requirements.txt`) e um SDK de
  nuvem ou cliente de API de terceiros. Se algum dia adicionar uma
  biblioteca nova, verifique se ela nao tem telemetria "phone home"
  habilitada por padrao antes de instalar.
- IA/NLP (fase futura e opcional) so pode rodar via modelo local (ex:
  Ollama). Nunca via API externa. A versao atual nao usa IA/LLM em nenhum
  ponto -- toda classificacao (estruturas de opcoes) e regra
  deterministica auditavel.

## Como rodar localmente

Requisitos: Python 3.11+.

```bash
cd crm
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run.py                    # sobe em http://127.0.0.1:8000
```

No primeiro start, o banco SQLite e criado em `data/crm.db` e tres
usuarios de exemplo sao semeados (troque as senhas no primeiro acesso em
um ambiente real):

| usuario     | papel       | senha inicial     |
|-------------|-------------|--------------------|
| `head_mesa` | head_mesa   | `mude-esta-senha`  |
| `compliance`| compliance  | `mude-esta-senha`  |
| `trader1`   | trader      | `mude-esta-senha`  |

Variaveis de ambiente uteis (todas opcionais, com default local):

| variavel                     | default                          | uso |
|-------------------------------|-----------------------------------|-----|
| `CRM_HOST`                    | `127.0.0.1`                       | IP em que o uvicorn escuta |
| `CRM_PORT`                    | `8000`                            | porta |
| `CRM_DATABASE_URL`            | `sqlite:///./data/crm.db`         | troque para `postgresql://...` no cenario multiusuario |
| `CRM_SECRET_KEY`               | chave de exemplo (troque!)        | assinatura do cookie de sessao |
| `CRM_DATA_DIR`                 | `./data`                          | onde fica o arquivo SQLite |
| `CRM_BACKUP_DIR`               | `./data/backups`                  | pasta de rede interna para backup |
| `CRM_IMPORT_DIR`               | `./data/importacao`               | pasta de rede interna onde o backoffice deposita o arquivo de posicao |
| `CRM_DIAS_SEM_CONTATO_ALERTA`  | `10`                              | limiar do alerta "sem contato" no dashboard |

### Rodando os testes

```bash
pip install -r requirements.txt   # inclui pytest e httpx
pytest -q
```

43 testes ao todo: 14 de integracao da Fase 1 (auth, visibilidade de
carteira, append-only de interacao, dashboard) + 20 unitarios do motor de
classificacao de estruturas + 9 unitarios do parser de importacao (Fase 2).

### Criptografia em repouso (SQLCipher)

O MVP usa SQLite puro. Para dados sigilosos em producao, troque o driver
por SQLCipher (`pysqlcipher3` ou equivalente) e ajuste
`app/database.py`/`CRM_DATABASE_URL` para abrir o banco com a chave de
criptografia -- a chave deve ser gerenciada pela area de seguranca da
instituicao (nunca commitada no repositorio). Isso nao muda nenhuma outra
parte da aplicacao.

### Cenario multiusuario (PostgreSQL)

Para varios traders acessando ao mesmo tempo, suba um PostgreSQL no
servidor interno da mesa e aponte `CRM_DATABASE_URL` para ele, por
exemplo:

```bash
export CRM_DATABASE_URL="postgresql+psycopg2://usuario:senha@servidor-interno:5432/crm_mesa"
```

Nenhuma mudanca de codigo e necessaria -- os modelos usam SQLAlchemy, que
e agnostico ao banco.

## Pasta de importacao de posicao (Fase 2)

O parser (`domain/position_import.py`) le um arquivo CSV/TXT depositado
em `CRM_IMPORT_DIR` pelo backoffice/custodia. Como o formato exato varia
entre instituicoes, o mapeamento de colunas e configuravel via
`ColumnMapping` (nomes de coluna, delimitador, separador decimal). O CRM
**nunca calcula posicao** -- ele apenas le e normaliza o que veio da
fonte oficial. Um exemplo de uso programatico:

```python
from domain.position_import import ColumnMapping, parse_position_file

mapping = ColumnMapping(
    cliente_codigo="cod_cliente",
    ticker="cod_ativo",
    tipo_ativo="tipo",
    quantidade="qtd",
    preco_medio="pm",
    preco_atual="preco_atual",
    delimitador=";",
    separador_decimal=",",
)
posicoes = parse_position_file("/pasta/rede/interna/posicao_20260811.csv", mapping)
```

A rotina/job que agenda a leitura diaria dessa pasta e faz o upsert no
banco (tabelas `Posicao`/`PosicaoHistorico`) ainda nao foi implementada
-- e o proximo passo, junto com a integracao do motor de classificacao
(`domain/options_engine.py`) as telas do cliente (aba de derivativos,
alertas de vencimento e de concentracao de risco).

## Backup

```bash
python scripts/backup.py                          # usa CRM_BACKUP_DIR
python scripts/backup.py --destino /caminho/rede   # destino explicito
```

Usa `sqlite3 .backup` (seguro mesmo com o banco em uso) e grava um
arquivo `crm_backup_<timestamp>.db` na pasta de rede interna designada.
Agende via cron/Task Scheduler do servidor interno da mesa -- nunca
aponte `CRM_BACKUP_DIR` para uma nuvem pessoal ou servico externo. Para
PostgreSQL, use `pg_dump` apontando para o mesmo servidor interno (o
script atual cobre apenas SQLite).

## Estrutura do projeto

```
crm/
  app/
    main.py              ponto de entrada FastAPI
    models.py             schema SQLAlchemy (Fase 1 + Fase 2)
    database.py            engine/sessao
    security.py             hash de senha (bcrypt)
    auth_deps.py            dependencias de sessao/autorizacao
    crud.py                  regras de visibilidade + trilha de auditoria
    seed.py                   usuarios iniciais
    routers/                 auth, clientes, interacoes, dashboard
    templates/                 HTML (Jinja2)
    static/                     CSS/JS proprios, sem CDN
  domain/
    options_engine.py    motor de classificacao de estruturas (Fase 2, item 7)
    position_import.py    parser de importacao de posicao (Fase 2, item 5)
  scripts/
    backup.py                dump do banco para pasta de rede interna
  tests/
    test_web.py              integracao Fase 1
    test_options_engine.py    unitarios do motor de classificacao
    test_position_import.py    unitarios do parser
  run.py                  `python run.py` sobe o servidor local
```
