# Worker de autenticação do Diário de Decisão

Backend mínimo (Cloudflare Workers, plano gratuito) que verifica o
login do Telegram Login Widget e devolve só os registros do usuário
autenticado. Sem isso, verificar o login teria que expor o token do
bot no navegador — o que não pode acontecer.

## Passo a passo (pelo painel do Cloudflare, sem instalar nada)

1. Crie uma conta gratuita em [dash.cloudflare.com](https://dash.cloudflare.com/sign-up) (se ainda não tiver).
2. No menu lateral, vá em **Workers & Pages** → **Create** → **Create Worker**.
3. Dê o nome `antesdosino-diario-auth` (ou o que preferir) → **Deploy** (ele cria com um código de exemplo, tudo bem, vamos trocar).
4. Clique em **Edit code**. Apague todo o conteúdo do editor e cole o conteúdo do arquivo [`diario-auth-worker.js`](./diario-auth-worker.js) desta pasta.
5. Clique em **Save and Deploy**.
6. Vá em **Settings** → **Variables and Secrets** → **Add** (repita para os dois):
   - Nome `TELEGRAM_BOT_TOKEN`, valor: o mesmo token do bot que já está configurado como secret no GitHub Actions (Settings → Secrets → Actions do repositório).
   - Nome `DECISOES_ENCRYPTION_KEY`, valor: a mesma chave Fernet que você já configurou como secret no GitHub Actions.
   - Marque os dois como **Secret** (não "Text"), pra não ficarem visíveis depois de salvos.
7. Depois de salvar, a URL do seu Worker aparece no topo da página (algo como `https://antesdosino-diario-auth.SEU-SUBDOMINIO.workers.dev`). **Copie essa URL e me envie** — é o que falta pra ligar a página `docs/diario.html` a esse Worker.

## Alternativa: linha de comando (wrangler)

Se preferir CLI em vez do painel:

```bash
cd worker
npm install -g wrangler
wrangler login
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put DECISOES_ENCRYPTION_KEY
wrangler deploy
```

## Por que precisa disso

O Telegram Login Widget devolve um payload assinado (hash HMAC-SHA256
com chave `SHA256(token_do_bot)`). Verificar essa assinatura exige o
token do bot — e o token do bot **nunca** pode estar no navegador
(quem tivesse acesso ao código-fonte da página poderia lê-lo e usá-lo
pra qualquer coisa em nome do bot). Por isso a verificação roda aqui,
num servidor, e não em `docs/theme.js` ou `docs/terminal.js`.

O Worker também é o único lugar que decifra `decisoes_usuarios.json`
(que fica sempre criptografado no repositório) — e devolve pro
navegador só os registros do `chat_id` que acabou de se autenticar,
nunca o arquivo inteiro.
