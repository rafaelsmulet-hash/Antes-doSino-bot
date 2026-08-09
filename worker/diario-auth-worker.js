/**
 * Antes do Sino - Diario de Decisao - Worker de autenticacao
 * =============================================================
 * Unico proposito deste Worker: verificar o login do Telegram Login
 * Widget (assinatura HMAC, que so pode ser checada com o token do bot
 * - por isso tem que rodar num servidor, nunca no navegador) e, se
 * valido, devolver SO os registros daquele chat_id em
 * decisoes_usuarios.json (nunca o arquivo inteiro).
 *
 * Sem banco de dados proprio: busca decisoes_usuarios.json direto do
 * GitHub a cada request (repositorio publico, sem autenticacao) e
 * decifra em memoria - o arquivo no repo fica sempre criptografado
 * (Fernet/AES), nunca em texto puro.
 *
 * Secrets necessarios (Settings do Worker, nunca no codigo):
 *   TELEGRAM_BOT_TOKEN      - o mesmo token do bot (ja existe como
 *                             secret do GitHub Actions, precisa ser
 *                             duplicado aqui)
 *   DECISOES_ENCRYPTION_KEY - a mesma chave Fernet usada pelo main.py
 *                             (idem, duplicar aqui)
 *
 * Variavel opcional (Settings > Variables, nao-secreta):
 *   GITHUB_RAW_URL - default abaixo; so muda se o repo for renomeado.
 */

const GITHUB_RAW_URL_DEFAULT =
  "https://raw.githubusercontent.com/rafaelsmulet-hash/Antes-doSino-bot/main/decisoes_usuarios.json";

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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }
    if (request.method !== "POST") {
      return jsonResponse({ erro: "Metodo nao permitido" }, 405);
    }
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

    let respostaGithub;
    try {
      respostaGithub = await fetch(env.GITHUB_RAW_URL || GITHUB_RAW_URL_DEFAULT, {
        cf: { cacheTtl: 0 },
      });
    } catch (e) {
      return jsonResponse({ erro: "Nao foi possivel buscar os dados agora" }, 502);
    }
    if (!respostaGithub.ok) {
      // Arquivo pode nao existir ainda (ninguem registrou decisao nenhuma) -
      // nao e erro, so nao ha nada pra mostrar.
      return jsonResponse({ decisoes: [] });
    }

    const tokenCriptografado = (await respostaGithub.text()).trim();
    if (!tokenCriptografado) {
      return jsonResponse({ decisoes: [] });
    }

    let estado;
    try {
      const textoPlano = await fernetDecrypt(tokenCriptografado, env.DECISOES_ENCRYPTION_KEY);
      estado = JSON.parse(textoPlano);
    } catch (e) {
      return jsonResponse({ erro: "Nao foi possivel ler os dados agora" }, 500);
    }

    const minhasDecisoes = (estado.decisoes || []).filter(
      (d) => String(d.chat_id) === chatId
    );

    return jsonResponse({ decisoes: minhasDecisoes });
  },
};
