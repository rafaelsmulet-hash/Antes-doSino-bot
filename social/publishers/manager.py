"""
Publisher Manager - Antes do Sino
====================================

Camada intermediaria entre o content engine e os publishers
especificos de cada rede. O content engine chama so:

    publish(platform="x", item=item)

e o manager decide qual publisher acionar - novos canais entram so
adicionando uma linha no PUBLISHERS, sem tocar em mais nada.
"""

from social.publishers import x_publisher
from social.publishers import instagram_publisher
from social.publishers import tiktok_publisher

PUBLISHERS = {
    "x": x_publisher,
    "instagram": instagram_publisher,
    "tiktok": tiktok_publisher,
}


def publish(platform, item):
    """Publica o item na plataforma indicada. Retorna sempre
    {"success", "url", "error"} - nunca lanca excecao (qualquer
    publisher mal comportado e protegido por try/except aqui)."""
    publisher = PUBLISHERS.get((platform or "").lower())
    if publisher is None:
        return {
            "success": False,
            "url": None,
            "error": "Plataforma desconhecida: '" + str(platform) + "'. Disponiveis: " + ", ".join(PUBLISHERS.keys()),
        }

    try:
        return publisher.publicar_conteudo(item)
    except Exception as e:
        return {"success": False, "url": None, "error": "Erro inesperado no publisher '" + str(platform) + "': " + str(e)}
