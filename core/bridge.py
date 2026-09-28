import json
import re

from core.config import DADOS_BRUTOS_DIR

# =========================================================
# UTILITÁRIOS
# =========================================================


def _normalizar(texto: str) -> str:
    """Normaliza texto para comparação."""
    if texto is None:
        return ""

    texto = str(texto).lower()

    # Remove acentos de forma simples e consistente.
    substituicoes = str.maketrans(
        {
            "á": "a",
            "à": "a",
            "ã": "a",
            "â": "a",
            "ä": "a",
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "í": "i",
            "ì": "i",
            "î": "i",
            "ï": "i",
            "ó": "o",
            "ò": "o",
            "õ": "o",
            "ô": "o",
            "ö": "o",
            "ú": "u",
            "ù": "u",
            "û": "u",
            "ü": "u",
            "ç": "c",
        }
    )

    texto = texto.translate(substituicoes)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def _lista(valor) -> list:
    """Garante que um valor seja tratado como lista."""
    if valor is None:
        return []

    if isinstance(valor, list):
        return valor

    if isinstance(valor, tuple):
        return list(valor)

    if isinstance(valor, str):
        return [valor] if valor.strip() else []

    return [valor]


def _normalizar_lista(valor) -> list[str]:
    """Normaliza uma lista de textos."""
    resultado = []

    for item in _lista(valor):
        item = _normalizar(item)

        if item:
            resultado.append(item)

    return resultado


def _texto_edital(edital: dict, requisitos: dict) -> str:
    """
    Constrói o texto usado para encontrar evidências de aderência.

    Inclui título, descrição, órgão, áreas temáticas e requisitos
    textuais extraídos do ToR.
    """
    partes = [
        edital.get("titulo", ""),
        edital.get("descricao", ""),
        edital.get("orgao_parceiro", ""),
        edital.get("area_principal", ""),
    ]

    partes.extend(_lista(edital.get("areas_tematicas", [])))

    partes.extend(_lista(requisitos.get("obrigatorios", [])))
    partes.extend(_lista(requisitos.get("desejaveis", [])))
    partes.extend(_lista(requisitos.get("entregaveis", [])))

    return _normalizar(" ".join(str(p) for p in partes if p))


def _texto_com_espacos(texto: str) -> str:
    """
    Coloca espaços nas extremidades para evitar falsos matches
    por substring.
    """
    return f" {_normalizar(texto)} "


def _termo_encontrado(termo: str, texto: str) -> bool:
    """
    Verifica se um termo aparece no texto.

    Para expressões com várias palavras, utiliza substring.
    Para termos simples, utiliza fronteiras de palavra.
    """
    termo = _normalizar(termo)
    texto = _normalizar(texto)

    if not termo or not texto:
        return False

    if " " in termo or "/" in termo or "-" in termo:
        return termo in texto

    return bool(re.search(rf"\b{re.escape(termo)}\b", texto))


def _match_termos(termos, texto: str) -> list[str]:
    """Retorna os termos encontrados no texto."""
    encontrados = []

    for termo in _normalizar_lista(termos):
        if _termo_encontrado(termo, texto):
            encontrados.append(termo)

    return encontrados


# =========================================================
# SINÔNIMOS / EQUIVALÊNCIAS
# =========================================================


SINONIMOS = {
    "power bi": [
        "power bi",
        "bi",
        "business intelligence",
        "dashboard",
        "dashboards",
    ],
    "excel": [
        "excel",
        "planilha",
        "planilhas",
        "planilha eletronica",
    ],
    "power query": [
        "power query",
        "tratamento de dados",
        "etl",
    ],
    "power automate": [
        "power automate",
        "automacao de processos",
        "automacao",
    ],
    "sql": [
        "sql",
        "banco de dados",
        "base de dados",
        "bases de dados",
    ],
    "python": [
        "python",
        "programacao python",
    ],
    "r": [
        "r",
        "linguagem r",
        "r studio",
        "rstudio",
    ],
    "tableau": [
        "tableau",
    ],
    "looker studio": [
        "looker studio",
        "google data studio",
    ],
    "bpmn": [
        "bpmn",
        "modelagem de processos",
        "modelagem de processo",
    ],
    "gestao de processos": [
        "gestao de processos",
        "gestao de processo",
        "mapeamento de processos",
        "melhoria de processos",
    ],
    "indicadores": [
        "indicadores",
        "indicadores de desempenho",
        "kpi",
        "kpis",
        "metricas",
        "métricas",
    ],
    "analytics": [
        "analytics",
        "analise de dados",
        "analises de dados",
        "data analytics",
        "analitica",
    ],
    "business intelligence": [
        "business intelligence",
        "bi",
        "inteligencia de negocios",
        "inteligencia empresarial",
    ],
    "dashboards": [
        "dashboard",
        "dashboards",
        "painel",
        "paineis",
        "painel de indicadores",
    ],
    "relatorios gerenciais": [
        "relatorio gerencial",
        "relatorios gerenciais",
        "relatorio de gestao",
        "relatorios de gestao",
    ],
    "monitoramento": [
        "monitoramento",
        "acompanhamento",
        "monitoramento e avaliacao",
    ],
    "avaliacao": [
        "avaliacao",
        "avaliação",
        "monitoramento e avaliacao",
    ],
    "diversidade": [
        "diversidade",
        "diversidade e inclusao",
        "diversidade, equidade e inclusao",
        "dei",
        "de&i",
    ],
    "equidade": [
        "equidade",
        "equidade racial",
        "equidade de genero",
    ],
    "inclusao": [
        "inclusao",
        "inclusão",
        "inclusao social",
        "inclusao profissional",
    ],
    "genero": [
        "genero",
        "gênero",
        "mulheres",
        "equidade de genero",
        "equidade de gênero",
    ],
    "raca": [
        "raca",
        "raça",
        "racial",
        "racismo",
        "equidade racial",
        "relacoes raciais",
        "relações raciais",
    ],
    "direitos humanos": [
        "direitos humanos",
        "direitos fundamentais",
        "cidadania",
    ],
    "esg": [
        "esg",
        "asg",
        "responsabilidade social",
        "sustentabilidade",
    ],
    "gestao de pessoas": [
        "gestao de pessoas",
        "recursos humanos",
        "rh",
        "gestao de recursos humanos",
    ],
    "pesquisa": [
        "pesquisa",
        "censo",
        "levantamento",
        "estudo",
        "estudos",
    ],
    "entrevistas qualitativas": [
        "entrevista",
        "entrevistas",
        "entrevista qualitativa",
        "entrevistas qualitativas",
    ],
    "grupos focais": [
        "grupo focal",
        "grupos focais",
        "focus group",
    ],
    "treinamento": [
        "treinamento",
        "capacitação",
        "capacitacao",
        "formacao",
        "formação",
        "curso",
        "oficina",
        "workshop",
    ],
    "comunicacao inclusiva": [
        "comunicacao inclusiva",
        "comunicação inclusiva",
        "linguagem inclusiva",
    ],
    "governanca": [
        "governanca",
        "governança",
        "governança corporativa",
    ],
    "politicas de diversidade": [
        "politica de diversidade",
        "política de diversidade",
        "politicas de diversidade",
        "políticas de diversidade",
    ],
}


def _expandir_termos(termos) -> list[str]:
    """
    Expande os termos do perfil usando o dicionário de equivalências.
    """
    resultado = []

    for termo in _normalizar_lista(termos):
        resultado.append(termo)

        for sinonimo in SINONIMOS.get(termo, []):
            sinonimo_norm = _normalizar(sinonimo)

            if sinonimo_norm and sinonimo_norm not in resultado:
                resultado.append(sinonimo_norm)

    return resultado


def _match_com_sinonimos(termos, texto: str) -> dict:
    """
    Encontra termos do perfil e suas evidências no texto.

    O resultado mantém o termo original do perfil como referência.
    """
    encontrados = []
    evidencias = {}

    for termo_original in _normalizar_lista(termos):
        candidatos = [termo_original]
        candidatos.extend(SINONIMOS.get(termo_original, []))

        encontrados_para_termo = []

        for candidato in candidatos:
            candidato = _normalizar(candidato)

            if candidato and _termo_encontrado(candidato, texto):
                encontrados_para_termo.append(candidato)

        if encontrados_para_termo:
            encontrados.append(termo_original)
            evidencias[termo_original] = sorted(set(encontrados_para_termo))

    return {
        "match": encontrados,
        "evidencias": evidencias,
    }


# =========================================================
# QUALIFICAÇÕES
# =========================================================


def carregar_qualificacoes() -> dict[str, dict]:
    """Carrega qualificações extraídas dos ToRs, indexadas por torid."""
    qual_path = DADOS_BRUTOS_DIR / "qualificacoes_extraidas.json"

    if not qual_path.exists():
        return {}

    dados = json.loads(qual_path.read_text())

    return {str(q.get("torid", "")): q for q in dados}


def enriquecer_edital(
    edital: dict,
    qualificacoes: dict[str, dict],
) -> dict:
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


# =========================================================
# GRADUAÇÃO
# =========================================================


def _graduacao_compativel(
    graduacao_perfil: str,
    graduacao_edital: str,
) -> bool:
    """Verifica compatibilidade básica entre duas formações."""
    perfil = _normalizar(graduacao_perfil)
    edital = _normalizar(graduacao_edital)

    if not perfil or not edital:
        return False

    if perfil == edital:
        return True

    if perfil in edital or edital in perfil:
        return True

    # Casos genéricos.
    if edital == "engenharia" and perfil.startswith("engenharia"):
        return True

    if perfil == "engenharia" and edital.startswith("engenharia"):
        return True

    if "administracao" in perfil and "administracao" in edital:
        return True

    if "computacao" in perfil and "computacao" in edital:
        return True

    return False


def _match_graduacoes(
    graduacoes_perfil,
    graduacoes_edital,
) -> list[str]:
    """Retorna formações do perfil compatíveis com o edital."""
    resultado = []

    for graduacao_perfil in _normalizar_lista(graduacoes_perfil):
        if any(
            _graduacao_compativel(graduacao_perfil, graduacao_edital)
            for graduacao_edital in _normalizar_lista(graduacoes_edital)
        ):
            resultado.append(graduacao_perfil)

    return resultado


def _adicionar_obrigatorio_nao_atendido(
    lista: list[dict],
    criterio: str,
    exigencia,
    motivo: str,
) -> None:
    """Registra uma exigência obrigatória efetivamente não atendida."""
    lista.append(
        {
            "criterio": criterio,
            "exigencia": exigencia,
            "motivo": motivo,
        }
    )


def _tem_informacao(valor) -> bool:
    """
    Indica se um campo possui informação efetivamente utilizável.

    Valores vazios, None e listas vazias são tratados como ausência
    de informação — não como requisito não atendido.
    """
    if valor is None:
        return False

    if isinstance(valor, str):
        return bool(valor.strip())

    if isinstance(valor, (list, tuple, set, dict)):
        return bool(valor)

    return True


# =========================================================
# MATCH PRINCIPAL
# =========================================================


def calcular_match_detalhado(
    edital: dict,
    perfil: dict,
) -> dict:
    """
    Calcula a aderência de um edital a um perfil.

    A lógica prioriza evidências efetivamente presentes no edital,
    evitando penalizar o perfil quando determinado requisito não
    é informado ou não é aplicável.

    O score final varia de 0 a 1.
    """

    requisitos = edital.get("requisitos", {})

    texto = _texto_edital(edital, requisitos)

    # ---------------------------------------------------------
    # PESOS
    # ---------------------------------------------------------
    #
    # Os pesos são aplicados apenas quando existe informação
    # correspondente no edital.
    #
    # Isso evita que:
    #   - edital sem idioma = penalização;
    #   - edital sem ferramenta = penalização;
    #   - edital sem pós = penalização.
    #
    # A aderência temática e profissional recebe maior peso.
    # ---------------------------------------------------------

    PESO_AREAS = 0.25
    PESO_COMPETENCIAS = 0.10
    PESO_FERRAMENTAS = 0.05
    PESO_GRADUACAO = 0.25
    PESO_POS = 0.05
    PESO_MESTRADO = 0.10
    PESO_DOUTORADO = 0.10
    PESO_EXPERIENCIA = 0.05
    PESO_VALOR = 0.05
    PESO_IDIOMAS = 0.0

    score = 0.0
    peso_aplicavel = 0.0

    detalhes = {}
    obrigatorios_nao_atendidos = []

    # =========================================================
    # 1. ÁREAS TEMÁTICAS
    # =========================================================

    areas_edital = _lista(edital.get("areas_tematicas", []))
    areas_texto = " ".join(str(a) for a in areas_edital)

    # A área é comparada também com título, descrição e demais
    # requisitos porque alguns editais possuem classificação
    # temática genérica.
    resultado_areas = _match_com_sinonimos(
        perfil.get("areas_interesse", []),
        f"{areas_texto} {texto}",
    )

    areas_perfil = _normalizar_lista(perfil.get("areas_interesse", []))

    match_areas = resultado_areas["match"]

    detalhes["areas"] = {
        "match": bool(match_areas),
        "encontradas": match_areas,
        "evidencias": resultado_areas["evidencias"],
    }

    if areas_perfil and texto:
        # Pontuação parcial por cobertura das áreas do perfil.
        #
        # Limitamos a contribuição para evitar que um perfil com
        # dezenas de áreas seja beneficiado por coincidências
        # excessivas.
        proporcao = min(
            len(match_areas) / max(len(areas_perfil), 1),
            1.0,
        )

        if match_areas:
            score += PESO_AREAS * max(proporcao, 0.20)

        peso_aplicavel += PESO_AREAS

    # =========================================================
    # 2. COMPETÊNCIAS
    # =========================================================
    #
    # Competências representam aquilo que o profissional precisa
    # saber fazer. São utilizadas diretamente no cálculo do score.
    # =========================================================

    competencias = _lista(perfil.get("competencias", []))

    texto_competencias = " ".join(
        str(p)
        for p in [
            edital.get("titulo", ""),
            edital.get("descricao", ""),
            *(_lista(requisitos.get("obrigatorios", []))),
            *(_lista(requisitos.get("desejaveis", []))),
            *(_lista(requisitos.get("entregaveis", []))),
        ]
        if p
    )

    resultado_competencias = _match_com_sinonimos(
        competencias,
        texto_competencias,
    )

    # Remove duplicidades preservando a ordem.
    match_competencias = list(dict.fromkeys(resultado_competencias["match"]))

    detalhes["competencias"] = {
        "match": match_competencias,
        "evidencias": resultado_competencias["evidencias"],
        "total_perfil": len(_normalizar_lista(competencias)),
    }

    if competencias and texto:
        total_competencias = len(_normalizar_lista(competencias))

        proporcao = min(
            len(match_competencias) / max(total_competencias, 1),
            1.0,
        )

        if match_competencias:
            # Pequena evidência já gera contribuição, mas a pontuação
            # cresce conforme aumenta a quantidade de competências.
            score += PESO_COMPETENCIAS * max(
                proporcao,
                0.20,
            )

        peso_aplicavel += PESO_COMPETENCIAS

    # =========================================================
    # 2.1 TEMAS
    # =========================================================
    #
    # Temas representam o assunto/objeto do trabalho.
    #
    # Nesta primeira alteração controlada, os temas são utilizados
    # somente como evidência complementar e ficam registrados nos
    # detalhes. Eles NÃO recebem peso adicional no score ainda.
    #
    # Isso permite comparar o comportamento antes de decidir se
    # devemos atribuir um peso próprio para aderência temática.
    # =========================================================

    temas = _lista(perfil.get("temas", []))

    resultado_temas = _match_com_sinonimos(
        temas,
        texto,
    )

    match_temas = list(dict.fromkeys(resultado_temas["match"]))

    detalhes["temas"] = {
        "match": match_temas,
        "evidencias": resultado_temas["evidencias"],
        "total_perfil": len(_normalizar_lista(temas)),
    }

    # =========================================================
    # 3. FERRAMENTAS
    # =========================================================

    ferramentas_edital = _normalizar_lista(requisitos.get("ferramentas", []))

    ferramentas_perfil = _normalizar_lista(perfil.get("ferramentas", []))

    match_ferr = []

    for ferramenta_perfil in ferramentas_perfil:
        candidatos = [
            ferramenta_perfil,
            *SINONIMOS.get(ferramenta_perfil, []),
        ]

        if any(
            _termo_encontrado(
                candidato,
                " ".join(ferramentas_edital),
            )
            for candidato in candidatos
        ):
            match_ferr.append(ferramenta_perfil)

    faltando_ferr = []

    if ferramentas_edital and ferramentas_perfil:
        for ferramenta_edital in ferramentas_edital:
            candidatos = [
                ferramenta_edital,
                *SINONIMOS.get(ferramenta_edital, []),
            ]

            if not any(
                _termo_encontrado(
                    candidato,
                    " ".join(ferramentas_perfil),
                )
                for candidato in candidatos
            ):
                faltando_ferr.append(ferramenta_edital)

                _adicionar_obrigatorio_nao_atendido(
                    obrigatorios_nao_atendidos,
                    "ferramenta",
                    ferramenta_edital,
                    (
                        f"A ferramenta '{ferramenta_edital}' "
                        "é exigida e não consta no perfil."
                    ),
                )

    detalhes["ferramentas"] = {
        "match": match_ferr,
        "faltando": faltando_ferr,
        "exigidas": ferramentas_edital,
    }

    # =========================================================
    # 4. GRADUAÇÃO
    # =========================================================

    graduacoes_edital = _normalizar_lista(
        requisitos.get(
            "graduacao",
            edital.get("graduacao", []) or [],
        )
    )

    graduacoes_perfil = _normalizar_lista(perfil.get("graduacoes", []))

    match_grad = _match_graduacoes(
        graduacoes_perfil,
        graduacoes_edital,
    )

    detalhes["graduacao"] = {
        "match": match_grad,
        "exigidas": graduacoes_edital,
    }

    if graduacoes_edital:
        if graduacoes_perfil:
            atendida = bool(match_grad)

            if atendida:
                score += PESO_GRADUACAO
            else:
                _adicionar_obrigatorio_nao_atendido(
                    obrigatorios_nao_atendidos,
                    "graduacao",
                    graduacoes_edital,
                    "Nenhuma formação do perfil é compatível com as formações exigidas.",
                )

        peso_aplicavel += PESO_GRADUACAO

    # =========================================================
    # 5. PÓS-GRADUAÇÃO
    # =========================================================
    #
    # A pós-graduação é tratada apenas como requisito booleano.
    #
    # Não comparamos área, curso ou título da pós-graduação.
    # A verificação da área específica permanece para consulta
    # do usuário no edital.
    #
    # Perfil:
    #   lista com alguma pós-graduação -> True
    #   lista vazia/ausente             -> None
    #
    # Importante:
    # ausência de informação no perfil NÃO significa que o
    # candidato não possui pós-graduação.
    # =========================================================

    pos_edital = requisitos.get("pos_graduacao") is True

    pos_perfil_lista = _normalizar_lista(perfil.get("pos_graduacoes", []))

    pos_perfil = True if pos_perfil_lista else None

    detalhes["pos_graduacao"] = {
        "exigida": pos_edital,
        "perfil": pos_perfil,
        "atendida": (pos_perfil if pos_edital and pos_perfil is not None else None),
    }

    if pos_edital:
        peso_aplicavel += PESO_POS

        if pos_perfil is True:
            score += PESO_POS

        elif pos_perfil is False:
            _adicionar_obrigatorio_nao_atendido(
                obrigatorios_nao_atendidos,
                "pos_graduacao",
                True,
                "O edital exige pós-graduação e o perfil informa que não possui pós-graduação.",
            )

    # =========================================================
    # 6. MESTRADO / DOUTORADO
    # =========================================================

    mestrado_exigido = requisitos.get("mestrado") is True
    doutorado_exigido = requisitos.get("doutorado") is True

    tem_mestrado = perfil.get("tem_mestrado")
    tem_doutorado = perfil.get("tem_doutorado")

    detalhes["pos_academica"] = {
        "mestrado_exigido": mestrado_exigido,
        "mestrado_perfil": tem_mestrado,
        "mestrado_atendido": (
            tem_mestrado if mestrado_exigido and tem_mestrado is not None else None
        ),
        "doutorado_exigido": doutorado_exigido,
        "doutorado_perfil": tem_doutorado,
        "doutorado_atendido": (
            tem_doutorado if doutorado_exigido and tem_doutorado is not None else None
        ),
    }

    if mestrado_exigido:
        peso_aplicavel += PESO_POS / 2

        if tem_mestrado is True:
            score += PESO_POS / 2

        elif tem_mestrado is False:
            _adicionar_obrigatorio_nao_atendido(
                obrigatorios_nao_atendidos,
                "mestrado",
                True,
                "O edital exige mestrado e o perfil informa que não possui mestrado.",
            )

    if doutorado_exigido:
        peso_aplicavel += PESO_POS / 2

        if tem_doutorado is True:
            score += PESO_POS / 2

        elif tem_doutorado is False:
            _adicionar_obrigatorio_nao_atendido(
                obrigatorios_nao_atendidos,
                "doutorado",
                True,
                "O edital exige doutorado e o perfil informa que não possui doutorado.",
            )

    # =========================================================
    # 8. EXPERIÊNCIA
    # =========================================================

    experiencia_edital = requisitos.get("anos_experiencia")
    experiencia_perfil = perfil.get("experiencia_anos")

    experiencia_atendida = None

    if _tem_informacao(experiencia_edital):
        try:
            experiencia_edital = float(experiencia_edital)

            if _tem_informacao(experiencia_perfil):
                experiencia_perfil = float(experiencia_perfil)

                experiencia_atendida = experiencia_perfil >= experiencia_edital

                if experiencia_atendida:
                    score += PESO_EXPERIENCIA
                else:
                    _adicionar_obrigatorio_nao_atendido(
                        obrigatorios_nao_atendidos,
                        "experiencia",
                        experiencia_edital,
                        (
                            f"O edital exige {experiencia_edital:g} anos "
                            f"e o perfil informa {experiencia_perfil:g} anos."
                        ),
                    )

            peso_aplicavel += PESO_EXPERIENCIA

        except (TypeError, ValueError):
            # Exigência inválida/não estruturada:
            # não tratá-la como requisito não atendido.
            experiencia_edital = None

    detalhes["experiencia"] = {
        "exigida": experiencia_edital,
        "perfil": experiencia_perfil,
        "atendida": experiencia_atendida,
    }

    # =========================================================
    # 9. VALOR
    # =========================================================

    valor_edital = edital.get("valor_estimado_num") or 0
    valor_minimo = perfil.get("valor_minimo", 0)

    if not valor_edital:
        valor_tor = requisitos.get("valor_tor")

        if valor_tor:
            try:
                if isinstance(valor_tor, str):
                    valor_normalizado = valor_tor.replace(".", "").replace(",", ".")
                    valor_edital = float(valor_normalizado)
                else:
                    valor_edital = float(valor_tor)

            except (ValueError, TypeError):
                valor_edital = 0

    valor_aplicavel = bool(valor_edital and valor_minimo)

    detalhes["valor"] = {
        "edital": valor_edital,
        "minimo_perfil": valor_minimo,
        "acima_minimo": (valor_edital >= valor_minimo if valor_aplicavel else None),
    }

    if valor_aplicavel:
        peso_aplicavel += PESO_VALOR

        if valor_edital >= valor_minimo:
            score += PESO_VALOR
        else:
            # Valor abaixo do mínimo não zera o match profissional,
            # mas reduz a contribuição deste critério.
            score += PESO_VALOR * min(
                valor_edital / valor_minimo,
                1.0,
            )

    # =========================================================
    # 10. EVIDÊNCIAS TEXTUAIS ADICIONAIS
    # =========================================================
    #
    # Alguns ToRs não estruturam corretamente as competências.
    # Por isso, as palavras-chave de competências e temas são
    # procuradas diretamente no título, descrição, áreas,
    # requisitos obrigatórios/desejáveis e entregáveis.
    #
    # O resultado já está incorporado ao bloco "competencias".
    # =========================================================

    # =========================================================
    # 11. REQUISITOS OBRIGATÓRIOS
    # =========================================================
    #
    # Os requisitos obrigatórios não atendidos são acumulados
    # durante a avaliação de cada critério.
    #
    # False = requisito explicitamente não atendido.
    # None/ausente = informação insuficiente para afirmar
    # que o requisito não é atendido.
    #
    # Esses requisitos são diagnósticos e não alteram o score.
    # =========================================================

    detalhes["obrigatorios"] = {
        "atendidos": not obrigatorios_nao_atendidos,
        "faltantes": obrigatorios_nao_atendidos,
    }

    # =========================================================
    # SCORE FINAL
    # =========================================================

    if peso_aplicavel > 0:
        score_final = score / peso_aplicavel
    else:
        score_final = 0.0

    score_final = max(0.0, min(score_final, 1.0))

    detalhes["metadados"] = {
        "peso_aplicavel": round(peso_aplicavel, 3),
        "score_bruto": round(score, 3),
        "criterios_considerados": round(
            peso_aplicavel / 1.0,
            3,
        ),
    }

    return {
        "score": round(score_final, 3),
        "detalhes": detalhes,
    }
