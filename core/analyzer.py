from collections import Counter
from datetime import datetime, timedelta

from core.bridge import (
    calcular_match_detalhado,
    carregar_qualificacoes,
    enriquecer_edital,
)
from core.classifier import classificar_edital
from core.perfil import (
    carregar_perfis,
    filtrar_por_perfil,
)


def analisar_editais(
    editais: list,
    periodo_meses: int | None = 3,
    perfil_nome: str | None = None,
    todos: bool = False,
    fonte_nome: str | None = None,
) -> dict:
    """Analisa editais com opções de período, perfil e fonte.

    Args:
        editais: Lista de editais brutos (do scraping)
        periodo_meses: Filtrar pelos últimos N meses (None = sem filtro)
        perfil_nome: Filtrar por perfil específico
        todos: Ignorar filtro de período (analisar todos)
        fonte_nome: Filtrar por fonte específica (pnud, unesco, oei)

    Returns:
        Dicionário com análises e metadados
    """
    classificados = [classificar_edital(e) for e in editais]

    if fonte_nome:
        classificados = [e for e in classificados if e.get("fonte") == fonte_nome]

    if periodo_meses and not todos:
        corte = datetime.now() - timedelta(days=periodo_meses * 30)
        classificados = [
            e
            for e in classificados
            if e.get("data_inicio") and e["data_inicio"] >= corte.strftime("%Y-%m-%d")
        ]

    perfis_disponiveis = carregar_perfis()
    qualificacoes = carregar_qualificacoes()

    for i, edital in enumerate(classificados):
        enriquecido = enriquecer_edital(edital, qualificacoes)

        melhor_perfil = None
        melhor_score = 0.0

        for nome, perfil in perfis_disponiveis.items():
            match = calcular_match_detalhado(enriquecido, perfil)
            score = match["score"]

            if score > melhor_score:
                melhor_score = score
                melhor_perfil = nome

        enriquecido["perfil_classificado"] = (
            melhor_perfil if melhor_score >= 0.15 else "Não classificado"
        )
        enriquecido["score_perfil"] = melhor_score

        classificados[i] = enriquecido

    if perfil_nome:
        perfil = perfis_disponiveis.get(perfil_nome)

        if not perfil:
            classificados = []
        else:
            classificados = [
                e
                for e in classificados
                if calcular_match_detalhado(e, perfil)["score"] >= 0.15
            ]
    return _gerar_estatisticas(
        classificados, perfis_disponiveis, periodo_meses, perfil_nome, todos, fonte_nome
    )


def _gerar_estatisticas(
    classificados: list,
    perfis_disponiveis: dict,
    periodo_meses: int | None,
    perfil_nome: str | None,
    todos: bool,
    fonte_nome: str | None = None,
) -> dict:
    total = len(classificados)

    contagem_tipos = Counter(e["tipo"] for e in classificados)
    contagem_fontes = Counter(e.get("fonte", "pnud") for e in classificados)

    areas_flat = []
    for e in classificados:
        areas = e.get("areas_tematicas", [])
        if isinstance(areas, list):
            areas_flat.extend(areas)
        elif isinstance(areas, str):
            areas_flat.extend(areas.split(", "))
    contagem_areas = Counter(areas_flat)

    contagem_orgaos = Counter(e["orgao_parceiro"] for e in classificados)

    contagem_perfis = Counter(e.get("perfil_classificado", "") for e in classificados)

    valores = []
    for e in classificados:
        v = e.get("valor_estimado_num")
        if v and v > 0:
            valores.append(v)

    # Distribuição por perfil
    por_perfil = {}
    for nome_perfil in perfis_disponiveis:
        matched = filtrar_por_perfil(classificados, nome_perfil)
        if matched:
            por_perfil[nome_perfil] = {
                "quantidade": len(matched),
                "descricao": perfis_disponiveis[nome_perfil].get("descricao", ""),
                "editais": [
                    {
                        "id": e["id"],
                        "titulo": e["titulo"],
                        "score": e.get("score_perfil", 0),
                    }
                    for e in matched[:5]
                ],
            }

    return {
        "total_editais": total,
        "filtro_aplicado": {
            "periodo_meses": periodo_meses if not todos else None,
            "perfil": perfil_nome,
            "todos": todos,
            "fonte": fonte_nome,
        },
        "contagem_tipos": dict(contagem_tipos.most_common()),
        "contagem_fontes": dict(contagem_fontes.most_common()),
        "contagem_areas": dict(contagem_areas.most_common(10)),
        "contagem_orgaos": dict(contagem_orgaos.most_common()),
        "contagem_perfis": dict(contagem_perfis.most_common()),
        "valores": {
            "minimo": min(valores) if valores else None,
            "maximo": max(valores) if valores else None,
            "medio": sum(valores) / len(valores) if valores else None,
            "mediano": sorted(valores)[len(valores) // 2] if valores else None,
            "quantidade_com_valor": len(valores),
        },
        "por_perfil": por_perfil,
        "editais": classificados,
        "data_analise": datetime.now().isoformat(),
    }
