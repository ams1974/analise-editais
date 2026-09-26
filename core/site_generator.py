import json
import logging
from datetime import datetime
from pathlib import Path

from core.bridge import (
    calcular_match_detalhado,
    carregar_qualificacoes,
    enriquecer_edital,
)
from core.classifier import classificar_edital
from core.config import API_URL, HISTORICO_MESES, ROOT
from core.perfil import carregar_perfis
from core.persistence import carregar_ultimo_snapshot
from core.recommender import gerar_recomendacoes_todos_perfis

logger = logging.getLogger(__name__)

SITE_DATA_DIR = ROOT / "docs" / "data"
SITE_ANALISE_FILE = SITE_DATA_DIR / "analise.json"
SITE_PERFIS_FILE = SITE_DATA_DIR / "perfis.json"


def gerar_dados_site(analise: dict, novidades: dict | None = None) -> tuple[Path, Path]:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    qualificacoes = carregar_qualificacoes()
    perfis = carregar_perfis()
    historicos = _carregar_historicos_enriquecidos(qualificacoes, perfis)

    site_data = _tentar_ia(analise) or _analise_deterministica(
        analise, qualificacoes, perfis, historicos
    )

    if site_data:
        site_data["historico_meses"] = HISTORICO_MESES
        _mesclar_valores_tors(site_data["editais"])
        _recalcular_valores(site_data)
        site_data["gerado_em"] = datetime.now().isoformat()
        site_data["resumo"]["novos_hoje"] = novidades["novos_count"] if novidades else 0
        site_data["resumo"]["encerrados_hoje"] = (
            novidades["encerrados_count"] if novidades else 0
        )
        site_data["resumo_ia"] = _gerar_resumo(site_data)
        editais_consulta_atual = carregar_ultimo_snapshot()
        site_data["historico"] = _montar_historico(historicos, editais_consulta_atual)
        _mesclar_valores_tors(site_data["historico"])

        # Contadores padronizados para o frontend.
        editais = site_data["editais"]
        historico = site_data["historico"]

        site_data["resumo"].update(
            {
                "editais_ativos": sum(
                    e.get("status_sistema") == "ativo" for e in editais
                ),
                "editais_encerrados": sum(
                    e.get("status_sistema") == "encerrado" for e in editais
                ),
                "historico_total": len(historico),
                "historico_ativos": sum(
                    e.get("status_sistema") == "ativo" for e in historico
                ),
                "historico_encerrados": sum(
                    e.get("status_sistema") == "encerrado" for e in historico
                ),
                "historico_inativos": sum(
                    e.get("status_sistema") == "inativo" for e in historico
                ),
            }
        )

    SITE_ANALISE_FILE.write_text(json.dumps(site_data, indent=2, ensure_ascii=False))

    perfis = carregar_perfis()
    SITE_PERFIS_FILE.write_text(
        json.dumps({"perfis": list(perfis.values())}, indent=2, ensure_ascii=False)
    )

    return SITE_ANALISE_FILE, SITE_PERFIS_FILE


def _tentar_ia(analise: dict) -> dict | None:
    from core.llm import analisar_com_ia
    from core.persistence import carregar_editais_historico

    ids_ativos = {e.get("id") for e in analise.get("editais", [])}
    if not ids_ativos:
        return None

    raw = [
        e
        for e in carregar_editais_historico(meses=HISTORICO_MESES)
        if e.get("id") in ids_ativos
    ]
    if not raw:
        return None

    logger.info("Tentando análise via DeepSeek...")
    resultado = analisar_com_ia(raw)
    if resultado:
        logger.info("Análise IA concluída com sucesso")
        return resultado
    return None


def _determinar_status_sistema(edital: dict, *, disponivel: bool = True) -> str:
    """Determina o status padronizado usado pelo sistema.

    Status possíveis:
    - ativo: edital disponível e com prazo vigente;
    - encerrado: edital disponível, mas com prazo vencido;
    - inativo: edital não está mais disponível na consulta atual.
    """
    if not disponivel:
        return "inativo"

    dias_restantes = edital.get("dias_restantes")

    if dias_restantes is None or dias_restantes >= 0:
        return "ativo"

    return "encerrado"


def _analise_deterministica(
    analise: dict, qualificacoes: dict, perfis: dict, historicos: list
) -> dict:
    editais_enriquecidos = []

    for edital in analise["editais"]:
        e = enriquecer_edital(edital, qualificacoes)

        matches = {}
        for nome_perfil, perfil in perfis.items():
            matches[nome_perfil] = calcular_match_detalhado(e, perfil)

        e["matches"] = matches

        # Editais que vieram da consulta atual:
        # - sem data_fim: ativo
        # - prazo vigente: ativo
        # - prazo vencido: encerrado
        e["status_sistema"] = _determinar_status_sistema(e)

        if not e.get("url_externo"):
            e["url_externo"] = API_URL

        editais_enriquecidos.append(e)

    perfil_list = []
    for nome, perfil in perfis.items():
        count = sum(
            1
            for e in editais_enriquecidos
            if e["matches"].get(nome, {}).get("score", 0) >= 0.15
        )

        perfil_list.append(
            {
                "nome": nome,
                "descricao": perfil.get("descricao", ""),
                "graduacoes": perfil.get("graduacoes", []),
                "ferramentas": perfil.get("ferramentas", []),
                "areas_interesse": perfil.get("areas_interesse", []),
                "idiomas": perfil.get("idiomas", []),
                "match_count": count,
            }
        )

    return {
        "gerado_em": None,
        "resumo": {
            "total_editais": analise["total_editais"],
            "novos_hoje": 0,
            "encerrados_hoje": 0,
            "por_tipo": analise.get("contagem_tipos", {}),
            "por_area": analise.get("contagem_areas", {}),
            "por_orgao": analise.get("contagem_orgaos", {}),
            "valores": analise.get("valores", {}),
        },
        "perfis": perfil_list,
        "editais": editais_enriquecidos,
        "recomendacoes": gerar_recomendacoes_todos_perfis(historicos),
        "modo": "deterministico",
    }


def _carregar_historicos_enriquecidos(qualificacoes: dict, perfis: dict) -> list:
    from core.persistence import carregar_editais_historico

    raw = carregar_editais_historico(meses=HISTORICO_MESES)
    if not raw:
        return []

    classificados = [classificar_edital(e) for e in raw]
    enriquecidos = []
    for edital in classificados:
        e = enriquecer_edital(edital, qualificacoes)
        matches = {}
        for nome_perfil, perfil in perfis.items():
            matches[nome_perfil] = calcular_match_detalhado(e, perfil)
        e["matches"] = matches
        enriquecidos.append(e)

    return enriquecidos


def _montar_historico(historicos: list, editais_ativos: list) -> list:
    """Lista editais históricos com o status atual."""
    ids_atuais = {e.get("id") for e in editais_ativos}

    historico = []

    for e in historicos:
        item = {**e}

        # O edital ainda aparece na consulta atual.
        item["status_sistema"] = _determinar_status_sistema(
            item,
            disponivel=e.get("id") in ids_atuais,
        )

        matches = item.get("matches", {})
        melhor_nome, melhor = max(
            matches.items(),
            key=lambda kv: kv[1].get("score", 0),
            default=(None, {"score": 0}),
        )

        item["perfil_classificado"] = (
            melhor_nome if melhor.get("score", 0) >= 0.15 else "Não classificado"
        )

        if not item.get("url_externo"):
            item["url_externo"] = API_URL

        historico.append(item)

    historico.sort(
        key=lambda e: e.get("data_inicio", ""),
        reverse=True,
    )

    return historico


def _recalcular_valores(site_data: dict):
    from statistics import median

    valores = [
        e["valor_estimado_num"]
        for e in site_data["editais"]
        if e.get("valor_estimado_num")
    ]
    if valores:
        site_data["resumo"]["valores"] = {
            "minimo": min(valores),
            "maximo": max(valores),
            "medio": round(sum(valores) / len(valores), 2),
            "mediano": round(median(valores), 2),
            "quantidade_com_valor": len(valores),
        }


def _mesclar_valores_tors(editais: list):
    from core.bridge import carregar_qualificacoes
    from core.tor_values import extrair_valores_tors

    qual = carregar_qualificacoes()
    valores_tor = extrair_valores_tors(qual)

    for e in editais:
        torid = str(e.get("torid", ""))
        if torid in valores_tor:
            v = valores_tor[torid]
            if not e.get("valor_estimado_num") or v > e["valor_estimado_num"]:
                e["valor_estimado_num"] = v
                e["valor_estimado"] = (
                    f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            e.setdefault("requisitos", {})["valor_tor"] = v


def _gerar_resumo(site_data: dict) -> str | None:
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None

    try:
        from openai import OpenAI

        stats = json.dumps(
            {
                "total": site_data["resumo"]["total_editais"],
                "por_tipo": site_data["resumo"].get("por_tipo", {}),
                "por_orgao": site_data["resumo"].get("por_orgao", {}),
                "por_area": dict(
                    list(site_data["resumo"].get("por_area", {}).items())[:5]
                ),
                "perfis": [
                    {"nome": p["nome"], "match": p["match_count"]}
                    for p in site_data.get("perfis", [])
                ],
            },
            ensure_ascii=False,
        )

        client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um analista. Escreva um resumo de 3-4 frases em português sobre os editais do PNUD, UNESCO e OEI no Brasil. Destaque: total, áreas mais quentes, órgãos principais, e perfis mais demandados. Seja direto e informativo.",
                },
                {"role": "user", "content": f"Resuma estes dados:\n{stats}"},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Falha ao gerar resumo IA: %s", e)
        return None
