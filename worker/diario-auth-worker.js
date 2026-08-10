/**
 * Antes do Sino - Worker de autenticacao (Diario de Decisao + Carteira
 * de Dividendos, ferramenta pessoal do dono do projeto)
 * =============================================================
 * Duas rotas, mesmo Worker (nao precisa criar um segundo):
 *
 *   POST /telegram-login (ou raiz "/", pra compatibilidade)
 *     Verifica o login do Telegram Login Widget (assinatura HMAC, que
 *     so pode ser checada com o token do bot - por isso roda aqui, nunca
 *     no navegador) e devolve SO os registros daquele chat_id em
 *     decisoes_usuarios.json (nunca o arquivo inteiro).
 *
 *   POST /carteira
 *     Verifica uma senha simples (hash SHA-256, pagina de uso pessoal
 *     do dono - nao e multiusuario) e devolve carteira_status.json
 *     inteiro (dado ja e todo do dono, sem necessidade de filtrar por
 *     usuario).
 *
 * Sem banco de dados proprio: busca os arquivos direto do GitHub a
 * cada request (repositorio publico, sem autenticacao) e decifra em
 * memoria - os arquivos no repo ficam sempre criptografados
 * (Fernet/AES), nunca em texto puro.
 *
 * Secrets necessarios (Settings do Worker, nunca no codigo):
 *   TELEGRAM_BOT_TOKEN      - o mesmo token do bot (ja existe como
 *                             secret do GitHub Actions, precisa ser
 *                             duplicado aqui)
 *   DECISOES_ENCRYPTION_KEY - a mesma chave Fernet usada pelo main.py
 *                             (idem, duplicar aqui) - usada pros dois
 *                             arquivos (decisoes_usuarios.json e
 *                             carteira_status.json)
 *   CARTEIRA_PASSWORD_HASH  - hash SHA-256 (hex) da senha da pagina
 *                             /carteira - NUNCA a senha em texto puro
 *
 * Variavel opcional (Settings > Variables, nao-secreta):
 *   GITHUB_RAW_URL          - default abaixo; so muda se o repo for renomeado.
 */

const GITHUB_RAW_BASE_DEFAULT =
  "https://raw.githubusercontent.com/rafaelsmulet-hash/Antes-doSino-bot/main/";

const ALLOWED_ORIGIN = "https://antesdosino.com.br";
const AUTH_MAX_AGE_SEGUNDOS = 24 * 60 * 60; // login do widget expira em 24h

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

// ---------------------------------------------------------------------
// Verificacao do Telegram Login Widget
// https://core.telegram.org/widgets/login#checking-authorization
// ---------------------------------------------------------------------

function bytesToHex(bytes) {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256(keyBytes, msgBytes) {
  const key = await crypto.subtle.importKey(
    "raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  return crypto.subtle.sign("HMAC", key, msgBytes);
}

async function verificarLoginTelegram(dados, botToken) {
  const { hash, ...resto } = dados;
  if (!hash) return false;

  const dataCheckString = Object.keys(resto)
    .sort()
    .map((k) => k + "=" + resto[k])
    .join("\n");

  const secretKey = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(botToken));
  const assinaturaCalculada = await hmacSha256(secretKey, new TextEncoder().encode(dataCheckString));
  const hashCalculado = bytesToHex(assinaturaCalculada);

  if (hashCalculado !== hash) return false;

  const authDate = parseInt(resto.auth_date, 10);
  const agora = Math.floor(Date.now() / 1000);
  if (!authDate || agora - authDate > AUTH_MAX_AGE_SEGUNDOS) return false;

  return true;
}

// ---------------------------------------------------------------------
// Decifra Fernet (mesmo formato da lib "cryptography" do Python,
// implementado aqui via WebCrypto - sem dependencia externa):
//   token base64url = versao(1) + timestamp(8) + iv(16) + ciphertext + hmac(32)
//   chave base64url (32 bytes) = signing_key(16) + encryption_key(16)
// ---------------------------------------------------------------------

function base64urlToBytes(b64url) {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "==".slice(0, (4 - (b64.length % 4)) % 4);
  const bin = atob(padded);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function fernetDecrypt(tokenB64url, chaveB64url) {
  const chave = base64urlToBytes(chaveB64url);
  const signingKey = chave.slice(0, 16);
  const encryptionKey = chave.slice(16, 32);

  const token = base64urlToBytes(tokenB64url);
  const versao = token[0];
  if (versao !== 0x80) throw new Error("versao Fernet inesperada");

  const iv = token.slice(9, 25);
  const ciphertext = token.slice(25, token.length - 32);
  const hmacRecebido = token.slice(token.length - 32);
  const semHmac = token.slice(0, token.length - 32);

  const hmacCalculado = new Uint8Array(await hmacSha256(signingKey, semHmac));
  if (bytesToHex(hmacCalculado) !== bytesToHex(hmacRecebido)) {
    throw new Error("HMAC do token invalido - chave errada ou dado corrompido");
  }

  const key = await crypto.subtle.importKey("raw", encryptionKey, { name: "AES-CBC" }, false, ["decrypt"]);
  const plainBuffer = await crypto.subtle.decrypt({ name: "AES-CBC", iv }, key, ciphertext);
  return new TextDecoder().decode(plainBuffer);
}

// ---------------------------------------------------------------------
// Senha simples (pagina de uso pessoal, single-user - nao precisa de
// OAuth). So o HASH fica salvo como secret, nunca a senha em si.
// ---------------------------------------------------------------------

async function verificarSenha(senhaRecebida, hashEsperado) {
  if (!senhaRecebida || !hashEsperado) return false;
  const hashCalculado = bytesToHex(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(senhaRecebida))
  );
  // Comparacao em tempo constante (evita vazar por timing o quanto do
  // hash bateu) - tamanho dos dois e sempre igual (hex de SHA-256).
  if (hashCalculado.length !== hashEsperado.length) return false;
  let diferenca = 0;
  for (let i = 0; i < hashCalculado.length; i++) {
    diferenca |= hashCalculado.charCodeAt(i) ^ hashEsperado.charCodeAt(i);
  }
  return diferenca === 0;
}

// ---------------------------------------------------------------------

async function buscarEDecifrar(nomeArquivo, chaveFernet, env) {
  const base = env.GITHUB_RAW_URL || GITHUB_RAW_BASE_DEFAULT;
  const resposta = await fetch(base + nomeArquivo, { cf: { cacheTtl: 0 } });
  if (!resposta.ok) return null;
  const tokenCriptografado = (await resposta.text()).trim();
  if (!tokenCriptografado) return null;
  const textoPlano = await fernetDecrypt(tokenCriptografado, chaveFernet);
  return JSON.parse(textoPlano);
}

async function tratarLoginTelegram(request, env) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.DECISOES_ENCRYPTION_KEY) {
    return jsonResponse({ erro: "Worker nao configurado (secrets ausentes)" }, 500);
  }

  let dadosLogin;
  try {
    dadosLogin = await request.json();
  } catch (e) {
    return jsonResponse({ erro: "Corpo da requisicao invalido" }, 400);
  }

  const valido = await verificarLoginTelegram(dadosLogin, env.TELEGRAM_BOT_TOKEN);
  if (!valido) {
    return jsonResponse({ erro: "Login invalido ou expirado" }, 401);
  }

  const chatId = String(dadosLogin.id);

  let estado;
  try {
    estado = await buscarEDecifrar("decisoes_usuarios.json", env.DECISOES_ENCRYPTION_KEY, env);
  } catch (e) {
    return jsonResponse({ erro: "Nao foi possivel ler os dados agora" }, 500);
  }
  if (!estado) return jsonResponse({ decisoes: [] });

  const minhasDecisoes = (estado.decisoes || []).filter((d) => String(d.chat_id) === chatId);
  return jsonResponse({ decisoes: minhasDecisoes });
}

async function tratarCarteira(request, env) {
  if (!env.CARTEIRA_PASSWORD_HASH || !env.DECISOES_ENCRYPTION_KEY) {
    return jsonResponse({ erro: "Worker nao configurado (secrets ausentes)" }, 500);
  }

  let corpo;
  try {
    corpo = await request.json();
  } catch (e) {
    return jsonResponse({ erro: "Corpo da requisicao invalido" }, 400);
  }

  const valido = await verificarSenha(corpo.senha, env.CARTEIRA_PASSWORD_HASH);
  if (!valido) {
    return jsonResponse({ erro: "Senha invalida" }, 401);
  }

  let status;
  try {
    status = await buscarEDecifrar("carteira_status.json", env.DECISOES_ENCRYPTION_KEY, env);
  } catch (e) {
    return jsonResponse({ erro: "Nao foi possivel ler os dados agora" }, 500);
  }

  return jsonResponse(status || { alocacao: [], universo: [] });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }
    if (request.method !== "POST") {
      return jsonResponse({ erro: "Metodo nao permitido" }, 405);
    }

    const { pathname } = new URL(request.url);
    if (pathname === "/carteira") {
      return tratarCarteira(request, env);
    }
    return tratarLoginTelegram(request, env);
  },
};
