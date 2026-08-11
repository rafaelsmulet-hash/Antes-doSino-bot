"""
Parser flexivel de importacao de posicao (item 1 da Fase 2).

O formato exato do arquivo gerado pelo backoffice/custodia pode variar
entre instituicoes e ao longo do tempo -- por isso o mapeamento de
colunas e um parametro (`ColumnMapping`), nunca hardcoded. O parser em si
so sabe ler CSV/TXT delimitado e normalizar tipos; ele nao calcula
posicao nenhuma -- apenas transcreve o que veio da fonte oficial.

Duas categorias de problema sao tratadas de forma diferente:

    - Erro estrutural (arquivo vazio, coluna obrigatoria ausente do
      mapeamento, nenhuma fonte de data de referencia configurada):
      levanta `PositionImportError` imediatamente, sem processar nenhuma
      linha -- isso sinaliza um problema de configuracao do mapeamento,
      nao um problema pontual do arquivo do dia.
    - Erro de linha (valor numerico invalido, data invalida, cliente sem
      codigo): a linha e desviada para `ResultadoImportacao.rejeitadas`
      com o motivo, e o parser continua processando as linhas seguintes.
      Isso evita que uma linha suja derrube a importacao inteira do dia.

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
    """Erro estrutural do arquivo/mapeamento -- nao ha linha para salvar."""


@dataclasses.dataclass
class PosicaoImportada:
    cliente_codigo: str
    ticker: str
    tipo_ativo: str
    quantidade: float
    preco_medio: float
    preco_atual: Optional[float]
    data_referencia: dt.date
    numero_linha: int


@dataclasses.dataclass
class LinhaRejeitada:
    """Linha que nao pode ser importada, com o motivo para diagnostico.

    O conteudo bruto da linha e preservado para permitir que quem chama
    (script de importacao) registre a rejeicao em log/tabela de auditoria
    sem precisar reabrir o arquivo original.
    """

    numero_linha: int
    motivo: str
    conteudo: dict


@dataclasses.dataclass
class ResultadoImportacao:
    posicoes: list[PosicaoImportada]
    rejeitadas: list[LinhaRejeitada]

    @property
    def total_lido(self) -> int:
        return len(self.posicoes) + len(self.rejeitadas)


class _ErroDeLinha(Exception):
    """Erro interno de uma unica linha -- nunca escapa de parse_position_file."""


_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def parse_position_file(
    origem: Union[str, Path, TextIO, Iterable[str]],
    mapping: ColumnMapping,
    data_referencia_padrao: Optional[dt.date] = None,
) -> ResultadoImportacao:
    """Le um arquivo de posicao e devolve posicoes validas + linhas rejeitadas.

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

    if not mapping.data_referencia and data_referencia_padrao is None:
        raise PositionImportError(
            "Nenhuma coluna de data de referencia mapeada e nenhuma "
            "data_referencia_padrao informada -- ajuste o mapeamento ou "
            "informe a data do job de importacao."
        )

    posicoes: list[PosicaoImportada] = []
    rejeitadas: list[LinhaRejeitada] = []

    for numero_linha, linha in enumerate(leitor, start=2):  # linha 1 = cabecalho
        if _linha_vazia(linha):
            continue
        try:
            posicoes.append(_processar_linha(linha, mapping, numero_linha, data_referencia_padrao))
        except _ErroDeLinha as exc:
            rejeitadas.append(
                LinhaRejeitada(numero_linha=numero_linha, motivo=str(exc), conteudo=dict(linha))
            )

    return ResultadoImportacao(posicoes=posicoes, rejeitadas=rejeitadas)


def _processar_linha(linha, mapping, numero_linha, data_referencia_padrao) -> PosicaoImportada:
    cliente_codigo = (linha.get(mapping.cliente_codigo) or "").strip()
    ticker = (linha.get(mapping.ticker) or "").strip().upper()
    tipo_ativo = (linha.get(mapping.tipo_ativo) or "").strip().upper()
    if not cliente_codigo or not ticker or not tipo_ativo:
        raise _ErroDeLinha("cliente_codigo, ticker e tipo_ativo sao obrigatorios.")

    quantidade = _parse_numero(linha[mapping.quantidade], mapping.separador_decimal, mapping.quantidade)
    preco_medio = _parse_numero(linha[mapping.preco_medio], mapping.separador_decimal, mapping.preco_medio)

    preco_atual = None
    if mapping.preco_atual and (linha.get(mapping.preco_atual) or "").strip():
        preco_atual = _parse_numero(linha[mapping.preco_atual], mapping.separador_decimal, mapping.preco_atual)

    if mapping.data_referencia and (linha.get(mapping.data_referencia) or "").strip():
        data_referencia = _parse_data(linha[mapping.data_referencia])
    else:
        data_referencia = data_referencia_padrao

    return PosicaoImportada(
        cliente_codigo=cliente_codigo,
        ticker=ticker,
        tipo_ativo=tipo_ativo,
        quantidade=quantidade,
        preco_medio=preco_medio,
        preco_atual=preco_atual,
        data_referencia=data_referencia,
        numero_linha=numero_linha,
    )


def _parse_numero(valor: str, separador_decimal: str, campo: str) -> float:
    bruto = valor
    valor = (valor or "").strip().replace(" ", "")
    if not valor:
        raise _ErroDeLinha(f"campo '{campo}' esta vazio.")
    if separador_decimal == ",":
        limpo = valor.replace(".", "").replace(",", ".")
    else:
        limpo = valor.replace(",", "")
    try:
        return float(limpo)
    except ValueError as exc:
        raise _ErroDeLinha(f"valor numerico invalido em '{campo}': {bruto!r}") from exc


def _parse_data(valor: str) -> dt.date:
    valor = valor.strip()
    for fmt in _FORMATOS_DATA:
        try:
            return dt.datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    raise _ErroDeLinha(f"data invalida: {valor!r} (formatos aceitos: {_FORMATOS_DATA})")


def _linha_vazia(linha: dict) -> bool:
    return all((v is None or not str(v).strip()) for v in linha.values())


def _abrir_linhas(origem) -> list[str]:
    if isinstance(origem, (str, Path)):
        with open(origem, "r", encoding="utf-8-sig", newline="") as f:
            return f.readlines()
    if hasattr(origem, "read"):
        return origem.readlines()
    return list(origem)
