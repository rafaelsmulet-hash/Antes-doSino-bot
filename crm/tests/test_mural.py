from app import models
from tests.conftest import SENHA_PADRAO_TESTE, criar_trader, login
from sqlalchemy import select


class TestMuralDaMesa:
    def test_qualquer_trader_pode_publicar_e_todos_veem(self, client, db_session):
        autor = criar_trader(db_session, "Autor Mural")
        leitor = criar_trader(db_session, "Leitor Mural")

        login(client, autor.username, SENHA_PADRAO_TESTE)
        resp = client.post(
            "/mural",
            data={"texto": "Saiu research bom para VALE3, quem tem cliente no setor?"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        client.post("/logout")

        login(client, leitor.username, SENHA_PADRAO_TESTE)
        pagina = client.get("/mural")
        assert "Saiu research bom para VALE3" in pagina.text
        assert autor.full_name in pagina.text

    def test_texto_vazio_e_rejeitado(self, client, db_session):
        autor = criar_trader(db_session, "Autor Mural Vazio")
        login(client, autor.username, SENHA_PADRAO_TESTE)
        resp = client.post("/mural", data={"texto": "   "})
        assert resp.status_code == 400
        assert "caracteres" in resp.text

    def test_texto_acima_do_limite_e_rejeitado(self, client, db_session):
        autor = criar_trader(db_session, "Autor Mural Longo")
        login(client, autor.username, SENHA_PADRAO_TESTE)
        resp = client.post("/mural", data={"texto": "x" * 501})
        assert resp.status_code == 400

        postagens = db_session.execute(
            select(models.PostagemMural).where(models.PostagemMural.autor_id == autor.id)
        ).scalars().all()
        assert postagens == []

    def test_mural_requer_login(self, client):
        resp = client.get("/mural", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")

    def test_nao_existe_rota_de_edicao_ou_delecao_de_postagem(self, client, db_session):
        autor = criar_trader(db_session, "Autor Mural Append")
        login(client, autor.username, SENHA_PADRAO_TESTE)
        client.post("/mural", data={"texto": "Postagem original."})
        postagem = db_session.execute(
            select(models.PostagemMural).where(models.PostagemMural.autor_id == autor.id)
        ).scalars().first()
        assert client.put(f"/mural/{postagem.id}").status_code == 404
        assert client.delete(f"/mural/{postagem.id}").status_code == 404
