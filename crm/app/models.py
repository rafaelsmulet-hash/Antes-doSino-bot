"""
Modelos de dados do CRM offline da mesa de sales trading.

Papeis de usuario (User.role):
    trader       -> ve apenas sua carteira de clientes (mais compartilhados)
    head_mesa    -> ve toda a mesa
    compliance   -> ve toda a mesa, com trilha de acesso

Interacao e append-only: uma correcao nunca edita/apaga o registro
original, apenas cria uma nova linha com `corrige_interacao_id` apontando
para a interacao corrigida (ver app/crud.py).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

ROLES = ("trader", "head_mesa", "compliance")
TIPOS_CLIENTE = ("PF", "PJ", "FUNDO")
CANAIS_INTERACAO = ("telefone", "presencial", "chat_interno", "email", "outro")
SENTIMENTOS = ("comprador", "vendedor", "neutro")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # ROLES
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    clientes_titular: Mapped[list["Cliente"]] = relationship(
        back_populates="trader_titular", foreign_keys="Cliente.trader_titular_id"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(64), unique=True)


class ClienteTag(Base):
    __tablename__ = "cliente_tags"

    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    tipo: Mapped[str] = mapped_column(String(8))  # TIPOS_CLIENTE
    book: Mapped[str | None] = mapped_column(String(64), nullable=True)
    perfil_risco: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trader_titular_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    data_cadastro: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    trader_titular: Mapped["User"] = relationship(
        back_populates="clientes_titular", foreign_keys=[trader_titular_id]
    )
    tags: Mapped[list["Tag"]] = relationship(secondary="cliente_tags")
    produtos: Mapped[list["ClienteProduto"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    compartilhamentos: Mapped[list["ClienteCompartilhamento"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )


class ClienteProduto(Base):
    __tablename__ = "cliente_produtos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    produto: Mapped[str] = mapped_column(String(64))

    cliente: Mapped["Cliente"] = relationship(back_populates="produtos")


class ClienteCompartilhamento(Base):
    """Compartilhamento explicito de um cliente com outro trader (view-only)."""

    __tablename__ = "cliente_compartilhamentos"
    __table_args__ = (UniqueConstraint("cliente_id", "user_id", name="uq_cliente_user_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="compartilhamentos")
    user: Mapped["User"] = relationship()


class Handoff(Base):
    """Transferencia temporaria de cobertura entre traders (item 6 da
    Fase 3) -- ex: ferias, ausencia.

    Se `cliente_id` for nulo, o handoff cobre toda a carteira do trader de
    origem; se preenchido, cobre apenas aquele cliente especifico. Enquanto
    ativo (fim nulo ou no futuro), `trader_destino` ganha acesso de
    leitura/escrita equivalente ao titular (ver app/crud.py). Ao encerrar
    (preencher `fim`), o acesso reverte automaticamente -- nao ha nenhuma
    edicao de registro, apenas a passagem do tempo ou o preenchimento do
    campo `fim`."""

    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trader_origem_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trader_destino_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True, index=True)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inicio: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    fim: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    trader_origem: Mapped["User"] = relationship(foreign_keys=[trader_origem_id])
    trader_destino: Mapped["User"] = relationship(foreign_keys=[trader_destino_id])
    autorizado_por: Mapped["User"] = relationship(foreign_keys=[autorizado_por_id])
    cliente: Mapped["Cliente | None"] = relationship()

    def ativo(self, agora: dt.datetime | None = None) -> bool:
        agora = agora or dt.datetime.utcnow()
        return self.fim is None or self.fim > agora


class Interacao(Base):
    """Log de interacao com cliente. Append-only: nunca editar/apagar."""

    __tablename__ = "interacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    canal: Mapped[str] = mapped_column(String(32))  # CANAIS_INTERACAO
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
    resumo: Mapped[str] = mapped_column(Text)
    tickers_mencionados: Mapped[str | None] = mapped_column(String(255), nullable=True)  # CSV
    sentimento: Mapped[str | None] = mapped_column(String(16), nullable=True)  # SENTIMENTOS
    follow_up_data: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    corrige_interacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("interacoes.id"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship()
    trader: Mapped["User"] = relationship()

    def tickers_lista(self) -> list[str]:
        if not self.tickers_mencionados:
            return []
        return [t.strip().upper() for t in self.tickers_mencionados.split(",") if t.strip()]


class NotaInterna(Base):
    """Nota interna da mesa vinculada a um cliente (item 7 da Fase 3).

    Nunca visivel externamente -- a interface deixa isso explicito
    ("nota interna, nao enviar ao cliente"). Append-only, como o log de
    interacao. Visibilidade segue exatamente a mesma regra de acesso ao
    cliente (trader titular, head_mesa, compliance, handoff ativo ou
    compartilhamento explicito -- ver app/crud.pode_ver_cliente)."""

    __tablename__ = "notas_internas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    cliente: Mapped["Cliente"] = relationship()
    autor: Mapped["User"] = relationship()


class PostagemMural(Base):
    """Postagem curta do mural interno da mesa (item 8 da Fase 3).

    Deliberadamente so tem um campo de texto livre, sem nenhuma referencia
    estruturada (FK) a cliente ou posicao -- o mural e para avisos e
    alertas do tipo "saiu research bom para o ticker Y, quem tem cliente
    nesse setor?", nao para extrato de carteira. Cabe ao autor nao colar
    dado sensivel de posicao no texto; a ausencia de FK para Posicao
    torna estruturalmente impossivel a postagem "puxar" um extrato.
    Visivel a todos os traders da mesa. Append-only."""

    __tablename__ = "postagens_mural"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    texto: Mapped[str] = mapped_column(String(500))
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    autor: Mapped["User"] = relationship()


MOTIVOS_ACESSO = ("TITULAR", "COMPARTILHADO", "HANDOFF", "HEAD_MESA", "COMPLIANCE")


class AccessLog(Base):
    """Trilha de auditoria (item 10 da Fase 3): quem acessou dados de qual
    cliente, quando, e por qual motivo (carteira titular, compartilhamento
    explicito, handoff de cobertura ativo, ou visao ampla de head_mesa /
    compliance). Append-only -- nunca editado ou apagado; a retencao segue
    a politica de compliance da instituicao (fora do escopo deste
    software, e responsabilidade operacional de quem administra o banco)."""

    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True, index=True)
    acao: Mapped[str] = mapped_column(String(64))
    motivo: Mapped[str | None] = mapped_column(String(16), nullable=True)  # MOTIVOS_ACESSO
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)

    user: Mapped["User"] = relationship()
    cliente: Mapped["Cliente | None"] = relationship()


# ---------------------------------------------------------------------------
# Fase 2 -- posicao e derivativos (modelo de dados). O CRM apenas exibe o que
# foi importado da fonte oficial (backoffice/custodia); nunca calcula
# posicao a partir dos proprios dados do CRM.
# ---------------------------------------------------------------------------


class Posicao(Base):
    """Posicao corrente em ativos a vista (acoes, ETFs, FIIs)."""

    __tablename__ = "posicoes"
    __table_args__ = (
        UniqueConstraint("cliente_id", "ticker", "data_referencia", name="uq_posicao_dia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    tipo_ativo: Mapped[str] = mapped_column(String(16))  # ACAO, ETF, FII
    quantidade: Mapped[float] = mapped_column(Float)
    preco_medio: Mapped[float] = mapped_column(Float)
    preco_atual: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_mercado: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_nao_realizado: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_referencia: Mapped[dt.date] = mapped_column(Date, index=True)


class PosicaoHistorico(Base):
    """Snapshot diario de posicao. Nunca sobrescrever -- uma linha por dia."""

    __tablename__ = "posicoes_historico"
    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "ticker", "data_snapshot", name="uq_posicao_hist_dia"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    tipo_ativo: Mapped[str] = mapped_column(String(16))
    quantidade: Mapped[float] = mapped_column(Float)
    preco_medio: Mapped[float] = mapped_column(Float)
    preco_atual: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_mercado: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_nao_realizado: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_referencia: Mapped[dt.date] = mapped_column(Date)
    data_snapshot: Mapped[dt.date] = mapped_column(Date, index=True)


class PosicaoDerivativo(Base):
    __tablename__ = "posicoes_derivativos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    ticker_ativo_objeto: Mapped[str] = mapped_column(String(24), index=True)
    tipo_derivativo: Mapped[str] = mapped_column(String(16))  # CALL, PUT, TERMO, FUTURO
    codigo_serie: Mapped[str] = mapped_column(String(24))
    direcao: Mapped[str] = mapped_column(String(16))  # COMPRADO, VENDIDO
    quantidade: Mapped[float] = mapped_column(Float)
    strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_vencimento: Mapped[dt.date] = mapped_column(Date, index=True)
    preco_medio_pago: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_referencia: Mapped[dt.date] = mapped_column(Date, index=True)


class PosicaoAluguel(Base):
    __tablename__ = "posicoes_aluguel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    quantidade: Mapped[float] = mapped_column(Float)
    posicao: Mapped[str] = mapped_column(String(16))  # DOADOR, TOMADOR
    taxa_aluguel: Mapped[float] = mapped_column(Float)
    data_inicio: Mapped[dt.date] = mapped_column(Date)
    data_vencimento: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    data_referencia: Mapped[dt.date] = mapped_column(Date, index=True)


class ImportacaoExecucao(Base):
    """Um rodada do job de importacao de posicao (item 1 da Fase 2).

    Guarda os totais da rodada; o detalhe de cada linha rejeitada fica em
    ImportacaoLinhaRejeitada. Nada aqui e sobrescrito -- cada execucao do
    job gera uma linha nova, formando o historico de importacoes.
    """

    __tablename__ = "importacao_execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arquivo: Mapped[str] = mapped_column(String(255))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
    total_lido: Mapped[int] = mapped_column(Integer, default=0)
    total_importado: Mapped[int] = mapped_column(Integer, default=0)
    total_rejeitado: Mapped[int] = mapped_column(Integer, default=0)

    rejeitadas: Mapped[list["ImportacaoLinhaRejeitada"]] = relationship(
        back_populates="execucao", cascade="all, delete-orphan"
    )


class ImportacaoLinhaRejeitada(Base):
    """Linha do arquivo de posicao que nao pode ser importada, com o motivo.

    Nunca falha silenciosamente: toda linha invalida (formato ruim,
    cliente nao cadastrado no CRM etc.) fica registrada aqui para
    conferencia posterior, em vez de ser descartada sem rastro.
    """

    __tablename__ = "importacao_linhas_rejeitadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("importacao_execucoes.id"), index=True)
    numero_linha: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(Text)
    conteudo: Mapped[str] = mapped_column(Text)  # linha bruta serializada em JSON

    execucao: Mapped["ImportacaoExecucao"] = relationship(back_populates="rejeitadas")
