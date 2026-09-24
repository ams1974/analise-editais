import json
import logging
import os
from collections import Counter
from datetime import date, datetime

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MODEL_RECOMENDACOES = "deepseek-v4-pro"

CLASSIFY_PROMPT = """Classifique cada edital (fontes: PNUD, UNESCO ou OEI Brasil). Retorne APENAS um array JSON com esta estrutura exata:

[{
  "id": 1,
  "tipo": "Consultoria Pessoa Física (PF)",
  "areas_tematicas": ["Saúde"],
  "orgao_parceiro": "TCU",
  "perfil_classificado": "pesquisador_computacao",
  "valor_estimado_num": 50000.0,
  "requisitos": {"graduacao": ["medicina"], "ferramentas": ["r"], "idiomas": ["inglês"], "anos_experiencia": 5, "mestrado": true, "doutorado": false},
  "matches": {
    "engenheiro_dados": {"score": 0.2, "areas": false, "ferramentas_match": [], "ferramentas_faltando": [], "graduacao_match": [], "graduacao_faltando": ["medicina"], "idiomas_match": ["inglês"], "idiomas_faltando": [], "comentario": "Área de saúde, sem afinidade"},
    "economista": {"score": 0.15, ...},
    "pesquisador_computacao": {"score": 0.3, ...}
  }
}]

MATCH — SEJA CONSERVADOR:
- Score 0.0-0.3: pouca compatibilidade
- Score 0.3-0.5: alguma interseção mas gaps significativos
- Score 0.5-0.7: boa compatibilidade — RARO
- Score 0.7-1.0: excepcional — MUITO RARO

PENALIZE:
- Exige mestrado e perfil tem tem_mestrado:false → score máx 0.4
- Exige doutorado e perfil tem tem_doutorado:false → score máx 0.3
- Experiência exigida > experiencia_anos do perfil → reduza
- Graduação exigida não está no perfil → reduza 0.2-0.3
- Áreas temáticas incompatíveis → score máx 0.2

CALCULE matches PARA CADA PERFIL presente no campo "perfis" do JSON de entrada (a lista de perfis pode variar — use exatamente as chaves recebidas, sem omitir nenhuma).

Retorne APENAS o array JSON, sem texto adicional."""


def _build_classify_prompt(editais: list, perfis: dict) -> str:
    import re

    items = []
    for e in editais:
        comments = e.get("comments") or ""
        valor_match = re.search(r"R\$\s*([\d.]+,\d{2})", comments)
        valor_pre = (
            float(valor_match.group(1).replace(".", "").replace(",", "."))
            if valor_match
            else None
        )

        items.append(
            {
                "id": e.get("id"),
                "title": e.get("title", ""),
                "description": (e.get("description") or "")[:250],
                "valor_extraido": valor_pre,
                "local": e.get("local", ""),
                "endDate": (e.get("endDate", "") or "")[:10],
                "receivingEmail": e.get("receivingEmail", ""),
            }
        )

    return json.dumps(
        {
            "perfis": {
                nome: {k: v for k, v in p.items() if k != "nome"}
                for nome, p in perfis.items()
            },
            "editais": items,
        },
        ensure_ascii=False,
        indent=2,
    )


def _extrair_json(texto: str) -> dict | None:
    texto = texto.strip()
    if texto.startswith("```"):
        lines = texto.split("\n")
        texto = "\n".join(lines[1:-1])
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        start = texto.find("{")
        end = texto.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(texto[start:end])
            except json.JSONDecodeError:
                pass
    return None


def _call_deepseek(
    prompt: str, system: str, max_tokens: int = 16384, model: str = DEEPSEEK_MODEL
) -> str | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def analisar_com_ia(editais: list) -> dict | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.info("DEEPSEEK_API_KEY não configurada — usando análise determinística")
        return None

    try:
        from core.perfil import carregar_perfis

        perfis = carregar_perfis()

        prompt = _build_classify_prompt(editais, perfis)
        texto = _call_deepseek(prompt, CLASSIFY_PROMPT, max_tokens=32768)
        if not texto:
            return None

        logger.info("DeepSeek respondeu com %d caracteres", len(texto))
        resultado = _extrair_json(texto)
        if resultado is None:
            logger.warning(
                "DeepSeek não retornou JSON válido. Início: %s", (texto or "")[:200]
            )
            return None
        if isinstance(resultado, list):
            resultado = {"editais": resultado}

        return _processar_resposta(resultado, perfis, editais)

    except Exception as e:
        logger.warning("Erro ao usar DeepSeek: %s — usando análise determinística", e)
        return None


def _processar_resposta(resultado: dict, perfis: dict, raw_editais: list) -> dict:
    editais_data = resultado.get("editais", resultado.get("classificados", []))
    id_to_raw = {e.get("id"): e for e in raw_editais}

    classificados = []
    for ed in editais_data:
        eid = ed.get("id")
        raw = id_to_raw.get(eid, {})
        req = ed.get("requisitos", ed.get("requisitos_inferidos", {}))

        data_fim = (raw.get("endDate", "") or ed.get("endDate", "") or "")[:10]
        dias_restantes, prazo_classificacao = _calcular_prazo(data_fim)

        classificados.append(
            {
                "id": eid,
                "torid": raw.get("torid", ed.get("torid", "")),
                "titulo": raw.get("title", ed.get("title", raw.get("titulo", ""))),
                "descricao": raw.get("description", ed.get("description", "")),
                "tipo": ed.get("tipo", "Consultoria (tipo não especificado)"),
                "areas_tematicas": ed.get("areas_tematicas", []),
                "data_inicio": (raw.get("startDate", "") or "")[:10],
                "data_fim": (raw.get("endDate", "") or ed.get("endDate", "") or "")[
                    :10
                ],
                "dias_restantes": dias_restantes,
                "prazo_classificacao": prazo_classificacao,
                "local": raw.get("local", ed.get("local", "")),
                "orgao_parceiro": ed.get("orgao_parceiro", "Não identificado"),
                "email_submissao": raw.get(
                    "receivingEmail", ed.get("receivingEmail", "")
                ),
                "valor_estimado": _format_valor(ed.get("valor_estimado_num")),
                "valor_estimado_num": ed.get("valor_estimado_num"),
                "status": ed.get("status", raw.get("statusDescription", "Aprovada")),
                "data_criacao": (raw.get("created", "") or "")[:10],
                "perfil_classificado": ed.get(
                    "perfil_classificado", "Não classificado"
                ),
                "requisitos": {
                    "graduacao": req.get("graduacao", []),
                    "ferramentas": req.get("ferramentas", []),
                    "idiomas": req.get("idiomas", []),
                    "anos_experiencia": req.get("anos_experiencia"),
                    "mestrado": req.get("mestrado", False),
                    "doutorado": req.get("doutorado", False),
                    "pos_graduacao": req.get("pos_graduacao", []),
                    "certificacoes": req.get("certificacoes", []),
                    "valor_tor": None,
                    "obrigatorios": req.get("obrigatorios", []),
                    "desejaveis": req.get("desejaveis", []),
                },
            }
        )

    for ec in classificados:
        matches_raw = {}
        for ed in editais_data:
            if ed.get("id") == ec["id"]:
                matches_raw = ed.get("matches", ed.get("match", {}))
                break

        ec["matches"] = {}
        for nome_perfil in perfis:
            m = matches_raw.get(nome_perfil, {})
            ec["matches"][nome_perfil] = {
                "score": m.get("score", 0),
                "detalhes": {
                    "areas": {"match": m.get("areas", False), "encontradas": []},
                    "ferramentas": {
                        "match": m.get("ferramentas_match", []),
                        "faltando": m.get("ferramentas_faltando", []),
                        "exigidas": ec.get("requisitos", {}).get("ferramentas", []),
                    },
                    "graduacao": {
                        "match": m.get("graduacao_match", []),
                        "exigidas": ec.get("requisitos", {}).get("graduacao", []),
                    },
                    "idiomas": {
                        "match": m.get("idiomas_match", []),
                        "exigidos": ec.get("requisitos", {}).get("idiomas", []),
                    },
                    "valor": {
                        "edital": ec.get("valor_estimado_num"),
                        "minimo_perfil": perfis.get(nome_perfil, {}).get(
                            "valor_minimo", 0
                        ),
                        "acima_minimo": (ec.get("valor_estimado_num") or 0)
                        >= perfis.get(nome_perfil, {}).get("valor_minimo", 0),
                    },
                },
            }
        ec["url_externo"] = "https://parceiros.undp.org.br/opportunities"

    recom = {}
    try:
        recom = _gerar_recomendacoes_ia(classificados, perfis)
    except Exception as e:
        logger.warning("Recomendações IA falharam: %s", e)

    perfis_list = []
    for nome, perfil in perfis.items():
        count = sum(
            1
            for e in classificados
            if e["matches"].get(nome, {}).get("score", 0) >= 0.15
        )
        perfis_list.append(
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

    contagem_tipos = Counter(e["tipo"] for e in classificados)
    contagem_orgaos = Counter(e["orgao_parceiro"] for e in classificados)
    areas_flat = []
    for e in classificados:
        a = e.get("areas_tematicas", [])
        areas_flat.extend(a if isinstance(a, list) else [a])
    contagem_areas = Counter(areas_flat)
    valores = [
        e["valor_estimado_num"] for e in classificados if e.get("valor_estimado_num")
    ]

    return {
        "gerado_em": None,
        "resumo": {
            "total_editais": len(classificados),
            "novos_hoje": 0,
            "encerrados_hoje": 0,
            "por_tipo": dict(contagem_tipos.most_common()),
            "por_area": dict(contagem_areas.most_common(10)),
            "por_orgao": dict(contagem_orgaos.most_common()),
            "valores": {
                "minimo": min(valores) if valores else None,
                "maximo": max(valores) if valores else None,
                "medio": sum(valores) / len(valores) if valores else None,
                "mediano": sorted(valores)[len(valores) // 2] if valores else None,
                "quantidade_com_valor": len(valores),
            },
        },
        "perfis": perfis_list,
        "editais": classificados,
        "recomendacoes": recom,
        "modo": "ia",
    }


RECOMMEND_PROMPT = """Você é um orientador de carreira. Com base nos gaps de qualificação abaixo (habilidades e \
graduações mais exigidas nos editais que o perfil ainda não tem), sugira um plano de estudos.

Retorne APENAS JSON com esta estrutura:
{
  "curto_prazo": [{"gap": "...", "curso": "...", "custo": "...", "carga": "...", "nivel": "...", "link": "..."}],
  "medio_prazo": [...],
  "longo_prazo": [...]
}

Curto prazo: 3-6 meses (cursos rápidos, certificações). Médio: 6-18 meses (especializações). Longo: 1-3 anos \
(mestrado/doutorado). No máximo 3 itens por prazo, priorizando os gaps mais exigidos.

Use SOMENTE links reais de provedores conhecidos (Microsoft Learn, Coursera, ENAP, Udemy, UFBA, INPE, ESRI, edX,
gov.br). Se não tiver certeza absoluta da URL exata de um curso específico, use a página inicial ou de busca do
provedor (ex: https://www.coursera.org/, https://www.udemy.com/) em vez de inventar uma URL de curso específica."""


def _sugerir_recomendacoes_ia(
    nome_perfil: str, perfil: dict, rec_base: dict
) -> dict | None:
    prompt = json.dumps(
        {
            "perfil": nome_perfil,
            "descricao": perfil.get("descricao", ""),
            "gaps_curto_prazo": [
                g["nome"] for g in rec_base.get("curto_prazo", {}).get("gaps", [])
            ][:8],
            "gaps_medio_prazo": [
                g["nome"] for g in rec_base.get("medio_prazo", {}).get("gaps", [])
            ][:8],
            "gaps_longo_prazo": [
                g["nome"] for g in rec_base.get("longo_prazo", {}).get("gaps", [])
            ][:8],
        },
        ensure_ascii=False,
        indent=2,
    )

    # deepseek-v4-pro gasta uma parte relevante do orçamento de tokens "pensando"
    # (reasoning_content) antes de escrever a resposta — precisa de bem mais
    # espaço que um modelo não-reasoning para não cortar o JSON pela metade.
    texto = _call_deepseek(
        prompt, RECOMMEND_PROMPT, max_tokens=20000, model=DEEPSEEK_MODEL_RECOMENDACOES
    )
    return _extrair_json(texto) if texto else None


def _link_valido(url: str, timeout: float = 4.0) -> bool:
    if not url or not url.startswith("http"):
        return False
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; analise-editais-bot/1.0)"}
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
        if r.status_code >= 400:
            r = requests.get(
                url, timeout=timeout, allow_redirects=True, headers=headers, stream=True
            )
        return r.status_code < 400
    except Exception:
        return False


def _validar_plano_ia(plano_ia: list, plano_fallback: list) -> list:
    """Confirma cada link sugerido pela IA batendo nele de verdade; troca pelo
    equivalente do catálogo curado (mesmo gap) se estiver quebrado."""
    fallback_por_gap = {(c.get("gap") or "").lower(): c for c in plano_fallback}
    resultado = []
    for item in (plano_ia or [])[:4]:
        link = item.get("link", "")
        if _link_valido(link):
            resultado.append(item)
            continue
        substituto = fallback_por_gap.get((item.get("gap") or "").lower())
        if substituto:
            resultado.append(substituto)
        logger.info(
            "Link descartado por não responder: %s (gap=%s)", link, item.get("gap")
        )
    return resultado or plano_fallback[:3]


def _gerar_recomendacoes_ia(classificados: list, perfis: dict) -> dict:
    from core.recommender import gerar_recomendacoes_todos_perfis

    base = gerar_recomendacoes_todos_perfis(classificados)

    for nome_perfil, perfil in perfis.items():
        rec = base.get(nome_perfil)
        if not rec or not rec.get("total_editais_compativeis"):
            continue

        sugestao = _sugerir_recomendacoes_ia(nome_perfil, perfil, rec)
        if not sugestao:
            continue

        for prazo_key in ("curto_prazo", "medio_prazo", "longo_prazo"):
            plano_ia = sugestao.get(prazo_key)
            if not plano_ia:
                continue
            plano_fallback = rec.get(prazo_key, {}).get("plano", [])
            rec.setdefault(prazo_key, {"gaps": [], "plano": []})["plano"] = (
                _validar_plano_ia(plano_ia, plano_fallback)
            )

        rec["periodo_analise"] = "Últimos 12 meses (DeepSeek v4 Pro)"

    return base


def _format_valor(v):
    if v is None:
        return None
    return f"R$ {v:,.2f}".replace(".", ",")


def _calcular_prazo(data_fim: str) -> tuple[int | None, str]:
    if not data_fim:
        return None, "sem prazo"

    try:
        data = datetime.strptime(data_fim[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, "sem prazo"

    dias = (data - date.today()).days

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
