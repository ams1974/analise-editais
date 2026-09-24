import re
from datetime import date, datetime

from core.config import AREAS_TEMATICAS, CLASSIFICACAO_TIPOS, DOMINIO_ORGAO


def _classificar_tipo(titulo: str, descricao: str = "") -> str:
    texto = f"{titulo} {descricao or ''}".lower()
    for tipo, palavras in CLASSIFICACAO_TIPOS.items():
        for p in palavras:
            if p in texto:
                return tipo
    return "Consultoria (tipo não especificado)"


def _classificar_areas(titulo: str, descricao: str = "") -> list[str]:
    texto = f"{titulo} {descricao or ''}".lower()
    areas = []
    for area, palavras in AREAS_TEMATICAS.items():
        for p in palavras:
            if p in texto:
                areas.append(area)
                break
    return areas if areas else ["Não classificada"]


def _extrair_orgao(email: str = "") -> str:
    if not email:
        return "Não identificado"
    dominio = email.split("@")[-1] if "@" in email else ""
    for dom, orgao in DOMINIO_ORGAO.items():
        if dom in dominio:
            return orgao
    return "Não identificado"


def _extrair_valor(comentario: str = "") -> tuple[str | None, float | None]:
    if not comentario:
        return None, None
    match = re.search(r"R\$\s*([\d.]+,\d{2})", comentario)
    if match:
        texto = match.group(1)
        try:
            numero = float(texto.replace(".", "").replace(",", "."))
            return texto, numero
        except ValueError:
            return texto, None
    return None, None


def classificar_edital(edital: dict) -> dict:
    titulo = edital.get("title", "")
    descricao = edital.get("description", "")
    comentario = edital.get("comments", "")

    valor_texto, valor_num = _extrair_valor(comentario)
    orgao = edital.get("orgao_parceiro") or _extrair_orgao(
        edital.get("receivingEmail", "")
    )

    data_fim = edital.get("endDate", "")[:10] if edital.get("endDate") else ""

    dias_restantes, prazo_classificacao = _calcular_prazo(data_fim)

    return {
        "id": edital["id"],
        "torid": edital.get("torid", ""),
        "fonte": edital.get("fonte", "pnud"),
        "titulo": titulo,
        "descricao": descricao,
        "tipo": _classificar_tipo(titulo, descricao),
        "areas_tematicas": _classificar_areas(titulo, descricao),
        "data_inicio": edital.get("startDate", "")[:10]
        if edital.get("startDate")
        else "",
        "data_fim": edital.get("endDate", "")[:10] if edital.get("endDate") else "",
        "dias_restantes": dias_restantes,
        "prazo_classificacao": prazo_classificacao,
        "local": edital.get("local", ""),
        "orgao_parceiro": orgao,
        "email_submissao": edital.get("receivingEmail", ""),
        "valor_estimado": valor_texto,
        "valor_estimado_num": valor_num,
        "status": edital.get("statusDescription", ""),
        "data_criacao": edital.get("created", "")[:10] if edital.get("created") else "",
        "url_externo": edital.get("url_externo", ""),
    }


def _calcular_prazo(data_fim: str) -> tuple[int | None, str]:
    """Calcula dias restantes e classificação do prazo."""
    if not data_fim:
        return None, "sem prazo"

    try:
        data = datetime.strptime(data_fim[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, "sem prazo"

    hoje = date.today()
    dias = (data - hoje).days

    if dias < 0:
        classificacao = "encerrado"
    elif dias <= 3:
        classificacao = "urgente"
    elif dias <= 7:
        classificacao = "curto"
    elif dias <= 15:
        classificacao = "medio"
    else:
        classificacao = "longo"

    return dias, classificacao
