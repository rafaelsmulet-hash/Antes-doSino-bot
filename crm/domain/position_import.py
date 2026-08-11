"""
Parser flexivel de importacao de posicao (item 5 da Fase 2).

O formato exato do arquivo gerado pelo backoffice/custodia pode variar
entre instituicoes e ao longo do tempo -- por isso o mapeamento de
colunas e um parametro (`ColumnMapping`), nunca hardcoded. O parser em si
so sabe ler CSV/TXT delimitado e normalizar tipos; ele nao calcula
posicao nenhuma -- apenas transcreve o que veio da fonte oficial.

Modulo isolado de banco de dados e do FastAPI, propositalmente testavel
sem infraestrutura externa.
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional, TextIO, Union


@dataclasses.dataclass
class ColumnMapping:
    """Mapeia nomes de coluna do arquivo de origem para os campos internos.

    `preco_atual` e `data_referencia` sao opcionais: se o arquivo nao tiver
    coluna de data de referencia, informe `data_referencia_padrao` ao
    chamar `parse_position_file` (tipicamente "hoje", no horario do job de
    importacao).
    """

    cliente_codigo: str
    ticker: str
    tipo_ativo: str
    quantidade: str
    preco_medio: str
    preco_atual: Optional[str] = None
    data_referencia: Optional[str] = None
    delimitador: str = ";"
    separador_decimal: str = ","  # "," (formato BR, ex: 1.234,56) ou "." (ex: 1234.56)


class PositionImportError(Exception):
    """Erro de importacao com contexto de linha/coluna para diagnostico rapido."""


@dataclasses.dataclass
class PosicaoImportada:
    cliente_codigo: str
    ticker: str
    tipo_ativo: str
    quantidade: float
    preco_medio: float
    preco_atual: Optional[float]
    data_referencia: dt.date


_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def parse_position_file(
    origem: Union[str, Path, TextIO, Iterable[str]],
    mapping: ColumnMapping,
    data_referencia_padrao: Optional[dt.date] = None,
) -> list[PosicaoImportada]:
    """Le um arquivo de posicao e devolve uma lista de posicoes normalizadas.

    `origem` pode ser um caminho de arquivo, um objeto arquivo ja aberto,
    ou qualquer iteravel de linhas de texto (usado nos testes).
    """
    linhas = _abrir_linhas(origem)
    leitor = csv.DictReader(linhas, delimiter=mapping.delimitador)

    if leitor.fieldnames is None:
        raise PositionImportError("Arquivo de posicao vazio ou sem cabecalho.")

    colunas_obrigatorias = [
        mapping.cliente_codigo,
        mapping.ticker,
        mapping.tipo_ativo,
        mapping.quantidade,
        mapping.preco_medio,
    ]
    faltando = [c for c in colunas_obrigatorias if c not in leitor.fieldnames]
    if faltando:
        raise PositionImportError(
            f"Colunas obrigatorias ausentes no arquivo: {faltando}. "
            f"Colunas encontradas: {leitor.fieldnames}. Ajuste o mapeamento de colunas."
        )

    resultado: list[PosicaoImportada] = []
    for numero_linha, linha in enumerate(leitor, start=2):  # linha 1 = cabecalho
        if _linha_vazia(linha):
            continue

        cliente_codigo = (linha.get(mapping.cliente_codigo) or "").strip()
        ticker = (linha.get(mapping.ticker) or "").strip().upper()
        tipo_ativo = (linha.get(mapping.tipo_ativo) or "").strip().upper()
        if not cliente_codigo or not ticker or not tipo_ativo:
            raise PositionImportError(
                f"Linha {numero_linha}: cliente_codigo, ticker e tipo_ativo sao obrigatorios."
            )

        quantidade = _parse_numero(
            linha[mapping.quantidade], mapping.separador_decimal, numero_linha, mapping.quantidade
        )
        preco_medio = _parse_numero(
            linha[mapping.preco_medio], mapping.separador_decimal, numero_linha, mapping.preco_medio
        )

        preco_atual = None
        if mapping.preco_atual and (linha.get(mapping.preco_atual) or "").strip():
            preco_atual = _parse_numero(
                linha[mapping.preco_atual], mapping.separador_decimal, numero_linha, mapping.preco_atual
            )

        if mapping.data_referencia and (linha.get(mapping.data_referencia) or "").strip():
            data_referencia = _parse_data(linha[mapping.data_referencia], numero_linha)
        elif data_referencia_padrao is not None:
            data_referencia = data_referencia_padrao
        else:
            raise PositionImportError(
                f"Linha {numero_linha}: sem coluna de data de referencia mapeada e "
                "nenhuma data_referencia_padrao informada."
            )

        resultado.append(
            PosicaoImportada(
                cliente_codigo=cliente_codigo,
                ticker=ticker,
                tipo_ativo=tipo_ativo,
                quantidade=quantidade,
                preco_medio=preco_medio,
                preco_atual=preco_atual,
                data_referencia=data_referencia,
            )
        )

    return resultado


def _parse_numero(valor: str, separador_decimal: str, linha: int, campo: str) -> float:
    bruto = valor
    valor = (valor or "").strip().replace(" ", "")
    if not valor:
        raise PositionImportError(f"Linha {linha}: campo '{campo}' esta vazio.")
    if separador_decimal == ",":
        limpo = valor.replace(".", "").replace(",", ".")
    else:
        limpo = valor.replace(",", "")
    try:
        return float(limpo)
    except ValueError as exc:
        raise PositionImportError(
            f"Linha {linha}: valor numerico invalido em '{campo}': {bruto!r}"
        ) from exc


def _parse_data(valor: str, linha: int) -> dt.date:
    valor = valor.strip()
    for fmt in _FORMATOS_DATA:
        try:
            return dt.datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    raise PositionImportError(
        f"Linha {linha}: data invalida: {valor!r} (formatos aceitos: {_FORMATOS_DATA})"
    )


def _linha_vazia(linha: dict) -> bool:
    return all((v is None or not str(v).strip()) for v in linha.values())


def _abrir_linhas(origem) -> list[str]:
    if isinstance(origem, (str, Path)):
        with open(origem, "r", encoding="utf-8-sig", newline="") as f:
            return f.readlines()
    if hasattr(origem, "read"):
        return origem.readlines()
    return list(origem)
