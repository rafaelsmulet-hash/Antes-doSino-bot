"""
Job de importacao diaria de posicao (item 1 da Fase 2).

Le um arquivo de posicao (CSV/TXT) depositado pelo backoffice/custodia em
uma pasta de rede interna, aplica o parser flexivel
(domain/position_import.py), resolve cada cliente pelo codigo cadastrado
no CRM, faz upsert em `Posicao` (posicao corrente) e insere um snapshot
em `PosicaoHistorico` (historico diario, nunca sobrescrito).

O CRM nunca calcula posicao -- este job so replica o que veio da fonte
oficial. Linhas invalidas (formato ruim) ou de cliente nao cadastrado no
CRM sao registradas em `ImportacaoExecucao`/`ImportacaoLinhaRejeitada`
em vez de derrubar a importacao inteira ou desaparecer sem rastro.

Uso tipico (agendado via cron/Task Scheduler do servidor interno da mesa,
no horario de abertura do pregao):

    python scripts/importar_posicoes.py /pasta/rede/interna/posicao_hoje.csv
    python scripts/importar_posicoes.py --config config/mapeamento_custodia_x.json /pasta/.../posicao.csv

O mapeamento de colunas por padrao e o definido em MAPEAMENTO_PADRAO
abaixo; para um backoffice com nomes de coluna diferentes, informe um
arquivo JSON via --config com as mesmas chaves de `ColumnMapping`
(cliente_codigo, ticker, tipo_ativo, quantidade, preco_medio,
preco_atual, data_referencia, delimitador, separador_decimal).
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from domain.position_import import (  # noqa: E402
    ColumnMapping,
    PosicaoImportada,
    parse_position_file,
)

MAPEAMENTO_PADRAO = ColumnMapping(
    cliente_codigo="cod_cliente",
    ticker="cod_ativo",
    tipo_ativo="tipo_ativo",
    quantidade="quantidade",
    preco_medio="preco_medio",
    preco_atual="preco_atual",
    delimitador=";",
    separador_decimal=",",
)


def carregar_mapeamento(caminho_config: Path | None) -> ColumnMapping:
    if caminho_config is None:
        return MAPEAMENTO_PADRAO
    dados = json.loads(caminho_config.read_text(encoding="utf-8"))
    return ColumnMapping(**dados)


def executar_importacao(
    db: Session,
    caminho_arquivo: Path,
    mapping: ColumnMapping,
    data_referencia_padrao: dt.date | None = None,
    data_snapshot: dt.date | None = None,
) -> models.ImportacaoExecucao:
    """Executa uma rodada de importacao e devolve o registro de execucao
    (ja commitado). Idempotente para o mesmo dia: rodar duas vezes no
    mesmo `data_snapshot` atualiza a posicao corrente mas nao duplica o
    snapshot historico."""
    data_snapshot = data_snapshot or dt.date.today()
    resultado = parse_position_file(caminho_arquivo, mapping, data_referencia_padrao=data_referencia_padrao)

    execucao = models.ImportacaoExecucao(
        arquivo=str(caminho_arquivo),
        timestamp=dt.datetime.utcnow(),
        total_lido=resultado.total_lido,
        total_importado=0,
        total_rejeitado=0,
    )
    db.add(execucao)
    db.flush()

    for rejeitada in resultado.rejeitadas:
        db.add(
            models.ImportacaoLinhaRejeitada(
                execucao_id=execucao.id,
                numero_linha=rejeitada.numero_linha,
                motivo=rejeitada.motivo,
                conteudo=json.dumps(rejeitada.conteudo, ensure_ascii=False),
            )
        )
    total_rejeitado = len(resultado.rejeitadas)
    total_importado = 0

    for posicao in resultado.posicoes:
        cliente = db.execute(
            select(models.Cliente).where(models.Cliente.codigo == posicao.cliente_codigo)
        ).scalar_one_or_none()
        if cliente is None:
            db.add(
                models.ImportacaoLinhaRejeitada(
                    execucao_id=execucao.id,
                    numero_linha=posicao.numero_linha,
                    motivo=f"cliente nao encontrado no CRM: codigo={posicao.cliente_codigo!r}",
                    conteudo=json.dumps(_serializar(posicao), ensure_ascii=False),
                )
            )
            total_rejeitado += 1
            continue

        _upsert_posicao_corrente(db, cliente.id, posicao)
        _inserir_snapshot_historico(db, cliente.id, posicao, data_snapshot)
        total_importado += 1

    execucao.total_importado = total_importado
    execucao.total_rejeitado = total_rejeitado
    db.commit()
    db.refresh(execucao)
    return execucao


def _serializar(posicao: PosicaoImportada) -> dict:
    dados = dataclasses.asdict(posicao)
    dados["data_referencia"] = dados["data_referencia"].isoformat()
    return dados


def _calcular_valor_mercado_e_pnl(posicao: PosicaoImportada) -> tuple[float | None, float | None]:
    if posicao.preco_atual is None:
        return None, None
    valor_mercado = posicao.preco_atual * posicao.quantidade
    pnl = (posicao.preco_atual - posicao.preco_medio) * posicao.quantidade
    return valor_mercado, pnl


def _upsert_posicao_corrente(db: Session, cliente_id: int, posicao: PosicaoImportada) -> None:
    existente = db.execute(
        select(models.Posicao).where(
            models.Posicao.cliente_id == cliente_id,
            models.Posicao.ticker == posicao.ticker,
            models.Posicao.data_referencia == posicao.data_referencia,
        )
    ).scalar_one_or_none()

    valor_mercado, pnl = _calcular_valor_mercado_e_pnl(posicao)

    if existente:
        existente.tipo_ativo = posicao.tipo_ativo
        existente.quantidade = posicao.quantidade
        existente.preco_medio = posicao.preco_medio
        existente.preco_atual = posicao.preco_atual
        existente.valor_mercado = valor_mercado
        existente.pnl_nao_realizado = pnl
    else:
        db.add(
            models.Posicao(
                cliente_id=cliente_id,
                ticker=posicao.ticker,
                tipo_ativo=posicao.tipo_ativo,
                quantidade=posicao.quantidade,
                preco_medio=posicao.preco_medio,
                preco_atual=posicao.preco_atual,
                valor_mercado=valor_mercado,
                pnl_nao_realizado=pnl,
                data_referencia=posicao.data_referencia,
            )
        )


def _inserir_snapshot_historico(
    db: Session, cliente_id: int, posicao: PosicaoImportada, data_snapshot: dt.date
) -> None:
    ja_existe = db.execute(
        select(models.PosicaoHistorico.id).where(
            models.PosicaoHistorico.cliente_id == cliente_id,
            models.PosicaoHistorico.ticker == posicao.ticker,
            models.PosicaoHistorico.data_snapshot == data_snapshot,
        )
    ).scalar_one_or_none()
    if ja_existe:
        return  # job ja rodou hoje para este cliente/ticker -- nunca duplica o historico

    valor_mercado, pnl = _calcular_valor_mercado_e_pnl(posicao)
    db.add(
        models.PosicaoHistorico(
            cliente_id=cliente_id,
            ticker=posicao.ticker,
            tipo_ativo=posicao.tipo_ativo,
            quantidade=posicao.quantidade,
            preco_medio=posicao.preco_medio,
            preco_atual=posicao.preco_atual,
            valor_mercado=valor_mercado,
            pnl_nao_realizado=pnl,
            data_referencia=posicao.data_referencia,
            data_snapshot=data_snapshot,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa posicao do backoffice/custodia para o CRM.")
    parser.add_argument("arquivo", type=str, help="Caminho do arquivo de posicao do dia.")
    parser.add_argument("--config", type=str, default=None, help="JSON com o mapeamento de colunas (ColumnMapping).")
    parser.add_argument(
        "--data-referencia",
        type=str,
        default=None,
        help="Data de referencia (AAAA-MM-DD) a usar quando o arquivo nao tiver coluna de data. Default: hoje.",
    )
    args = parser.parse_args()

    mapping = carregar_mapeamento(Path(args.config) if args.config else None)
    data_referencia_padrao = (
        dt.date.fromisoformat(args.data_referencia) if args.data_referencia else dt.date.today()
    )

    init_db()
    sessao = SessionLocal()
    try:
        execucao = executar_importacao(sessao, Path(args.arquivo), mapping, data_referencia_padrao)
    finally:
        sessao.close()

    print(
        f"Importacao concluida: {execucao.total_importado} posicoes importadas, "
        f"{execucao.total_rejeitado} linhas rejeitadas (de {execucao.total_lido} lidas). "
        f"Detalhe das rejeicoes na tabela importacao_linhas_rejeitadas (execucao_id={execucao.id})."
    )
