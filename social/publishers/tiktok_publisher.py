"""
TikTok Publisher - Antes do Sino (PLACEHOLDER)
=================================================

Ainda NAO implementado. Existe so para o publisher manager ja
conseguir rotear platform="tiktok" sem quebrar.

Quando for implementar: o TikTok Content Posting API exige app
aprovado pela plataforma e, no caso deste projeto, geracao de VIDEO
(hoje o content engine so produz o roteiro em texto, nao o video em
si) - depende de uma etapa de geracao de video que ainda nao existe.
"""


def credenciais_configuradas():
    return False


def publicar_conteudo(item, sessao=None):
    """Interface identica ao x_publisher.publicar_conteudo."""
    return {
        "success": False,
        "url": None,
        "error": "Publicação automática do TikTok ainda não implementada.",
    }
