import json

from core.config import DADOS_BRUTOS_DIR


def carregar_qualificacoes() -> dict[str, dict]:
    """Carrega qualificações extraídas dos ToRs, indexadas por torid."""
    qual_path = DADOS_BRUTOS_DIR / "qualificacoes_extraidas.json"
    if not qual_path.exists():
        return {}
    dados = json.loads(qual_path.read_text())
    return {str(q.get("torid", "")): q for q in dados}


def enriquecer_edital(edital: dict, qualificacoes: dict[str, dict]) -> dict:
    """Adiciona dados de qualificação do ToR a um edital classificado."""
    torid = str(edital.get("torid", ""))
    qual = qualificacoes.get(torid, {})

    return {
        **edital,
        "requisitos": {
            "graduacao": qual.get("graduacao", []),
            "pos_graduacao": qual.get("pos_graduacao", []),
            "mestrado": qual.get("mestrado", False),
            "doutorado": qual.get("doutorado", False),
            "anos_experiencia": qual.get("anos_experiencia"),
            "ferramentas": qual.get("ferramentas", []),
            "idiomas": qual.get("idiomas", []),
            "certificacoes": qual.get("certificacoes", []),
            "valor_tor": qual.get("valor"),
            "obrigatorios": qual.get("requisitos_obrigatorios", []),
            "desejaveis": qual.get("requisitos_desejaveis", []),
            "entregaveis": qual.get("entregaveis", []),
        },
    }


def calcular_match_detalhado(edital: dict, perfil: dict) -> dict:
    """Calcula match score e retorna breakdown detalhado por categoria."""
    score = 0.0
    peso_maximo = 0.0
    detalhes = {}

    requisitos = edital.get("requisitos", {})
    areas_edital = edital.get("areas_tematicas", [])
    areas_str = (
        areas_edital if isinstance(areas_edital, str) else ", ".join(areas_edital)
    )

    areas_interesse = set(perfil.get("areas_interesse", []))
    match_areas = [a for a in areas_interesse if a.lower() in areas_str.lower()]
    detalhes["areas"] = {"match": bool(match_areas), "encontradas": match_areas}
    if areas_interesse:
        score += 0.25 * (len(match_areas) / len(areas_interesse))
    peso_maximo += 0.25

    ferramentas_edital = [f.lower() for f in requisitos.get("ferramentas", [])]
    ferramentas_perfil = [f.lower() for f in perfil.get("ferramentas", [])]
    match_ferr = [f for f in ferramentas_perfil if f in ferramentas_edital]
    missing_ferr = [
        f
        for f in ferramentas_perfil
        if f not in ferramentas_edital and ferramentas_edital
    ]
    detalhes["ferramentas"] = {
        "match": match_ferr,
        "faltando": missing_ferr,
        "exigidas": ferramentas_edital,
    }
    if ferramentas_edital and ferramentas_perfil:
        score += 0.25 * (len(match_ferr) / max(len(ferramentas_edital), 1))
    peso_maximo += 0.25

    graduacoes_edital = [g.lower() for g in requisitos.get("graduacao", [])]
    graduacoes_perfil = [g.lower() for g in perfil.get("graduacoes", [])]
    match_grad = [
        g
        for g in graduacoes_perfil
        if any(ge in g or g in ge for ge in graduacoes_edital)
    ]
    detalhes["graduacao"] = {
        "match": match_grad,
        "exigidas": graduacoes_edital,
    }
    if graduacoes_edital and graduacoes_perfil:
        score += 0.25 * (len(match_grad) / max(len(graduacoes_edital), 1))
    peso_maximo += 0.25

    idiomas_edital = [i.lower() for i in requisitos.get("idiomas", [])]
    idiomas_perfil = [i.lower() for i in perfil.get("idiomas", [])]
    match_lang = [i for i in idiomas_edital if i in idiomas_perfil]
    detalhes["idiomas"] = {
        "match": match_lang,
        "exigidos": idiomas_edital,
    }
    if idiomas_edital:
        score += 0.15 * (len(match_lang) / len(idiomas_edital))
    peso_maximo += 0.15

    # Value: penalize if below minimum
    valor_edital = edital.get("valor_estimado_num") or 0
    valor_minimo = perfil.get("valor_minimo", 0)
    detalhes["valor"] = {
        "edital": valor_edital,
        "minimo_perfil": valor_minimo,
        "acima_minimo": valor_edital >= valor_minimo
        if valor_edital and valor_minimo
        else None,
    }
    if valor_edital and valor_minimo:
        score += 0.10 * min(valor_edital / valor_minimo, 1.0)
    peso_maximo += 0.10

    score_final = round(score / peso_maximo if peso_maximo > 0 else 0, 3)
    return {"score": score_final, "detalhes": detalhes}
