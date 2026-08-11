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
  visibilidade por papel), alertas de posicao (ver Fase 2).

**Fase 2 -- posicao e derivativos (completa):**
- Modelos de dados (`Posicao`, `PosicaoHistorico`, `PosicaoDerivativo`,
  `PosicaoAluguel`) em `app/models.py`.
- Parser flexivel de importacao de posicao (`domain/position_import.py`):
  mapeamento de colunas configuravel (o formato do arquivo do backoffice
  pode variar entre custodiantes). Linhas invalidas viram **linhas
  rejeitadas com motivo** em vez de derrubar a importacao inteira; so um
  problema estrutural (coluna obrigatoria ausente, arquivo sem cabecalho,
  nenhuma fonte de data de referencia) interrompe o parser.
- Job de importacao (`scripts/importar_posicoes.py`): le o arquivo da
  pasta de rede interna, resolve cada cliente pelo codigo cadastrado no
  CRM, faz upsert em `Posicao` e insere snapshot em `PosicaoHistorico`
  (nunca sobrescrito). Cada rodada e registrada em `ImportacaoExecucao` /
  `ImportacaoLinhaRejeitada` -- linha rejeitada (formato invalido ou
  cliente nao cadastrado) fica registrada para conferencia, nunca some
  silenciosamente. Idempotente por dia: rodar duas vezes no mesmo dia
  atualiza a posicao corrente mas nao duplica o historico.
- **Motor de classificacao de estruturas de opcoes**
  (`domain/options_engine.py`): funcao pura, deterministica (regras
  explicitas, sem heuristica probabilistica ou LLM), que reconhece trava
  de alta/baixa com CALL, trava de alta/baixa com PUT, straddle
  comprado, strangle comprado e collar, na ordem definida na
  especificacao. Quantidades desiguais viram estrutura parcial + sobra
  (nunca descarta a identificacao nem forca pareamento errado).
- **Alertas de posicao** (`domain/alertas.py`), tambem deterministicos:
  vencimento em ate 5 dias uteis sem posicao de rolagem identificada no
  mesmo ticker, perna vendida com risco de exercicio (strike dentro do
  dinheiro ou proximo do preco atual perto do vencimento), e concentracao
  de exposicao derivativa em um unico ticker. Aparecem tanto na ficha de
  posicao do cliente quanto agregados no dashboard do dia.
- Tela de cliente -- posicao (`/clientes/{id}/posicao`): abas Resumo
  (patrimonio, exposicao liquida, variacao do dia), Acoes/ETFs/FIIs,
  Derivativos (agrupados por estrutura identificada, com destaque visual
  para vencimento proximo e para perna vendida) e Exposicao consolidada
  por ticker.

`domain/options_engine.py`, `domain/alertas.py` e
`domain/position_import.py` sao modulos **isolados e testaveis**, sem
dependencia de banco de dados ou do FastAPI -- propositalmente, para
permitir revisao por compliance linha a linha. `app/position_view.py` e a
camada fina que busca os dados importados no banco e os alimenta a esses
modulos puros para montar a tela do cliente e os alertas do dashboard.

**Fase 3 -- colaboracao e compliance (completa):**
- **Log de acesso a cliente** (`AccessLog`, item 10): toda visualizacao
  da ficha ou da posicao de um cliente e registrada com o motivo do
  acesso -- `TITULAR`, `COMPARTILHADO`, `HANDOFF`, `HEAD_MESA` ou
  `COMPLIANCE` (`app/crud.determinar_motivo_acesso`). Append-only; a
  retencao segue a politica de compliance da instituicao (administracao
  do banco, fora do escopo deste software).
- **Handoff de cobertura entre traders** (`/handoffs`, item 6): head_mesa
  ou compliance registra a transferencia temporaria de acesso de um
  trader para outro -- de toda a carteira ou de um cliente especifico --
  com motivo, inicio e fim opcional. Enquanto ativo (fim nulo ou no
  futuro), o trader destino ve e interage com os clientes cobertos como
  se fosse titular; ao encerrar (manualmente ou pela data de fim), o
  acesso reverte imediatamente -- nao ha edicao de registro, apenas o
  handoff deixar de estar ativo.
- **Notas internas da mesa** (item 7): vinculadas a um cliente, marcadas
  na interface como "nota interna -- nao enviar ao cliente", append-only.
  Visiveis para quem ja pode ver o cliente (titular, head_mesa,
  compliance, handoff ativo ou compartilhamento explicito) -- a mesma
  regra de visibilidade da ficha do cliente, sem controle de acesso
  separado para reduzir risco de inconsistencia.
- **Mural interno da mesa** (`/mural`, item 8): postagens curtas (ate 500
  caracteres) visiveis a todos os traders. Deliberadamente so tem um
  campo de texto livre, sem nenhuma referencia estruturada a cliente ou
  posicao -- o mural e para avisos, nao para extrato de carteira.
- **Relatorio de auditoria exportavel** (`/auditoria`, item 9): uso
  exclusivo de head_mesa/compliance. Filtra por periodo, trader e/ou
  cliente; consolida interacoes registradas e acessos fora da carteira
  titular do usuario (`AccessLog.motivo != TITULAR`). Exporta CSV
  (`/auditoria/export.csv`) com uma linha por registro e a coluna
  `tipo_registro` distinguindo `INTERACAO` de `ACESSO_FORA_TITULAR`.

Todo texto de interface deste sistema deixa explicito: **visao
informativa para uso interno da mesa** -- nada aqui gera recomendacao de
hedge ou qualquer output endereçado a cliente final. O motor de
classificacao e os alertas sao regra deterministica auditavel, nunca
IA/LLM.

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
- O relatorio de auditoria e exportado como arquivo CSV baixado
  diretamente do navegador -- nao ha envio automatico a nenhum servico
  externo; a distribuicao do arquivo apos o download e responsabilidade
  operacional da area de compliance.
- Nenhuma dependencia deste projeto (ver `requirements.txt`) e um SDK de
  nuvem ou cliente de API de terceiros. Se algum dia adicionar uma
  biblioteca nova, verifique se ela nao tem telemetria "phone home"
  habilitada por padrao antes de instalar.
- IA/NLP (fase futura e opcional) so pode rodar via modelo local (ex:
  Ollama). Nunca via API externa. A versao atual nao usa IA/LLM em nenhum
  ponto -- toda classificacao (estruturas de opcoes, alertas) e regra
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
| `CRM_DIAS_UTEIS_ALERTA_VENCIMENTO` | `5`                          | limiar (dias uteis) dos alertas de vencimento/risco de exercicio |

### Rodando os testes

```bash
pip install -r requirements.txt   # inclui pytest e httpx
pytest -q
```

98 testes ao todo, cobrindo:
- integracao da Fase 1 (auth, visibilidade de carteira, append-only de
  interacao, dashboard);
- unitarios do motor de classificacao de estruturas e dos alertas de
  posicao (Fase 2);
- unitarios do parser de importacao e do job de importacao ligado ao
  banco (Fase 2);
- integracao da tela de posicao do cliente e dos alertas no dashboard
  (Fase 2);
- integracao de handoff de cobertura, notas internas, mural da mesa e
  relatorio de auditoria, incluindo a trilha de motivo de acesso (Fase 3).

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

## Pasta de importacao de posicao

O job (`scripts/importar_posicoes.py`) le um arquivo CSV/TXT depositado
em uma pasta de rede interna pelo backoffice/custodia. Como o formato
exato varia entre instituicoes, o mapeamento de colunas e configuravel:
edite `MAPEAMENTO_PADRAO` em `scripts/importar_posicoes.py` ou passe um
JSON com as mesmas chaves de `ColumnMapping` via `--config`. O CRM
**nunca calcula posicao** -- ele apenas le e normaliza o que veio da
fonte oficial.

Uso tipico, agendado via cron/Task Scheduler do servidor interno no
horario de abertura do pregao:

```bash
python scripts/importar_posicoes.py /pasta/rede/interna/posicao_hoje.csv
python scripts/importar_posicoes.py --config config/mapeamento_custodia_x.json /pasta/.../posicao.csv
```

Ao final, o job imprime quantas posicoes foram importadas e quantas
linhas foram rejeitadas; o detalhe de cada rejeicao (numero da linha,
motivo, conteudo bruto) fica gravado na tabela
`importacao_linhas_rejeitadas`, vinculado a rodada em
`importacao_execucoes` -- nada e descartado sem rastro.

Para uso programatico direto do parser (sem tocar o banco):

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
resultado = parse_position_file("/pasta/rede/interna/posicao_20260811.csv", mapping)
resultado.posicoes      # linhas validas
resultado.rejeitadas    # linhas invalidas, com motivo -- nunca derruba a importacao inteira
```

A importacao cobre posicao a vista (`Posicao`/`PosicaoHistorico`).
Derivativos (`PosicaoDerivativo`) e aluguel (`PosicaoAluguel`) usam o
mesmo padrao de modelo mas ainda nao tem um job de importacao dedicado
-- se o backoffice exportar esses dados em arquivo separado, o proximo
passo natural e um segundo `ColumnMapping`/parser especifico (strike,
vencimento, direcao, codigo de serie) seguindo o mesmo formato de
`domain/position_import.py`.

## Handoff de cobertura entre traders

`/handoffs` (menu visivel para `head_mesa`/`compliance`) registra a
transferencia temporaria de acesso de um trader para outro -- por
exemplo, ferias ou licenca. Ao criar um handoff, escolha:

- **Escopo**: toda a carteira do trader de origem, ou apenas um cliente
  especifico.
- **Fim previsto** (opcional): se deixado em branco, o handoff fica
  ativo ate ser encerrado manualmente pelo botao "Encerrar" na lista.

Enquanto ativo, o trader destino ve os clientes cobertos na sua lista de
clientes, pode registrar interacoes e notas internas, e o acesso fica
registrado em `AccessLog` com `motivo=HANDOFF`. Ao encerrar (data de fim
alcancada ou encerramento manual), o acesso reverte imediatamente -- a
proxima requisicao do trader destino ja nao encontra mais o cliente na
carteira.

## Relatorio de auditoria

`/auditoria` (uso exclusivo de `head_mesa`/`compliance`) filtra por
periodo, trader e/ou cliente, e mostra:

1. **Interacoes registradas** no periodo (o log de contato com o
   cliente -- inclui qualquer recomendacao dada verbalmente, registrada
   pelo proprio trader no campo de resumo).
2. **Acessos fora da carteira titular**: toda linha de `AccessLog` cujo
   motivo nao seja `TITULAR` (ou seja, `COMPARTILHADO`, `HANDOFF`,
   `HEAD_MESA` ou `COMPLIANCE`).

O botao "Exportar CSV" (`/auditoria/export.csv`) gera um arquivo com os
mesmos filtros aplicados, com a coluna `tipo_registro` distinguindo
`INTERACAO` de `ACESSO_FORA_TITULAR` -- pronto para anexar a um processo
de compliance ou abrir em planilha. O download acontece inteiramente
dentro do navegador, sem nenhuma chamada de rede externa.

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
    main.py                  ponto de entrada FastAPI
    models.py                 schema SQLAlchemy (Fase 1 + Fase 2 + Fase 3)
    database.py                engine/sessao
    security.py                 hash de senha (bcrypt)
    auth_deps.py                dependencias de sessao/autorizacao
    crud.py                      regras de visibilidade (inclui handoff) + trilha de auditoria
    position_view.py              monta a visao de posicao/alertas de um cliente
    auditoria.py                   consulta e exportacao CSV do relatorio de auditoria
    seed.py                          usuarios iniciais
    routers/                         auth, clientes, posicoes, interacoes, notas,
                                      handoffs, mural, auditoria, dashboard
    templates/                         HTML (Jinja2)
    static/                             CSS/JS proprios, sem CDN
  domain/
    options_engine.py    motor de classificacao de estruturas (Fase 2, item 7)
    alertas.py             alertas deterministicos de posicao (Fase 2, item 5)
    position_import.py       parser de importacao de posicao (Fase 2, item 1)
  scripts/
    importar_posicoes.py   job de importacao ligado ao banco (Fase 2, item 1)
    backup.py                 dump do banco para pasta de rede interna
  tests/
    test_web.py                     integracao Fase 1
    test_options_engine.py           unitarios do motor de classificacao
    test_alertas.py                   unitarios dos alertas de posicao
    test_position_import.py            unitarios do parser
    test_importar_posicoes.py           integracao do job de importacao
    test_posicoes_view.py                integracao da tela de posicao + alertas no dashboard
    test_handoffs.py                      integracao de handoff de cobertura
    test_notas_internas.py                 integracao de notas internas
    test_mural.py                           integracao do mural da mesa
    test_auditoria.py                        integracao do relatorio de auditoria
  run.py                  `python run.py` sobe o servidor local
```
