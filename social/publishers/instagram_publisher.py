"""
Instagram Publisher - Antes do Sino (PLACEHOLDER)
====================================================

Ainda NAO implementado. Existe so para o publisher manager ja
conseguir rotear platform="instagram" sem quebrar, e para deixar
claro qual e a interface esperada quando for implementado de verdade.

Quando for implementar: a API do Instagram (Graph API / Content
Publishing API da Meta) exige conta Business/Creator vinculada a uma
Pagina do Facebook, e o fluxo de publicacao de carrossel e assincrono
(cria os media containers, depois publica) - bem mais complexo que o
X. Fica para uma proxima fase.
"""


def credenciais_configuradas():
    return False


def publicar_conteudo(item, sessao=None):
    """Interface identica ao x_publisher.publicar_conteudo - mesmo
    formato de retorno, para o manager tratar os dois de forma
    uniforme."""
    return {
        "success": False,
        "url": None,
        "error": "Publicação automática do Instagram ainda não implementada.",
    }

