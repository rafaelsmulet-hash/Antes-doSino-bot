# Worker de autenticação (Diário de Decisão + Carteira de Dividendos)

Backend mínimo (Cloudflare Workers, plano gratuito), com duas rotas:

- **`/telegram-login`** (ou raiz `/`) — verifica o login do Telegram Login Widget e devolve só os registros do usuário autenticado (Diário de Decisão). Sem isso, verificar o login teria que expor o token do bot no navegador — o que não pode acontecer.
- **`/carteira`** — verifica uma senha simples (página de uso pessoal do dono do projeto, não é multiusuário) e devolve o cálculo do aporte mensal da Carteira de Dividendos.

Mesmo Worker pras duas coisas — não precisa criar um segundo.

## Passo a passo (pelo painel do Cloudflare, sem instalar nada)

1. Crie uma conta gratuita em [dash.cloudflare.com](https://dash.cloudflare.com/sign-up) (se ainda não tiver).
2. No menu lateral, vá em **Workers & Pages** → **Create application** (ou **Create** → **Create Worker**, dependendo da versão do painel).
3. Escolha a opção de começar do zero (ex: "Start with Hello World!") — **não** conecte um repositório GitHub, **não** escolha um template.
4. Dê o nome `antesdosino-diario-auth` (ou o que preferir) → **Deploy** (ele cria com um código de exemplo, tudo bem, vamos trocar).
5. Clique em **Edit code**. Apague todo o conteúdo do editor e cole o conteúdo do arquivo [`diario-auth-worker.js`](./diario-auth-worker.js) desta pasta.
6. Clique em **Save and Deploy**.
7. Vá em **Settings** → **Variables and Secrets** → **Add** (repita para os três):
   - Nome `TELEGRAM_BOT_TOKEN`, valor: o mesmo token do bot que já está configurado como secret no GitHub Actions.
   - Nome `DECISOES_ENCRYPTION_KEY`, valor: a mesma chave Fernet que você já configurou como secret no GitHub Actions.
   - Nome `CARTEIRA_PASSWORD_HASH`, valor: `d70007eacadb5487ce0cea5acdf0b0c275b4bdb41f75b3080ab36b7d20ab6a4f` (hash da senha `qbJzilxNjMeqMaZ4` — guarde essa senha, é a que você digita na página `/carteira.html`; pode trocar por outra senha sua, gerando o hash com `python3 -c "import hashlib; print(hashlib.sha256('SUA-SENHA'.encode()).hexdigest())"`).
   - Marque os três como **Secret** (não "Text"), pra não ficarem visíveis depois de salvos.
8. Depois de salvar, a URL do seu Worker aparece no topo da página (algo como `https://antesdosino-diario-auth.SEU-SUBDOMINIO.workers.dev`). **Copie essa URL e me envie** — é o que falta pra ligar `docs/diario.html` e `docs/carteira.html` a esse Worker.

## Alternativa: linha de comando (wrangler)

Se preferir CLI em vez do painel:

```bash
cd worker
npm install -g wrangler
wrangler login
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put DECISOES_ENCRYPTION_KEY
wrangler secret put CARTEIRA_PASSWORD_HASH
wrangler deploy
```

## Por que precisa disso

O Telegram Login Widget devolve um payload assinado (hash HMAC-SHA256
com chave `SHA256(token_do_bot)`). Verificar essa assinatura exige o
token do bot — e o token do bot **nunca** pode estar no navegador
(quem tivesse acesso ao código-fonte da página poderia lê-lo e usá-lo
pra qualquer coisa em nome do bot). Por isso a verificação roda aqui,
num servidor, e não em `docs/theme.js` ou `docs/terminal.js`.

Pela mesma razão, a senha da Carteira de Dividendos é verificada aqui
(comparando o hash) em vez de embutida em texto puro no HTML de
`docs/carteira.html` — senão qualquer um que abrisse o código-fonte da
página veria a senha.

O Worker também é o único lugar que decifra `decisoes_usuarios.json`
e `carteira_status.json` (que ficam sempre criptografados no
repositório) — e devolve pro navegador só o que cada rota precisa,
nunca os arquivos inteiros sem verificação.
