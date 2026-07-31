"""
X (Twitter) Publisher - Antes do Sino
========================================

Responsabilidades: autenticacao, upload de imagem, publicacao de
texto, retorno da URL publicada, tratamento de erro. Nunca deixa
credencial no codigo - tudo vem de variavel de ambiente:

    X_API_KEY
    X_API_SECRET
    X_ACCESS_TOKEN
    X_ACCESS_SECRET

Interface publica usada pelo publisher manager:
    publicar_conteudo(item, sessao=None) -> {"success": bool, "url": str|None, "error": str|None}

O parametro 'sessao' existe justamente para permitir teste com mock,
sem precisar de credencial real (injeta uma sessao falsa no lugar da
OAuth1Session de verdade).
"""

import os

X_API_KEY = os.environ.get("X_API_KEY", "")
X_API_SECRET = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET", "")

MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_CREATE_URL = "https://api.twitter.com/2/tweets"


def credenciais_configuradas():
    return bool(X_API_KEY and X_API_SECRET and X_ACCESS_TOKEN and X_ACCESS_SECRET)


def _autenticar():
    """Cria a sessao OAuth1 autenticada. Isolado numa funcao propria
    para poder ser facilmente substituida por um mock nos testes."""
    from requests_oauthlib import OAuth1Session
    return OAuth1Session(
        X_API_KEY,
        client_secret=X_API_SECRET,
        resource_owner_key=X_ACCESS_TOKEN,
        resource_owner_secret=X_ACCESS_SECRET,
    )


def _upload_media(sessao, caminho_imagem):
    """Faz upload de uma imagem via API v1.1 (a v2 ainda nao tem
    upload de midia direto) e retorna o media_id para anexar ao
    tweet. Lanca excecao com mensagem clara em caso de falha - quem
    chama trata e converte em resultado seguro."""
    with open(caminho_imagem, "rb") as f:
        response = sessao.post(MEDIA_UPLOAD_URL, files={"media": f})
    if response.status_code not in (200, 201):
        raise ValueError("Falha no upload de midia (HTTP " + str(response.status_code) + "): " + response.text)
    data = response.json()
    media_id = data.get("media_id_string")
    if not media_id:
        raise ValueError("Upload de midia nao retornou media_id: " + str(data))
    return media_id


def publicar_conteudo(item, sessao=None):
    """Publica o conteudo do item no X. Usa o texto de item['x']['post']
    e, se existir, a primeira imagem da pasta de design como midia.

    Retorna sempre um dict {"success", "url", "error"} - nunca lanca
    excecao para o chamador (publisher manager / content engine)."""
    if sessao is None and not credenciais_configuradas():
        return {
            "success": False,
            "url": None,
            "error": "Credenciais do X nao configuradas (X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_SECRET).",
        }

    texto = ((item.get("x") or {}).get("post") or "").strip()
    if not texto:
        return {"success": False, "url": None, "error": "Item nao tem texto para X (campo x.post vazio)."}

    try:
        sessao_ativa = sessao if sessao is not None else _autenticar()

        media_ids = []
        pasta = item.get("design_folder")
        if pasta:
            caminho_imagem = os.path.join(pasta, "slide_01.png")
            if os.path.exists(caminho_imagem):
                media_id = _upload_media(sessao_ativa, caminho_imagem)
                media_ids.append(media_id)

        payload = {"text": texto}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        response = sessao_ativa.post(TWEET_CREATE_URL, json=payload)

        if response.status_code not in (200, 201):
            return {
                "success": False,
                "url": None,
                "error": "Falha ao publicar tweet (HTTP " + str(response.status_code) + "): " + response.text,
            }

        data = response.json()
        tweet_id = (data.get("data") or {}).get("id")
        if not tweet_id:
            return {"success": False, "url": None, "error": "Resposta da API sem ID do tweet: " + str(data)}

        url_publicado = "https://x.com/i/web/status/" + str(tweet_id)
        return {"success": True, "url": url_publicado, "error": None}

    except Exception as e:
        return {"success": False, "url": None, "error": "Erro ao publicar no X: " + str(e)}
