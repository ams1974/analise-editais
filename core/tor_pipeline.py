"""Baixa e extrai o ToR de editais que ainda não têm qualificação processada.

Fluxo, por edital pendente: localizar a linha na tabela de oportunidades pelo
título, clicar no botão de download (baixa um .zip nomeado "{torid}.zip"),
descompactar, extrair texto do PDF e rodar a extração de qualificações por
regex — tudo no mesmo passo em que o arquivo é baixado.
"""

import asyncio
import json
import logging
import re
import zipfile
from pathlib import Path

from core.config import API_URL, DADOS_BRUTOS_DIR, TORS_DIR
from core.tor_texts import salvar_texto

logger = logging.getLogger(__name__)

QUALIFICACOES_FILE = DADOS_BRUTOS_DIR / "qualificacoes_extraidas.json"

GRAD_PATTERNS = [
    "ciência da computação",
    "engenharia de software",
    "sistemas de informação",
    "tecnologia da informação",
    "análise de sistemas",
    "engenharia da computação",
    "engenharia",
    "economia",
    "administração",
    "estatística",
    "geografia",
    "geologia",
    "biologia",
    "ecologia",
    "engenharia química",
    "engenharia ambiental",
    "direito",
    "ciências sociais",
    "sociologia",
    "antropologia",
    "história",
    "arquitetura",
    "urbanismo",
    "ciência de dados",
    "inteligência artificial",
    "matemática",
    "física",
    "química",
    "ciências contábeis",
    "gestão pública",
    "políticas públicas",
    "saúde pública",
    "medicina",
    "enfermagem",
    "comunicação",
    "biblioteconomia",
    "arquivologia",
    "ciência política",
    "relações internacionais",
]

FERRAMENTAS_LIST = [
    "power bi",
    "power automate",
    "power query",
    "dax",
    "power platform",
    "sharepoint",
    "microsoft 365",
    "outlook",
    "teams",
    "planner",
    "python",
    "r",
    "sql",
    "excel",
    "tableau",
    "qgis",
    "arcgis",
    "powerpoint",
    "word",
    "access",
    "sei",
    "sic",
    "dataverse",
    "google earth engine",
    "stata",
    "spss",
    "sas",
    "matlab",
    "git",
    "docker",
    "azure",
    "aws",
    "google cloud",
    "office 365",
    "project online",
]

CERT_PATTERNS = [
    "pmp",
    "scrum",
    "itil",
    "cobit",
    "cissp",
    "comptia",
    "microsoft certified",
    "aws certified",
    "google certified",
    "bsafe",
    "security clearance",
]


def _extract_pdf_text(pdf_path: Path) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            texts = [t for page in pdf.pages if (t := page.extract_text())]
            return "\n".join(texts)
    except Exception as e:
        logger.warning("Falha ao extrair texto de %s: %s", pdf_path, e)
        return ""


def _extract_entregaveis(text: str) -> list[str]:
    """
    Extrai os produtos/entregáveis previstos no Termo de Referência.

    A função trata principalmente os formatos encontrados nos TORs do PNUD,
    incluindo:

    - "7. Produtos esperados"
    - "5. PRODUTOS"
    - "A consultora produzirá os seguintes produtos:"
    - "PRODUTO 1: ..."
    - "PRODUTO 02 - ..."
    - listas no formato "1. Produto ... 2. Produto ..."
    - tabelas de cronograma contendo "Produto 1", "Produto 2" etc.

    O objetivo é retornar somente os produtos efetivamente contratados,
    evitando capturar:
    - qualificações profissionais;
    - pagamentos;
    - cronogramas como produtos adicionais;
    - disponibilidade;
    - documentos da proposta;
    - outras seções posteriores do TOR.
    """

    if not text:
        return []

    # ------------------------------------------------------------------
    # 1. NORMALIZAÇÃO
    # ------------------------------------------------------------------

    # Mantém quebras de linha, pois elas ajudam a identificar seções,
    # mas elimina espaços/tabs excessivos.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)

    # Evita diferenças causadas por hífens Unicode.
    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2212", "-")

    # ------------------------------------------------------------------
    # 2. LOCALIZAR O INÍCIO DA SEÇÃO DE PRODUTOS
    # ------------------------------------------------------------------

    inicio = None

    padroes_inicio = [
        # "7. Produtos esperados"
        re.compile(
            r"(?im)^\s*\d+(?:\.\d+)*\.?\s+"
            r"produtos?\s+esperados\b"
        ),
        # "6. DESCRIÇÃO DOS PRODUTOS ESPERADOS"
        re.compile(
            r"(?im)^\s*\d+(?:\.\d+)*\.?\s+"
            r"descri[cç][ãa]o\s+dos\s+produtos?\s+esperados\b"
        ),
        # "5. PRODUTOS"
        re.compile(
            r"(?im)^\s*\d+(?:\.\d+)*\.?\s+"
            r"produtos?\s*$"
        ),
        # "4. PRODUTOS:" / "4. Produtos"
        re.compile(
            r"(?im)^\s*\d+(?:\.\d+)*\.?\s+"
            r"produtos?\s*:"
        ),
        # "A consultora produzirá os seguintes produtos:"
        re.compile(
            r"(?i)produzir[aá]?\s+(?:os\s+)?"
            r"seguintes\s+produtos\s*:"
        ),
        # "serão entregues os seguintes produtos"
        re.compile(
            r"(?i)(?:ser[aã]o|ser[aá]o)\s+"
            r"(?:entregues|apresentados)\s+"
            r"(?:os\s+)?seguintes\s+produtos"
        ),
    ]

    candidatos_inicio = []

    for padrao in padroes_inicio:
        for match in padrao.finditer(text):
            candidatos_inicio.append(match)

    if candidatos_inicio:
        # O sumário pode conter o mesmo título da seção antes
        # da seção real. Preferimos o marcador que esteja mais
        # próximo de um "PRODUTO 1".
        candidatos_validos = []

        for match in candidatos_inicio:
            trecho_apos = text[match.end() : match.end() + 50000]

            if re.search(
                r"(?i)\bproduto\s+0*1\s*[:\-–.]?\s+",
                trecho_apos,
            ):
                candidatos_validos.append(match)

        if candidatos_validos:
            # Entre os candidatos que realmente antecedem produtos,
            # usa o último. Isso evita escolher o título do sumário.
            inicio_match = max(
                candidatos_validos,
                key=lambda m: m.start(),
            )
        else:
            # Fallback: mantém o comportamento anterior.
            inicio_match = min(
                candidatos_inicio,
                key=lambda m: m.start(),
            )

        inicio = inicio_match.end()

    # ------------------------------------------------------------------
    # 3. FALLBACK
    # ------------------------------------------------------------------

    # Alguns documentos não possuem um cabeçalho perfeitamente identificável.
    # Nesse caso, procuramos o primeiro "Produto 1".
    if inicio is None:
        fallback = re.search(
            r"(?i)\bproduto\s+0*1\s*[:\-–]?\s+",
            text,
        )

        if fallback:
            inicio = fallback.start()

    if inicio is None:
        return []

    # ------------------------------------------------------------------
    # 4. LOCALIZAR O FIM DA SEÇÃO DE PRODUTOS
    # ------------------------------------------------------------------

    restante = text[inicio:]

    limites = []

    # Seções numeradas posteriores:
    #
    # 8. Qualificações
    # 5.1. Produtos e Cronograma...
    # 6. Modalidade...
    #
    # Não usamos "(?i)" dentro da expressão; isso evita o erro:
    # "global flags not at the start of the expression".
    padrao_secao = re.compile(r"(?im)^\s*\d+(?:\.\d+)+\.?\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]")

    for match in padrao_secao.finditer(restante):
        limites.append(match.start())

    # Seção principal posterior:
    #
    # 8. Qualificações
    # 9. Remuneração
    # 10. ...
    #
    padrao_secao_principal = re.compile(r"(?im)^\s*\d+\.?\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]")

    for match in padrao_secao_principal.finditer(restante):
        limites.append(match.start())

    # Também interrompe diante de cabeçalhos muito comuns que aparecem
    # sem numeração no texto extraído.
    padroes_fim_textual = [
        r"(?im)^\s*qualifica(?:ções|cao|ção)\s+(?:profissionais?|acad[eê]mica)",
        r"(?im)^\s*qualifica(?:ções|cao|ção)\s*$",
        r"(?im)^\s*remunera(?:ção|cao)\b",
        r"(?im)^\s*pagamentos?\b",
        r"(?im)^\s*disponibilidade\b",
        r"(?im)^\s*supervis[aã]o\b",
        r"(?im)^\s*local\s+de\s+trabalho\b",
        r"(?im)^\s*documentos?\s+a\s+serem\s+apresentados\b",
        r"(?im)^\s*crit[eé]rio\s+de\s+avalia(?:ção|cao)\b",
        r"(?im)^\s*classifica(?:ção|cao)\s+das\s+propostas\b",
        r"(?im)^\s*modalidade\s+de\s+contrata(?:ção|cao)\b",
        r"(?im)^\s*considera(?:ções|coes)\s+gerais\b",
        r"(?im)^\s*cronograma\s+de\s+pagamento\b",
    ]

    for padrao in padroes_fim_textual:
        match = re.search(padrao, restante)
        if match:
            limites.append(match.start())

    if limites:
        fim_relativo = min(pos for pos in limites if pos > 0)
        bloco = restante[:fim_relativo]
    else:
        # Limite de segurança para documentos em que não há seção posterior.
        bloco = restante[:30000]

    bloco = bloco.strip()

    if not bloco:
        return []

    # ------------------------------------------------------------------
    # 5. IDENTIFICAR OS MARCADORES DE PRODUTO
    # ------------------------------------------------------------------

    marcadores = []

    # --------------------------------------------------------------
    # Formato:
    #
    # PRODUTO 1:
    # PRODUTO 02 -
    # Produto 3
    #
    # É o marcador mais confiável.
    # --------------------------------------------------------------

    padrao_produto = re.compile(
        r"(?i)\bproduto\s+0*(\d{1,2})\s*"
        r"(?:[:\-]\s*|\.\s*|\s+)"
    )

    for match in padrao_produto.finditer(bloco):
        numero = int(match.group(1))

        # Evita números absurdos decorrentes de texto capturado.
        if 1 <= numero <= 30:
            marcadores.append(
                {
                    "numero": numero,
                    "inicio": match.start(),
                    "conteudo_inicio": match.end(),
                }
            )

    # --------------------------------------------------------------
    # Formato de lista:
    #
    # 1. Referencial...
    # 2. Catálogo...
    # 3. Modelo...
    #
    # Aqui somos deliberadamente conservadores. Não aceitamos:
    #
    # 1) Diagnóstico...
    # 2) Identificação...
    #
    # porque esses números normalmente são subitens internos de um produto.
    # --------------------------------------------------------------

    padrao_lista = re.compile(
        r"(?<![\w)])"
        r"(?<!\d)"
        r"\b([1-9]|1\d|2\d|30)"
        r"\.\s+"
        r"(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])"
    )

    for match in padrao_lista.finditer(bloco):
        numero = int(match.group(1))

        # Verifica o contexto imediatamente anterior.
        contexto = bloco[max(0, match.start() - 80) : match.start()]

        # Não considerar como produto se estiver claramente dentro de:
        # "no mínimo: 1. ..."
        # "Produto 1 ... 2. ..."
        # etc.
        if re.search(
            r"(?i)(?:no\s+m[ií]nimo|mínimo|mínimos|contemplar|incluindo)"
            r"\s*[:\-]?\s*$",
            contexto,
        ):
            continue

        marcadores.append(
            {
                "numero": numero,
                "inicio": match.start(),
                "conteudo_inicio": match.end(),
            }
        )

    # ------------------------------------------------------------------
    # 6. ORDENAR E ELIMINAR MARCADORES DUPLICADOS
    # ------------------------------------------------------------------

    marcadores.sort(key=lambda x: x["inicio"])

    if not marcadores:
        return []

    # Há casos em que o mesmo produto aparece primeiro no texto narrativo
    # e novamente na tabela de cronograma. Mantemos a primeira ocorrência
    # de cada número, desde que ela tenha conteúdo útil.
    marcadores_unicos = []

    numeros_vistos = set()

    for marcador in marcadores:
        numero = marcador["numero"]

        if numero in numeros_vistos:
            continue

        numeros_vistos.add(numero)
        marcadores_unicos.append(marcador)

    marcadores = marcadores_unicos

    # ------------------------------------------------------------------
    # 7. CORRIGIR CASOS EM QUE O PRIMEIRO PRODUTO NÃO TEM "PRODUTO 1"
    # ------------------------------------------------------------------

    # Exemplo:
    #
    # Plano de Trabalho PRODUTO 02 - Relatório ...
    #
    # O texto anterior ao primeiro "PRODUTO 02" é o Produto 1.
    #
    # Só fazemos isso quando:
    # - o primeiro marcador encontrado é > 1;
    # - existe conteúdo significativo antes dele;
    # - esse conteúdo não parece ser apenas cabeçalho.
    #
    primeiro = marcadores[0]

    if primeiro["numero"] > 1:
        prefixo = bloco[: primeiro["inicio"]].strip()

        prefixo = re.sub(
            r"(?im)^\s*(?:produtos?|produtos?\s+esperados?)\s*:?\s*",
            "",
            prefixo,
        ).strip()

        # Remove cabeçalhos soltos.
        prefixo = re.sub(
            r"(?im)^\s*\d+(?:\.\d+)*\.?\s+produtos?\s*(?:esperados?)?\s*:?\s*",
            "",
            prefixo,
        ).strip()

        # Evita criar produto falso a partir de texto muito curto.
        if len(prefixo) >= 30:
            marcadores.insert(
                0,
                {
                    "numero": 1,
                    "inicio": 0,
                    "conteudo_inicio": 0,
                },
            )

    # ------------------------------------------------------------------
    # 8. EXTRAIR O TEXTO DE CADA PRODUTO
    # ------------------------------------------------------------------

    produtos_por_numero = {}

    for i, marcador in enumerate(marcadores):
        numero = marcador["numero"]

        inicio_produto = marcador["conteudo_inicio"]

        # Se for o produto inferido a partir do prefixo.
        if (
            i == 0
            and numero == 1
            and marcador["inicio"] == 0
            and marcador["conteudo_inicio"] == 0
        ):
            inicio_produto = 0

        if i + 1 < len(marcadores):
            fim_produto = marcadores[i + 1]["inicio"]
        else:
            fim_produto = len(bloco)

        conteudo = bloco[inicio_produto:fim_produto]

        # --------------------------------------------------------------
        # Limpeza
        # --------------------------------------------------------------

        conteudo = conteudo.strip(" \n\t:.-")

        # Remove cabeçalhos repetidos que eventualmente ficam no meio.
        conteudo = re.sub(
            r"(?i)\bTERMO\s+DE\s+REFER[EÊ]NCIA\s+N[º°o]?\s*\d+\b",
            " ",
            conteudo,
        )

        conteudo = re.sub(
            r"(?i)\bContrato\s+por\s+Produto\s*-\s*Nacional\b",
            " ",
            conteudo,
        )

        # Remove "Produto X" residual no começo.
        conteudo = re.sub(
            r"(?i)^produto\s+0*\d{1,2}\s*[:\-–.]?\s*",
            "",
            conteudo,
        ).strip()

        # Remove cabeçalho "PRODUTO X" que pode ter sido repetido
        # imediatamente depois de uma quebra de linha.
        conteudo = re.sub(
            r"(?im)^\s*produto\s+0*\d{1,2}\s*[:\-–.]?\s*",
            "",
            conteudo,
        ).strip()

        # Normaliza espaços novamente.
        conteudo = re.sub(r"\s+", " ", conteudo).strip()

        # Remove pontuação isolada no começo.
        conteudo = conteudo.lstrip(" .:-–—")

        if len(conteudo) < 20:
            continue

        # --------------------------------------------------------------
        # 9. FILTROS DE SEGURANÇA
        # --------------------------------------------------------------

        # Se por algum motivo a seção seguinte entrou no produto,
        # corta nesse ponto.
        cortes = []

        for padrao in [
            r"(?i)\bqualifica(?:ções|cao|ção)\s+profissionais?\b",
            r"(?i)\bqualifica(?:ções|cao|ção)\s+acad[eê]mica",
            r"(?i)\bremunera(?:ção|cao)\b",
            r"(?i)\bpagamentos?\b",
            r"(?i)\bdisponibilidade\b",
            r"(?i)\bsupervis[aã]o\b",
            r"(?i)\blocal\s+de\s+trabalho\b",
            r"(?i)\bdocumentos?\s+a\s+serem\s+apresentados\b",
            r"(?i)\bcrit[eé]rio\s+de\s+avalia(?:ção|cao)\b",
            r"(?i)\bclassifica(?:ção|cao)\s+das\s+propostas\b",
            r"(?i)\bmodalidade\s+de\s+contrata(?:ção|cao)\b",
            r"(?i)\bconsidera(?:ções|coes)\s+gerais\b",
        ]:
            match = re.search(padrao, conteudo)
            if match:
                cortes.append(match.start())

        if cortes:
            conteudo = conteudo[: min(cortes)].strip()

        if len(conteudo) < 20:
            continue

        # --------------------------------------------------------------
        # 10. ARMAZENAR
        # --------------------------------------------------------------

        atual = produtos_por_numero.get(numero)

        # Se houver duas ocorrências do mesmo produto, preferimos
        # a descrição mais completa.
        if atual is None or len(conteudo) > len(atual):
            produtos_por_numero[numero] = conteudo

    # ------------------------------------------------------------------
    # 11. RESULTADO FINAL
    # ------------------------------------------------------------------

    if not produtos_por_numero:
        return []

    resultado = []

    for numero in sorted(produtos_por_numero):
        produto = produtos_por_numero[numero]

        # Limpeza final.
        produto = re.sub(r"\s+", " ", produto).strip()
        produto = produto.strip(" .:-–—")

        if len(produto) >= 20:
            resultado.append(produto)

    return resultado


def _find_qualifications(text: str, torid: str) -> dict:
    """Extrai qualificações estruturadas do texto do ToR (regex, sem IA)."""
    result = {
        "torid": torid,
        "graduacao": [],
        "pos_graduacao": [],
        "mestrado": False,
        "doutorado": False,
        "anos_experiencia": None,
        "ferramentas": [],
        "idiomas": [],
        "certificacoes": [],
        "valor": None,
        "area_principal": "",
        "requisitos_obrigatorios": [],
        "requisitos_desejaveis": [],
        "entregaveis": [],
        "competencias": [],
    }

    text_lower = text.lower()

    for p in GRAD_PATTERNS:
        if p in text_lower:
            result["graduacao"].append(p)

    for term in ["pós-graduação", "especialização", "lato sensu", "mba"]:
        if term in text_lower:
            result["pos_graduacao"].append(term)

    if any(t in text_lower for t in ["mestrado", "mestre", "stricto sensu"]):
        result["mestrado"] = True
    if any(t in text_lower for t in ["doutorado", "doutor", "phd"]):
        result["doutorado"] = True

    exp_match = re.search(
        r"(\d+)\s*(?:\(.*?\))?\s*anos?\s*(?:de\s*)?experi[êe]ncia", text_lower
    )
    if exp_match:
        result["anos_experiencia"] = int(exp_match.group(1))

    for f in FERRAMENTAS_LIST:
        if f in text_lower:
            result["ferramentas"].append(f)

    if "inglês" in text_lower or "english" in text_lower:
        result["idiomas"].append("Inglês")
    if "espanhol" in text_lower or "spanish" in text_lower:
        result["idiomas"].append("Espanhol")

    for c in CERT_PATTERNS:
        if c in text_lower:
            result["certificacoes"].append(c)

    valor_match = re.search(r"R\$\s*([\d.]+,\d{2})", text)
    if not valor_match:
        valor_match = re.search(
            r"valor\s*(?:total\s*)?(?:da\s*contratação\s*)?:?\s*R\$\s*([\d.]+,\d{2})",
            text_lower,
        )
    if valor_match:
        result["valor"] = valor_match.group(1)

    req_match = re.search(
        r"(?:requisitos?\s*obrigat[óo]rios?\s*:?|qualifica[cç][ãa]o\s*obrigat[óo]ria)(.*?)"
        r"(?:requisitos?\s*desej[áa]veis|crit[ée]rios\s*de\s*avalia[cç][ãa]o|processo\s*seletivo|"
        r"qualifica[cç][ãa]o\s*desej[áa]vel|\d+\.\s*entrega|\d+\.\s*cronograma)",
        text_lower,
        re.DOTALL,
    )
    if req_match:
        result["requisitos_obrigatorios"] = [
            l.strip()
            for l in req_match.group(1).split("\n")
            if l.strip() and len(l.strip()) > 20
        ][:10]

    req_desej_match = re.search(
        r"(?:requisitos?\s*desej[áa]veis|qualifica[cç][ãa]o\s*desej[áa]vel)(.*?)"
        r"(?:processo\s*seletivo|crit[ée]rios\s*de\s*pontua[cç][ãa]o|entrega\s*dos\s*produtos|"
        r"\d+\.\s*entrega|\d+\.\s*cronograma)",
        text_lower,
        re.DOTALL,
    )
    if req_desej_match:
        result["requisitos_desejaveis"] = [
            l.strip()
            for l in req_desej_match.group(1).split("\n")
            if l.strip() and len(l.strip()) > 20
        ][:10]

    result["entregaveis"] = _extract_entregaveis(text)

    return result


def _carregar_qualificacoes_existentes() -> dict[str, dict]:
    if not QUALIFICACOES_FILE.exists():
        return {}
    dados = json.loads(QUALIFICACOES_FILE.read_text())
    return {str(q.get("torid", "")): q for q in dados}


def _salvar_qualificacoes(qual_por_torid: dict[str, dict]):
    lista = list(qual_por_torid.values())
    QUALIFICACOES_FILE.write_text(json.dumps(lista, indent=2, ensure_ascii=False))


def _processar_zip_baixado(torid: str, zip_path: Path, edital: dict) -> dict | None:
    extract_dir = TORS_DIR / f"{torid}_extracted"
    extract_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    except zipfile.BadZipFile:
        logger.warning("ToR %s: zip inválido", torid)
        return None

    pdfs = list(extract_dir.glob("*.pdf"))
    tor_pdf = next((f for f in pdfs if f.name == "TOR.pdf"), None) or (
        pdfs[0] if pdfs else None
    )
    if not tor_pdf:
        logger.warning("ToR %s: nenhum PDF encontrado no zip", torid)
        return None

    text = _extract_pdf_text(tor_pdf)
    if not text:
        return None

    salvar_texto(torid, text)

    qual = _find_qualifications(text, torid)
    qual["titulo"] = edital.get("title", "")
    qual["descricao"] = edital.get("description", "")
    qual["local"] = edital.get("local", "")
    qual["data_fim"] = (edital.get("endDate", "") or "")[:10]
    return qual


async def _baixar_e_extrair_async(pendentes: list[dict]) -> dict[str, dict]:
    from playwright.async_api import async_playwright

    restantes = {str(e["title"]).strip(): e for e in pendentes if e.get("title")}
    novas_qualificacoes: dict[str, dict] = {}
    if not restantes:
        return novas_qualificacoes

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        try:
            await page.goto(API_URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            logger.warning("Falha ao carregar página de oportunidades: %s", e)
            await browser.close()
            return novas_qualificacoes

        await page.wait_for_timeout(3000)
        rows = await page.query_selector_all("mat-row")

        for row in rows:
            if not restantes:
                break
            try:
                text = (await row.inner_text()).strip()
            except Exception:
                continue

            titulo_match = next((t for t in restantes if t in text), None)
            if not titulo_match:
                continue
            edital = restantes.pop(titulo_match)
            torid = str(edital.get("torid", ""))
            if not torid:
                continue

            try:
                btn = await row.query_selector("mat-cell:last-child button")
                if not btn:
                    logger.info("ToR %s: sem botão de download na linha", torid)
                    continue

                async with page.expect_download(timeout=15000) as dl_info:
                    await btn.click()
                download = await dl_info.value

                zip_path = TORS_DIR / download.suggested_filename
                await download.save_as(str(zip_path))

                qual = _processar_zip_baixado(torid, zip_path, edital)
                if qual:
                    novas_qualificacoes[torid] = qual
                    logger.info("ToR %s extraído com sucesso", torid)
            except Exception as e:
                logger.warning("Falha ao baixar/processar ToR %s: %s", torid, e)

        await browser.close()

    return novas_qualificacoes


def baixar_e_extrair_tors(editais: list[dict]) -> int:
    """Baixa e extrai o ToR de cada edital ainda sem qualificação processada.

    Retorna quantos ToRs foram baixados e extraídos com sucesso nesta chamada.
    """
    TORS_DIR.mkdir(parents=True, exist_ok=True)
    existentes = _carregar_qualificacoes_existentes()

    pendentes = [
        e
        for e in editais
        if str(e.get("torid", "")) and str(e.get("torid", "")) not in existentes
    ]
    if not pendentes:
        return 0

    try:
        novas = asyncio.run(_baixar_e_extrair_async(pendentes))
    except Exception as e:
        logger.warning("Falha geral ao baixar/extrair ToRs: %s", e)
        return 0

    if novas:
        existentes.update(novas)
        _salvar_qualificacoes(existentes)

    return len(novas)
