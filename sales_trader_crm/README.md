# Controle de Contato — Mesa (Sales Trader)

Ferramenta local para garantir que nenhum cliente de derivativos fique mais de
60 dias sem contato.

## Como rodar

```bash
cd sales_trader_crm
pip install -r requirements.txt
python app.py
```

Abra http://localhost:5000 no navegador. Os dados ficam em `clients.db`
(SQLite, criado automaticamente na primeira execução, ignorado pelo git).

## Regras de status

- **Verde**: mais de 20 dias restantes até o limite de 60 dias sem contato.
- **Amarelo**: 20 dias ou menos restantes.
- **Vermelho**: prazo estourado (mais de 60 dias sem contato).

A "data do último contato" de cada cliente é sempre o registro mais recente
no histórico de contatos — não existe um campo duplicado no cadastro.

## Estrutura

- `db.py` — schema SQLite (`clients`, `contacts`) e conexão.
- `status.py` — cálculo de dias desde o último contato, dias restantes e cor.
- `app.py` — rotas Flask (CRUD de clientes, dashboard, histórico de contato).
- `templates/`, `static/` — telas e estilo.
