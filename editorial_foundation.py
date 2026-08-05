"""
Editorial Foundation - Fase 0 da nova arquitetura editorial (Antes do Sino)
================================================================================

Fundacao da nova arquitetura editorial (feed continuo -> servico de
acompanhamento). Consolidado num arquivo so, na raiz do repositorio,
por escolha deliberada - reduz o trabalho de criar multiplos arquivos
manualmente no GitHub. Continua SEPARADO do main.py (que deve apenas
orquestrar, nao concentrar logica nova).

FASE 0: todo o conteudo deste arquivo esta criado e testado, mas
NENHUMA funcao daqui e chamada por main.py ainda - fundacao isolada,
sem alterar nenhum comportamento atual do pipeline.

Contem, na ordem:
  1. Story State    - stories em andamento hoje (active_stories.json)
  2. Round Queue     - fila de itens aguardando checkpoint (round_queue.json)
  3. Decision Log    - auditoria de decisoes editoriais (ai_decisions_log.json)
  4. Source Tier     - mapeamento de prioridade (FEEDS) para tier semantico
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

BR_TZ = timezone(timedelta(hours=-3))


# =============================================================================
# 1) STORY STATE - stories de mercado em andamento hoje
#
# Conceito DIFERENTE do events_detected.json ja existente no main.py
# (que e uma agenda de eventos FUTUROS com data marcada, tipo Copom).
# Por isso o nome do arquivo e deliberadamente diferente
# (active_stories.json) - evita colisao conceitual entre "evento
# futuro na agenda" e "story em andamento agora".
# =============================================================================

ACTIVE_STORIES_FILE = "docs/active_stories.json"


def load_active_stories():
    """Carrega o estado de stories ativos. Se o arquivo nao existir ou
    estiver corrompido, retorna um estado vazio valido - nunca quebra
    o pipeline por causa disso."""
    if not os.path.exists(ACTIVE_STORIES_FILE):
        return {"stories": []}
    try:
        with open(ACTIVE_STORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "stories" not in data:
                return {"stories": []}
            return data
    except Exception as e:
        print("AVISO (story_state): falha ao carregar " + ACTIVE_STORIES_FILE + " (" + str(e) + "). Usando estado vazio.")
        return {"stories": []}


def save_active_stories(state):
    """Salva o estado de stories ativos. Cria o diretorio de destino
    se nao existir - nunca falha por causa de pasta ausente."""
    try:
        os.makedirs(os.path.dirname(ACTIVE_STORIES_FILE), exist_ok=True)
        with open(ACTIVE_STORIES_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("ERRO (story_state): falha ao salvar " + ACTIVE_STORIES_FILE + ": " + str(e))
        return False


def create_story(cluster_key, materiality_score=None, source=None):
    """Cria um novo registro de story - id estavel (uuid), pensado
    para migracao futura direta pra uma tabela SQL (1 story = 1 linha)
    sem precisar redesenhar o schema."""
    agora = datetime.now(BR_TZ).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "cluster_key": cluster_key,
        "first_seen": agora,
        "last_updated": agora,
        "materiality_peak": materiality_score,
        "sources_seen": [source] if source else [],
        "update_count": 1,
        "status": "active",
    }


def update_story(state, story_id, materiality_score=None, source=None):
    """Atualiza um story ja existente (por id) - atualiza last_updated,
    mantem o maior materiality_score ja visto (materiality_peak), e
    acumula fontes distintas que ja confirmaram a mesma story. Retorna
    o state atualizado (nao salva sozinho - quem chama decide quando
    persistir, evitando escrita em disco a cada chamada)."""
    for story in state.get("stories", []):
        if story["id"] == story_id:
            story["last_updated"] = datetime.now(BR_TZ).isoformat()
            story["update_count"] = story.get("update_count", 1) + 1
            if materiality_score is not None:
                peak_atual = story.get("materiality_peak")
                if peak_atual is None or materiality_score > peak_atual:
                    story["materiality_peak"] = materiality_score
            if source and source not in story.get("sources_seen", []):
                story.setdefault("sources_seen", []).append(source)
            break
    return state


def expire_old_stories(state, max_age_hours=24):
    """Remove stories cujo last_updated e mais antigo que max_age_hours
    - evita crescimento indefinido do arquivo. Retorna o state
    limpo (nao salva sozinho)."""
    agora = datetime.now(BR_TZ)
    cutoff = agora - timedelta(hours=max_age_hours)

    stories_mantidas = []
    for story in state.get("stories", []):
        try:
            ultima_atualizacao = datetime.fromisoformat(story["last_updated"])
            if ultima_atualizacao >= cutoff:
                stories_mantidas.append(story)
        except Exception:
            continue

    state["stories"] = stories_mantidas
    return state


def find_story_by_cluster_key(state, cluster_key):
    """Helper de busca - usado pela futura logica de clustering para
    decidir se uma noticia pertence a uma story ja ativa ou e nova."""
    for story in state.get("stories", []):
        if story.get("cluster_key") == cluster_key and story.get("status") == "active":
            return story
    return None


# =============================================================================
# 2) ROUND QUEUE - fila de itens aguardando o proximo checkpoint
# =============================================================================

ROUND_QUEUE_FILE = "docs/round_queue.json"


def get_round_queue():
    """Carrega a fila atual. Se o arquivo nao existir ou estiver
    corrompido, retorna uma fila vazia valida - nunca quebra o
    pipeline por causa disso."""
    if not os.path.exists(ROUND_QUEUE_FILE):
        return {"queue": []}
    try:
        with open(ROUND_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "queue" not in data:
                return {"queue": []}
            return data
    except Exception as e:
        print("AVISO (round_queue): falha ao carregar " + ROUND_QUEUE_FILE + " (" + str(e) + "). Usando fila vazia.")
        return {"queue": []}


def _save_round_queue(state):
    try:
        os.makedirs(os.path.dirname(ROUND_QUEUE_FILE), exist_ok=True)
        with open(ROUND_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("ERRO (round_queue): falha ao salvar " + ROUND_QUEUE_FILE + ": " + str(e))
        return False


def add_to_round_queue(item):
    """Adiciona 1 item a fila e persiste imediatamente. 'item' e um
    dict simples (title, source, materiality_score, etc) - o formato
    exato sera definido quando o materiality_score entrar (fase
    futura); por ora aceita qualquer dict serializavel."""
    state = get_round_queue()
    item_completo = dict(item)
    item_completo.setdefault("queued_at", datetime.now(BR_TZ).isoformat())
    state["queue"].append(item_completo)
    return _save_round_queue(state)


def clear_round_queue():
    """Esvazia a fila - usado depois que um checkpoint consome os
    itens acumulados."""
    return _save_round_queue({"queue": []})


def prioritize_queue(queue_items):
    """Ordena os itens da fila por prioridade - funcao PURA (nao le
    nem escreve arquivo), recebe uma lista e devolve outra ordenada.
    Hoje ordena por 'materiality_score' (maior primeiro, itens sem
    score vao pro fim) e, em empate, pelo mais antigo na fila primeiro
    (queued_at) - garante que nada fique esquecido indefinidamente."""
    def chave_ordenacao(item):
        score = item.get("materiality_score")
        score_para_ordenar = score if score is not None else -1
        return (-score_para_ordenar, item.get("queued_at", ""))

    return sorted(queue_items, key=chave_ordenacao)


# =============================================================================
# 3) DECISION LOG - auditoria de decisoes editoriais
# =============================================================================

DECISION_LOG_FILE = "docs/ai_decisions_log.json"
LIMITE_REGISTROS_MANTIDOS = 2000  # mesmo espirito do sent_items.json, evita crescimento indefinido
DECISOES_VALIDAS = ("breaking", "round", "discard")


def _load_decision_log():
    if not os.path.exists(DECISION_LOG_FILE):
        return {"decisions": []}
    try:
        with open(DECISION_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "decisions" not in data:
                return {"decisions": []}
            return data
    except Exception as e:
        print("AVISO (decision_log): falha ao carregar " + DECISION_LOG_FILE + " (" + str(e) + "). Usando log vazio.")
        return {"decisions": []}


def log_decision(title, source, score, motivo, decisao_sugerida, decisao_sistema_atual=None):
    """Registra 1 decisao editorial. 'decisao_sugerida' precisa ser
    'breaking', 'round' ou 'discard' - qualquer outro valor e
    normalizado para 'discard' com aviso, nunca quebra o registro por
    causa de um valor inesperado.

    'decisao_sistema_atual' e OPCIONAL (Fase 1) - registra o que o
    fluxo ATUAL fez de verdade com essa noticia ('publicado' ou
    'descartado'), permitindo comparar depois o sistema novo (sombra)
    com o que realmente aconteceu. Parametro opcional para nao quebrar
    quem chamou log_decision na Fase 0 sem esse argumento."""
    if decisao_sugerida not in DECISOES_VALIDAS:
        print("AVISO (decision_log): decisao_sugerida invalida ('" + str(decisao_sugerida) + "'), registrando como 'discard'.")
        decisao_sugerida = "discard"

    state = _load_decision_log()
    registro = {
        "title": title,
        "source": source,
        "score": score,
        "motivo": motivo,
        "decisao_sugerida": decisao_sugerida,
        "decisao_sistema_atual": decisao_sistema_atual,
        "timestamp": datetime.now(BR_TZ).isoformat(),
    }
    state["decisions"].append(registro)
    state["decisions"] = state["decisions"][-LIMITE_REGISTROS_MANTIDOS:]

    try:
        os.makedirs(os.path.dirname(DECISION_LOG_FILE), exist_ok=True)
        with open(DECISION_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("ERRO (decision_log): falha ao salvar " + DECISION_LOG_FILE + ": " + str(e))
        return False


def get_recent_decisions(limit=100):
    """Le as decisoes mais recentes - usado pra inspecao/debug, nunca
    pelo pipeline de producao."""
    state = _load_decision_log()
    return state["decisions"][-limit:]


# =============================================================================
# 4) SOURCE TIER - mapeamento de prioridade (FEEDS) para tier semantico
#
# Camada de MAPEAMENTO, nao de substituicao. O campo "priority" (2-5)
# que ja existe em FEEDS (main.py) continua sendo a fonte da verdade -
# isto so traduz esse numero para um nome semantico, preparando o
# terreno para a proxima fase sem alterar main.py nem FEEDS agora.
# =============================================================================

MAPA_PRIORIDADE_PARA_TIER = {
    5: "official_critical",
    4: "premium",
    3: "standard",
    2: "low",
}

TIER_PADRAO = "standard"


def get_source_tier(priority_number):
    """Traduz o numero de prioridade (2-5, ja usado em FEEDS) para o
    nome semantico do tier. Numero desconhecido cai em 'standard' -
    nunca lanca excecao por um valor inesperado."""
    return MAPA_PRIORIDADE_PARA_TIER.get(priority_number, TIER_PADRAO)


def get_tier_for_source(feeds_dict, source_name):
    """Atalho que recebe o proprio dict FEEDS (main.py) e o nome da
    fonte, e devolve o tier - sem precisar que quem chama saiba o
    campo interno 'priority'. Se a fonte nao existir no dict, cai no
    tier padrao."""
    info_fonte = feeds_dict.get(source_name)
    if not info_fonte:
        return TIER_PADRAO
    return get_source_tier(info_fonte.get("priority"))


# =============================================================================
# 5) DECISAO SOMBRA E CLUSTERING SIMPLES (Fase 1)
#
# Funcoes PURAS (nao leem nem escrevem arquivo) - fazem so o calculo,
# quem chama decide o que fazer com o resultado. Isso facilita testar
# cada uma isoladamente, sem precisar de arquivo/estado.
# =============================================================================

LIMIAR_BREAKING = 8
LIMIAR_ROUND = 4


def compute_shadow_decision(score):
    """Decide, em modo SOMBRA, o que o sistema novo faria com essa
    noticia - NUNCA usado para bloquear o envio real nesta fase.
    score None (IA nao rodou ou falhou) -> 'discard' (sem informacao
    suficiente pra promover)."""
    if score is None:
        return "discard"
    if score >= LIMIAR_BREAKING:
        return "breaking"
    if score >= LIMIAR_ROUND:
        return "round"
    return "discard"


def derive_cluster_key(text, ticker_list):
    """Identifica a que 'story' essa noticia provavelmente pertence,
    usando a MESMA lista de termos ja usada em compute_news_clusters
    (main.py) - simples de proposito nesta fase (so o primeiro termo
    encontrado no texto), evita reimplementar clustering semantico
    complexo antes de validar se a abordagem simples ja basta.
    Retorna None se nenhum termo bater (a noticia nao vira story
    rastreada, so fica de fora do active_stories)."""
    texto_lower = text.lower()
    for termo in ticker_list:
        if termo in texto_lower:
            return termo
    return None


# =============================================================================
# 6) ESTATISTICAS DIARIAS E RELATORIO DE MODO SOMBRA (Fase 1)
# =============================================================================

SHADOW_STATS_FILE = "docs/shadow_daily_stats.json"
SHADOW_REPORT_FILE = "docs/shadow_mode_report.json"


def _hoje_str():
    return datetime.now(BR_TZ).strftime("%Y-%m-%d")


def _load_shadow_stats():
    if not os.path.exists(SHADOW_STATS_FILE):
        return {"date": _hoje_str(), "total_ingeridas": 0, "aprovadas_atual": 0, "descartadas_atual": 0}
    try:
        with open(SHADOW_STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "date" not in data:
                raise ValueError("formato inesperado")
            return data
    except Exception as e:
        print("AVISO (shadow_stats): falha ao carregar " + SHADOW_STATS_FILE + " (" + str(e) + "). Reiniciando contadores.")
        return {"date": _hoje_str(), "total_ingeridas": 0, "aprovadas_atual": 0, "descartadas_atual": 0}


def _save_shadow_stats(stats):
    try:
        os.makedirs(os.path.dirname(SHADOW_STATS_FILE), exist_ok=True)
        with open(SHADOW_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("ERRO (shadow_stats): falha ao salvar " + SHADOW_STATS_FILE + ": " + str(e))
        return False


def increment_shadow_stat(campo):
    """Incrementa 1 contador diario ('total_ingeridas',
    'aprovadas_atual' ou 'descartadas_atual'). Reinicia os contadores
    sozinho quando o dia muda - nunca precisa de job separado de
    limpeza."""
    stats = _load_shadow_stats()
    if stats.get("date") != _hoje_str():
        stats = {"date": _hoje_str(), "total_ingeridas": 0, "aprovadas_atual": 0, "descartadas_atual": 0}
    stats[campo] = stats.get(campo, 0) + 1
    _save_shadow_stats(stats)


def get_shadow_daily_stats():
    """Leitura pura dos contadores de hoje - se o arquivo for de um
    dia anterior, devolve zerado (sem alterar o arquivo em disco;
    quem realmente reinicia e o increment_shadow_stat, na proxima
    escrita)."""
    stats = _load_shadow_stats()
    if stats.get("date") != _hoje_str():
        return {"date": _hoje_str(), "total_ingeridas": 0, "aprovadas_atual": 0, "descartadas_atual": 0}
    return stats


def generate_shadow_daily_report():
    """Gera o relatorio diario de modo sombra, combinando os
    contadores gerais (shadow_daily_stats) com as decisoes com score
    registradas hoje (decision_log). Sobrescreve o relatorio a cada
    chamada - reflete sempre o acumulado ATE AGORA no dia, fica
    completo por si so ao longo do dia (sem precisar de logica
    separada de 'fim de dia')."""
    hoje = _hoje_str()
    stats = get_shadow_daily_stats()

    todas_decisoes = _load_decision_log().get("decisions", [])
    decisoes_hoje = [d for d in todas_decisoes if d.get("timestamp", "").startswith(hoje)]

    scores_validos = [d["score"] for d in decisoes_hoje if isinstance(d.get("score"), (int, float))]
    score_medio = round(sum(scores_validos) / len(scores_validos), 2) if scores_validos else None

    contagem_por_decisao = {"breaking": 0, "round": 0, "discard": 0}
    divergencias = []
    for d in decisoes_hoje:
        contagem_por_decisao[d["decisao_sugerida"]] = contagem_por_decisao.get(d["decisao_sugerida"], 0) + 1

        sugerida = d.get("decisao_sugerida")
        atual = d.get("decisao_sistema_atual")
        if atual is None:
            continue
        # Divergencia = sistema novo promoveria (breaking/round) algo
        # que o atual descartou, OU sistema novo descartaria algo que
        # o atual publicou.
        novo_promoveria = sugerida in ("breaking", "round")
        atual_publicou = atual == "publicado"
        if novo_promoveria != atual_publicou:
            divergencias.append({
                "title": d.get("title"),
                "source": d.get("source"),
                "score": d.get("score"),
                "decisao_sugerida": sugerida,
                "decisao_sistema_atual": atual,
            })

    relatorio = {
        "date": hoje,
        "total_ingeridas": stats.get("total_ingeridas", 0),
        "aprovadas_pelo_fluxo_atual": stats.get("aprovadas_atual", 0),
        "descartadas_pelos_filtros_atuais": stats.get("descartadas_atual", 0),
        "score_medio_materialidade": score_medio,
        "seriam_breaking": contagem_por_decisao["breaking"],
        "iriam_para_rodada": contagem_por_decisao["round"],
        "seriam_descartadas_pelo_novo_sistema": contagem_por_decisao["discard"],
        "total_divergencias": len(divergencias),
        "divergencias": divergencias[:20],  # amostra - lista completa fica no decision_log
    }

    try:
        os.makedirs(os.path.dirname(SHADOW_REPORT_FILE), exist_ok=True)
        with open(SHADOW_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("ERRO (shadow_report): falha ao salvar " + SHADOW_REPORT_FILE + ": " + str(e))

    return relatorio
