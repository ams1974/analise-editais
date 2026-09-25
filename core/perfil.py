import json
import logging

from core.config import PERFIS_DIR

logger = logging.getLogger(__name__)


def carregar_perfis() -> dict[str, dict]:
    perfis = {}
    if PERFIS_DIR.exists():
        for arquivo in PERFIS_DIR.glob("*.json"):
            nome = arquivo.stem
            try:
                perfis[nome] = json.loads(arquivo.read_text())
            except (json.JSONDecodeError, KeyError):
                logger.warning("Perfil inválido ignorado: %s", arquivo.name)
    return perfis


def carregar_perfil(nome: str) -> dict | None:
    arquivo = PERFIS_DIR / f"{nome}.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text())
    return None


def pontuar_edital_para_perfil(edital: dict, perfil: dict) -> float:
    score = 0.0
    peso_maximo = 0.0

    requisitos = edital.get("requisitos", {})

    # =========================================================
    # ÁREAS TEMÁTICAS
    # =========================================================
    areas_edital = edital.get("areas_tematicas", [])
    areas_interesse = set(perfil.get("areas_interesse", []))

    if isinstance(areas_edital, str):
        areas_str = areas_edital
    else:
        areas_str = ", ".join(areas_edital)

    if areas_interesse:
        matches = [
            area for area in areas_interesse if area.lower() in areas_str.lower()
        ]

        if matches:
            score += 0.30 * (len(matches) / len(areas_interesse))

    peso_maximo += 0.30

    # =========================================================
    # FERRAMENTAS
    # =========================================================
    ferramentas_edital = [
        f.lower()
        for f in requisitos.get(
            "ferramentas",
            edital.get("ferramentas", []) or [],
        )
    ]

    ferramentas_perfil = [f.lower() for f in perfil.get("ferramentas", [])]

    if ferramentas_edital and ferramentas_perfil:
        matches = set(ferramentas_edital) & set(ferramentas_perfil)

        if matches:
            score += 0.25 * (len(matches) / len(ferramentas_perfil))

    peso_maximo += 0.25

    # =========================================================
    # GRADUAÇÃO
    # =========================================================
    graduacoes_edital = [
        g.lower()
        for g in requisitos.get(
            "graduacao",
            edital.get("graduacao", []) or [],
        )
    ]

    graduacoes_perfil = [g.lower() for g in perfil.get("graduacoes", [])]

    if graduacoes_edital and graduacoes_perfil:
        matches = set()

        for graduacao_perfil in graduacoes_perfil:
            for graduacao_edital in graduacoes_edital:
                if (
                    graduacao_perfil in graduacao_edital
                    or graduacao_edital in graduacao_perfil
                ):
                    matches.add(graduacao_perfil)
                    break

        if matches:
            score += 0.25 * (len(matches) / len(graduacoes_perfil))

    peso_maximo += 0.25

    # =========================================================
    # IDIOMAS
    # =========================================================
    idiomas_edital = [
        i.lower()
        for i in requisitos.get(
            "idiomas",
            edital.get("idiomas", []) or [],
        )
    ]

    idiomas_perfil = [i.lower() for i in perfil.get("idiomas", [])]

    if idiomas_edital and idiomas_perfil:
        matches = set(idiomas_edital) & set(idiomas_perfil)

        if matches:
            score += 0.10 * (len(matches) / len(idiomas_edital))

    peso_maximo += 0.10

    # =========================================================
    # VALOR
    # =========================================================
    valor_edital = edital.get("valor_estimado_num") or 0
    valor_minimo = perfil.get("valor_minimo", 0)

    # Caso o valor ainda não tenha sido colocado no edital
    # mas esteja disponível no ToR, usar o valor do ToR.
    if not valor_edital:
        valor_tor = requisitos.get("valor_tor")

        if valor_tor:
            try:
                valor_edital = float(str(valor_tor).replace(".", "").replace(",", "."))
            except (ValueError, TypeError):
                valor_edital = 0

    if valor_edital and valor_minimo:
        if valor_edital >= valor_minimo:
            score += 0.10
        else:
            score += 0.05 * (valor_edital / valor_minimo)

    peso_maximo += 0.10

    # =========================================================
    # SCORE FINAL
    # =========================================================
    if peso_maximo > 0:
        score /= peso_maximo

    return round(score, 3)


def classificar_perfil_do_edital(edital: dict) -> str:
    perfis = carregar_perfis()
    if not perfis:
        return "Não classificado"

    melhor_perfil = "Não classificado"
    melhor_pontuacao = 0.0

    for nome, perfil in perfis.items():
        pontuacao = pontuar_edital_para_perfil(edital, perfil)
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_perfil = nome

    if melhor_pontuacao >= 0.15:
        return melhor_perfil
    return "Não classificado"


def filtrar_por_perfil(editais: list, nome_perfil: str) -> list:
    perfil = carregar_perfil(nome_perfil)
    if not perfil:
        return []

    resultado = []
    for edital in editais:
        pontuacao = pontuar_edital_para_perfil(edital, perfil)
        if pontuacao >= 0.15:
            resultado.append({**edital, "score_perfil": pontuacao})
    return sorted(resultado, key=lambda e: e["score_perfil"], reverse=True)
