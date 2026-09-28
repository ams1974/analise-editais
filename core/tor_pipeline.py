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
    # Computação / TI
    "ciência da computação",
    "engenharia da computação",
    "sistemas de informação",
    "análise e desenvolvimento de sistemas",
    "tecnologia da informação",
    "engenharia de software",
    "engenharia de sistemas",
    "informática",
    # Dados / Matemática / Estatística
    "estatística",
    "matemática",
    "matemática aplicada",
    "ciência de dados",
    # Engenharias
    "engenharia",
    "engenharia de produção",
    "engenharia cartográfica",
    "engenharia cartográfica e de agrimensura",
    # Geografia / território
    "geografia",
    "geoprocessamento",
    "cartografia",
    "sensoriamento remoto",
    "meteorologia",
    # Ciências sociais / humanas
    "ciências sociais",
    "sociologia",
    "antropologia",
    "ciência política",
    "políticas públicas",
    "administração pública",
    "gestão pública",
    "administração",
    "economia",
    "ciências econômicas",
    "direito",
    # Meio ambiente
    "ciências ambientais",
    "gestão ambiental",
    "engenharia ambiental",
    "engenharia florestal",
    # Comunicação / documentação
    "comunicação social",
    "jornalismo",
    "biblioteconomia",
    "arquivologia",
]

FERRAMENTAS_LIST = [
    # BI / Microsoft
    "power bi",
    "power automate",
    "power query",
    "power platform",
    "dax",
    "sharepoint",
    "microsoft 365",
    "office 365",
    "outlook",
    "teams",
    "planner",
    "project online",
    "dataverse",
    # Dados / programação
    "python",
    "r",
    "sql",
    "sas",
    "spss",
    "stata",
    "matlab",
    # Planilhas / produtividade
    "excel",
    "access",
    "powerpoint",
    "word",
    # BI / visualização
    "tableau",
    # GIS / geoprocessamento
    "gis",
    "qgis",
    "arcgis",
    "fme",
    "geopandas",
    "google earth engine",
    # Desenvolvimento / infraestrutura
    "git",
    "docker",
    # Cloud
    "azure",
    "aws",
    "google cloud",
    # Sistemas governamentais
    "sei",
    "sic",
]

CERT_PATTERNS = [
    # Gestão de projetos
    "pmp",
    "project management professional",
    "prince2",
    # Métodos ágeis
    "scrum",
    "scrum master",
    "product owner",
    "safe",
    # IT Service Management
    "itil",
    # Governança / segurança
    "cobit",
    "cissp",
    "comptia",
    # Cloud
    "aws certified",
    "microsoft certified",
    "azure certification",
    "google certified",
    # Dados / BI
    "microsoft power bi data analyst",
    "power bi data analyst",
    # Outras
    "security clearance",
    "bsafe",
]


def _extract_pdf_text(pdf_path: Path) -> str:
    """
    Extrai texto de um PDF.

    Estratégia:
    1. Tenta extração textual direta com pdfplumber.
    2. Se o texto extraído for insuficiente, tenta OCR.
    3. O OCR renderiza as páginas com pdftoppm e utiliza Tesseract
       com o idioma português.

    PDFs que já possuem texto utilizável não passam pelo OCR.
    PDFs essencialmente compostos por imagens são processados via OCR.
    """

    import shutil
    import subprocess
    import tempfile

    import pdfplumber

    # ---------------------------------------------------------
    # 1. EXTRAÇÃO TEXTUAL NORMAL
    # ---------------------------------------------------------

    texto = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            textos = []

            for page in pdf.pages:
                try:
                    page_text = page.extract_text()

                    if page_text:
                        textos.append(page_text)
                except Exception as e:
                    logger.warning(
                        "Falha ao extrair uma página de %s: %s",
                        pdf_path,
                        e,
                    )

            texto = "\n".join(textos).strip()

    except Exception as e:
        logger.warning(
            "Falha ao extrair texto de %s: %s",
            pdf_path,
            e,
        )

    # ---------------------------------------------------------
    # 2. VERIFICAR SE A EXTRAÇÃO É SUFICIENTE
    # ---------------------------------------------------------

    # PDFs escaneados/impressos como imagem podem retornar apenas
    # alguns caracteres, mesmo contendo várias páginas.
    #
    # Um limite baixo evita OCR desnecessário em PDFs textuais
    # normais.
    if len(texto) >= 500:
        return texto

    logger.info(
        "Texto insuficiente em %s (%d caracteres); tentando OCR.",
        pdf_path,
        len(texto),
    )

    # ---------------------------------------------------------
    # 3. VERIFICAR DEPENDÊNCIAS DO OCR
    # ---------------------------------------------------------

    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")

    if not pdftoppm:
        logger.warning(
            "pdftoppm não encontrado; não foi possível executar OCR em %s.",
            pdf_path,
        )
        return texto

    if not tesseract:
        logger.warning(
            "tesseract não encontrado; não foi possível executar OCR em %s.",
            pdf_path,
        )
        return texto

    # ---------------------------------------------------------
    # 4. OCR
    # ---------------------------------------------------------

    try:
        with tempfile.TemporaryDirectory(prefix="analise_editais_ocr_") as tmp:
            tmp_dir = Path(tmp)

            prefixo = tmp_dir / "pagina"

            # Renderiza todas as páginas em PNG.
            #
            # 250 DPI foi escolhido como compromisso entre:
            # - qualidade suficiente para OCR;
            # - tempo de processamento;
            # - consumo de memória/disco.
            resultado = subprocess.run(
                [
                    pdftoppm,
                    "-r",
                    "250",
                    "-png",
                    str(pdf_path),
                    str(prefixo),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if resultado.returncode != 0:
                logger.warning(
                    "Falha ao renderizar PDF para OCR: %s: %s",
                    pdf_path,
                    resultado.stderr.strip(),
                )
                return texto

            imagens = sorted(tmp_dir.glob("pagina-*.png"))

            if not imagens:
                logger.warning(
                    "Nenhuma página foi renderizada para OCR: %s",
                    pdf_path,
                )
                return texto

            textos_ocr = []

            for imagem in imagens:
                arquivo_saida = tmp_dir / imagem.stem

                resultado = subprocess.run(
                    [
                        tesseract,
                        str(imagem),
                        str(arquivo_saida),
                        "-l",
                        "por",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if resultado.returncode != 0:
                    logger.warning(
                        "Falha no OCR da página %s de %s: %s",
                        imagem.name,
                        pdf_path,
                        resultado.stderr.strip(),
                    )
                    continue

                arquivo_txt = arquivo_saida.with_suffix(".txt")

                if not arquivo_txt.exists():
                    continue

                try:
                    texto_pagina = arquivo_txt.read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).strip()
                except Exception as e:
                    logger.warning(
                        "Falha ao ler resultado OCR %s: %s",
                        arquivo_txt,
                        e,
                    )
                    continue

                if texto_pagina:
                    textos_ocr.append(texto_pagina)

            texto_ocr = "\n\n".join(textos_ocr).strip()

            if texto_ocr:
                logger.info(
                    "OCR concluído para %s: %d caracteres em %d páginas.",
                    pdf_path,
                    len(texto_ocr),
                    len(imagens),
                )

                return texto_ocr

    except Exception as e:
        logger.warning(
            "Falha ao executar OCR em %s: %s",
            pdf_path,
            e,
        )

    # ---------------------------------------------------------
    # 5. ÚLTIMO RECURSO
    # ---------------------------------------------------------

    # Se havia algum texto parcial obtido pelo pdfplumber,
    # preservamos esse resultado.
    return texto


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


def _extrair_secoes_requisitos(text: str) -> tuple[str, str]:
    """
    Extrai requisitos obrigatórios e desejáveis de um Termo de Referência.

    Trata principalmente:

    1. Seções separadas:
        REQUISITOS OBRIGATÓRIOS
        ...
        REQUISITOS DESEJÁVEIS
        ...

    2. Seção de qualificações:
        QUALIFICAÇÕES PROFISSIONAIS
        Qualificações obrigatórias - ...
        Qualificações desejáveis e pontuáveis - ...

    3. Formato:
        QUALIFICAÇÕES OBRIGATÓRIAS:
        ...
        QUALIFICAÇÕES DESEJÁVEIS E PONTUÁVEIS:
        ...

    4. Seção única:
        REQUISITOS MÍNIMOS DE QUALIFICAÇÃO
        ...

    5. Casos em que "desejável" aparece no meio do bloco.

    Retorna:
        (texto_obrigatorio, texto_desejavel)
    """

    if not text:
        return "", ""

    # =========================================================
    # 1. NORMALIZAÇÃO
    # =========================================================

    linhas = text.splitlines()

    linhas_norm = []

    for linha in linhas:
        linha = re.sub(r"[ \t]+", " ", linha).strip()

        if linha:
            linhas_norm.append(linha)

    if not linhas_norm:
        return "", ""

    # =========================================================
    # 2. PADRÕES
    # =========================================================

    # Seção que contém qualificações/requisitos.
    #
    # Inclui:
    #   Qualificações profissionais
    #   Qualificações profissionais:
    #   Requisitos mínimos de qualificação
    #   Requisitos obrigatórios
    #   Requisitos mínimos

    padrao_inicio_qualificacao = re.compile(
        r"^\s*"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"(?:"
        r"qualifica[cç][õo]es?\s+"
        r"(?:"
        r"profissionais?"
        r"|m[ií]nimas?"
        r"|obrigat[óo]rias?"
        r"|desej[áa]veis?"
        r"|preferenciais?"
        r")"
        r"|"
        r"requisitos?\s+"
        r"(?:"
        r"m[ií]nimos?"
        r"|obrigat[óo]rios?"
        r"|desej[áa]veis?"
        r"|preferenciais?"
        r")"
        r")"
        r"(?:\s*\([^)]*\))?"
        r"\s*[:\-–—]?\s*$",
        re.IGNORECASE,
    )

    # Marcador de obrigatório.
    padrao_obrigatorio = re.compile(
        r"^\s*"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"(?:"
        r"requisitos?\s+obrigat[óo]rios?"
        r"|qualifica[cç][õo]es?\s+obrigat[óo]rias?"
        r"|qualifica[cç][ãa]o\s+obrigat[óo]ria"
        r"|crit[ée]rios?\s+obrigat[óo]rios?"
        r"|requisitos?\s+m[ií]nimos?"
        r"|qualifica[cç][õo]es?\s+m[ií]nimas?"
        r")"
        r"(?:\s*\([^)]*\))?"
        r"\s*[:\-–—]?"
        r"(?:\s*$|\s+)",
        re.IGNORECASE,
    )

    # Marcador de desejável.
    padrao_desejavel = re.compile(
        r"^\s*"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"(?:"
        r"requisitos?\s+desej[áa]veis?"
        r"|qualifica[cç][õo]es?\s+desej[áa]veis?"
        r"|qualifica[cç][ãa]o\s+desej[áa]vel"
        r"|crit[ée]rios?\s+desej[áa]veis?"
        r"|requisitos?\s+preferenciais?"
        r"|qualifica[cç][õo]es?\s+preferenciais?"
        r"|qualifica[cç][ãa]o\s+preferencial"
        r")"
        # Algumas fontes usam:
        # "Requisitos Desejáveis/Pontuáveis"
        # ou
        # "Qualificações desejáveis e pontuáveis".
        r"(?:\s*/\s*pontu[áa]veis?)?"
        r"(?:\s*\([^)]*\))?"
        r"\s*[:\-–—]?"
        r"(?:\s*$|\s+)",
        re.IGNORECASE,
    )

    # Marcadores inline.
    #
    # Exemplos:
    #
    # Qualificações obrigatórias - Nível superior...
    # Qualificações desejáveis e pontuáveis - Experiência...
    #
    padrao_inline_qualificacao = re.compile(
        r"\b"
        r"(?:"
        r"qualifica[cç][õo]es?"
        r"|requisitos?"
        r")"
        r"\s+"
        r"(obrigat[óo]rias?|desej[áa]veis?|preferenciais?)"
        r"(?:"
        r"\s*(?:e\s+|/)\s*"
        r"pontu[áa]veis?"
        r")?"
        r"(?:"
        r"\s*\([^)]*\)"
        r")?"
        r"(?:"
        r"\s+(?:educa[cç][aã]o|experi[eê]ncia|habilidades?|compet[eê]ncias?|idiomas?)"
        r")?"
        r"\s*"
        r"[*•]?"
        r"\s*"
        r"[:\-–—]"
        r"\s*",
        re.IGNORECASE,
    )

    # =========================================================
    # 3. EXPANDIR MARCADORES INLINE
    # =========================================================
    #
    # Transformamos:
    #
    # Qualificações obrigatórias - A. Qualificações desejáveis - B
    #
    # em:
    #
    # Qualificações obrigatórias
    # A.
    # Qualificações desejáveis
    # B
    #
    # Isso facilita muito a separação posterior.
    # =========================================================

    linhas_expandidas = []

    padrao_desejavel_inline = re.compile(
        r"(?<=\.)\s+(Desej[aá]vel|Desej[aá]veis)(?=\s|$)",
        re.IGNORECASE,
    )

    for linha in linhas_norm:
        encontrados = list(padrao_inline_qualificacao.finditer(linha))

        match_desejavel = padrao_desejavel_inline.search(linha)

        if match_desejavel:
            antes = linha[: match_desejavel.start()].strip()
            depois = linha[match_desejavel.end() :].strip()

            if antes:
                linhas_expandidas.append(antes)

            linhas_expandidas.append("Qualificações desejáveis")

            if depois:
                linhas_expandidas.append(depois)

            continue

        if not encontrados:
            linhas_expandidas.append(linha)
            continue

        posicao = 0

        for match in encontrados:
            antes = linha[posicao : match.start()].strip()

            if antes:
                linhas_expandidas.append(antes)

            tipo = match.group(1).lower()

            if tipo.startswith("obrig"):
                linhas_expandidas.append("Qualificações obrigatórias")
            else:
                linhas_expandidas.append("Qualificações desejáveis")

            posicao = match.end()

        restante = linha[posicao:].strip()

        if restante:
            linhas_expandidas.append(restante)

    linhas_norm = linhas_expandidas

    # =========================================================
    # 4. LOCALIZAR INÍCIO DA SEÇÃO DE QUALIFICAÇÕES
    # =========================================================

    # 4. LOCALIZAR INÍCIO DA SEÇÃO DE QUALIFICAÇÕES

    indice_inicio = None

    for i, linha in enumerate(linhas_norm):
        # "Qualificações desejáveis" pode ter sido criado
        # artificialmente durante a expansão de marcadores inline.
        # Nunca deve ser considerado o início da seção.
        if linha.strip().lower() == "qualificações desejáveis":
            continue

        if padrao_inicio_qualificacao.match(linha):
            indice_inicio = i
            break

    # Se não encontrou seção explícita, procurar diretamente
    # pelos marcadores de obrigatório/desejável.
    if indice_inicio is None:
        for i, linha in enumerate(linhas_norm):
            if padrao_obrigatorio.match(linha):
                indice_inicio = i
                break

            if padrao_desejavel.match(linha):
                # Se o primeiro marcador encontrado for apenas
                # "desejável", pode existir um requisito obrigatório
                # imediatamente antes dele sem marcador próprio.
                #
                # Exemplo do 146182:
                #
                # Mestrado em Estatística...
                # OBSERVAÇÃO: ...
                # Qualificações desejáveis
                # - Doutorado...
                #
                # Nesse caso, não podemos começar a seção no
                # marcador desejável, pois perderíamos o Mestrado.
                #
                # Procuramos para trás o início do bloco de
                # qualificação, usando a última linha claramente
                # estrutural como limite.
                indice_inicio = i

                j = i - 1

                while j >= 0:
                    linha_anterior = linhas_norm[j]

                    # Limites claros de uma seção anterior.
                    if re.match(
                        r"^\s*"
                        r"(?:"
                        r"\d+(?:\.\d+)*[\s.)-]*"
                        r"(?:"
                        r"objetivo|contexto|atividades|atribui[cç][õo]es?|"
                        r"produtos?|entreg[aá]veis?|insumos?|"
                        r"local|prazo|remunera[cç][aã]o|"
                        r"cronograma|processo\s+seletivo"
                        r")"
                        r")\b",
                        linha_anterior,
                        re.IGNORECASE,
                    ):
                        break

                    # Se encontrarmos uma linha vazia, não atravessar
                    # grandes blocos anteriores.
                    if not linha_anterior.strip():
                        break

                    indice_inicio = j
                    j -= 1

                break

    if indice_inicio is None:
        return "", ""

    # =========================================================
    # 5. DEFINIR FIM DA SEÇÃO
    # =========================================================
    #
    # A seção normalmente termina antes de:
    #
    #   Insumos
    #   Produtos
    #   Nome do supervisor
    #   Localidade
    #   Data de início
    #   Critérios de avaliação
    #   Processo seletivo
    #   Produtos x Honorários
    #
    # Não usamos "qualificações" aqui porque a própria seção
    # pode conter vários subtítulos desse tipo.
    # =========================================================

    padrao_fim = re.compile(
        r"^\s*"
        r"(?:"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"insumos?"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"produtos?(?:\s+esperados?)?"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"nome\s+do\s+supervisor"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"cargo\s+do\s+supervisor"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"local(?:idade)?\s+(?:de|do)\s+trabalho"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"data\s+de\s+(?:in[ií]cio|t[eé]rmino)"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"crit[ée]rios?\s+de\s+(?:avalia[cç][ãa]o|pontua[cç][ãa]o)"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"tabela\s+de\s+critérios?\s+(?:pontuáveis?|avaliação|pontuação)"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"processo\s+(?:seletivo|de\s+sele[cç][ãa]o)"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"atividades(?:\s+previstas|\s+a\s+serem\s+desenvolvidas)?"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"termo\s+de\s+refer[eê]ncia"
        r"(?:\s+(?:n[ºo°]|número|no\.?)\s*\d+)?"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"produtos?\s+(?:ou\s+)?resultados?\s+previstos?"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"descri[cç][ãa]o\s+das\s+atividades"
        r"|"
        r"(?:\d+(?:\.\d+)*[\s.)-]*)?"
        r"produtos?\s+x\s+honor[aá]rios"
        r")"
        r"\s*[:\-–—]?\s*$",
        re.IGNORECASE,
    )

    bloco = []

    for linha in linhas_norm[indice_inicio + 1 :]:
        if padrao_fim.match(linha):
            break

        bloco.append(linha)

    # =========================================================
    # 6. CASO EM QUE O PRÓPRIO TÍTULO JÁ É OBRIGATÓRIO
    # =========================================================

    if padrao_obrigatorio.match(linhas_norm[indice_inicio]) and not bloco:
        bloco = []

    # =========================================================
    # 7. SEPARAR O BLOCO
    # =========================================================

    obrigatorio = []
    desejavel = []

    modo = None

    for linha in bloco:
        if re.match(
            r"^\s*[A-Z]\.\s+(?:"
            r"forma[cç][aã]o|"
            r"exig[eê]ncias?|"
            r"requisitos?"
            r")\b",
            linha,
            re.IGNORECASE,
        ):
            modo = "obrigatorio"
            obrigatorio.append(linha)
            continue

        if re.match(
            r"^\s*[A-Z]\.\d+\s+(?:"
            r"forma[cç][aã]o|"
            r"exig[eê]ncias?|"
            r"requisitos?"
            r")\b",
            linha,
            re.IGNORECASE,
        ):
            modo = "obrigatorio"
            obrigatorio.append(linha)
            continue

        # -----------------------------------------------------
        # Marcador explícito de obrigatório
        # -----------------------------------------------------

        if padrao_obrigatorio.match(linha):
            modo = "obrigatorio"

            restante = padrao_obrigatorio.sub(
                "",
                linha,
                count=1,
            ).strip()

            if restante:
                obrigatorio.append(restante)

            continue

        if re.match(
            r"^\s*Requisito\s+m[ií]nimo\b",
            linha,
            re.IGNORECASE,
        ):
            modo = "obrigatorio"
            obrigatorio.append(linha)
            continue

        # -----------------------------------------------------
        # Marcador explícito de desejável
        # -----------------------------------------------------

        if padrao_desejavel.match(linha):
            modo = "desejavel"

            restante = padrao_desejavel.sub(
                "",
                linha,
                count=1,
            ).strip()

            if restante:
                desejavel.append(restante)

            continue

        # -----------------------------------------------------
        # Linhas normais
        # -----------------------------------------------------

        if modo == "desejavel":
            desejavel.append(linha)

        else:
            obrigatorio.append(linha)
            modo = "obrigatorio"

    # =========================================================
    # 8. CASO EM QUE A SEÇÃO COMEÇA DIRETAMENTE COM
    # "QUALIFICAÇÕES PROFISSIONAIS"
    #
    # Exemplo do 146097:
    #
    # Qualificações profissionais
    # Qualificações obrigatórias - Nível superior...
    # ...
    # Qualificações desejáveis e pontuáveis - Experiência...
    #
    # O tratamento acima já deve funcionar, mas fazemos uma
    # segunda proteção para marcadores que tenham permanecido
    # dentro de uma linha.
    # =========================================================

    if obrigatorio and not desejavel:
        texto = " ".join(obrigatorio)

        match = re.search(
            r"\b"
            r"(?:qualifica[cç][õo]es?|requisitos?)"
            r"\s+desej[áa]veis?"
            r"(?:\s+e\s+pontu[áa]veis?)?"
            r"\s*"
            r"[:\-–—]\s*",
            texto,
            flags=re.IGNORECASE,
        )

        if match:
            parte_obrigatoria = texto[: match.start()].strip()
            parte_desejavel = texto[match.end() :].strip()

            obrigatorio = [parte_obrigatoria] if parte_obrigatoria else []

            desejavel = [parte_desejavel] if parte_desejavel else []

    # =========================================================
    # 9. CASO "SERÁ CONSIDERADA DESEJÁVEL"
    # =========================================================
    #
    # Alguns documentos dizem:
    #
    # Especialização, mestrado ou doutorado será considerada
    # desejável.
    #
    # Nesse caso o item foi inicialmente classificado como
    # obrigatório, mas precisa ser transferido.
    # =========================================================

    padrao_fim_desejavel = re.compile(
        r"\b"
        r"(?:"
        r"ser[aá]\s+considerad[oa]"
        r"(?:\s+como)?"
        r"|considerad[oa]"
        r")"
        r"\s+desej[áa]vel"
        r"\b",
        re.IGNORECASE,
    )

    if obrigatorio:
        novo_obrigatorio = []
        novo_desejavel = []

        acumulado = []

        for linha in obrigatorio:
            acumulado.append(linha)

            if padrao_fim_desejavel.search(linha):
                texto_item = " ".join(acumulado).strip()

                if texto_item:
                    novo_desejavel.append(texto_item)

                acumulado = []

        novo_obrigatorio.extend(acumulado)

        if novo_desejavel:
            obrigatorio = novo_obrigatorio
            desejavel = novo_desejavel + desejavel

    # =========================================================
    # 10. LIMPEZA
    # =========================================================

    def limpar(itens: list[str]) -> str:

        resultado = []

        for item in itens:
            item = re.sub(
                r"\s+",
                " ",
                item,
            ).strip()

            if not item:
                continue

            resultado.append(item)

        return "\n".join(resultado).strip()

    return (
        limpar(obrigatorio),
        limpar(desejavel),
    )


def _extrair_graduacoes_contextuais(texto: str) -> list[str]:
    """Extrai graduações somente quando aparecem em contexto de formação."""

    resultados = []

    termos_genericos = {
        "engenharia",
    }

    texto = re.sub(r"\s+", " ", texto)

    # ---------------------------------------------------------
    # Contextos explícitos de formação.
    #
    # Capturamos apenas o trecho imediatamente associado ao
    # marcador de formação.
    # ---------------------------------------------------------

    padroes_contexto = [
        re.compile(
            r"""
            \bgraduac[aã]o\b
            (?:
                \s+(?:completa|conclu[ií]da|em\s+n[ií]vel\s+superior
                |em\s+curso|conclu[ií]da\s+ou\s+em\s+andamento)
            )*
            \s*
            (?:em|nas?\s+areas?\s+de|na\s+area\s+de)
            \s*
            (.{0,250}?)
            (?=;|•|\.|$)
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \bn[ií]vel\s+superior\b
            \s*
            (?:completo|completa|conclu[ií]do|conclu[ií]da)?
            \s*
            (?:em|nas?\s+areas?\s+de|na\s+area\s+de)
            \s*
            (.{0,250}?)
            (?=;|•|\.|$)
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \b(?:bacharelado|licenciatura)\b
            \s*
            (?:em|nas?\s+areas?\s+de|na\s+area\s+de)
            \s*
            (.{0,200}?)
            (?=;|•|\.|$)
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \bforma[cç][aã]o\s+(?:superior|acad[eê]mica)\b
            \s*
            (?:em|nas?\s+areas?\s+de|na\s+area\s+de)
            \s*
            (.{0,200}?)
            (?=;|•|\.|$)
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        ),
    ]

    # ---------------------------------------------------------
    # Procurar os contextos de formação.
    # ---------------------------------------------------------

    trechos = []

    for padrao_contexto in padroes_contexto:
        for match in padrao_contexto.finditer(texto):
            trecho = match.group(1).strip()

            if trecho:
                trechos.append(trecho)

    # ---------------------------------------------------------
    # Procurar os cursos conhecidos dentro de cada contexto.
    #
    # GRAD_PATTERNS continua sendo a fonte de cursos válidos.
    # Assim evitamos considerar qualquer palavra como graduação.
    # ---------------------------------------------------------

    for trecho in trechos:
        for curso in GRAD_PATTERNS:
            padrao_curso = re.compile(
                rf"(?<!\w){re.escape(curso)}(?!\w)",
                flags=re.IGNORECASE,
            )

            if padrao_curso.search(trecho):
                if curso not in resultados:
                    resultados.append(curso)

    # ---------------------------------------------------------
    # Remover termos genéricos quando houver formação específica.
    #
    # Exemplo:
    #
    # engenharia
    # engenharia da computação
    #
    # Resultado:
    #
    # engenharia da computação
    # ---------------------------------------------------------

    resultados_filtrados = [
        curso
        for curso in resultados
        if not (
            curso in termos_genericos
            and any(
                outro != curso and outro.startswith(curso + " ") for outro in resultados
            )
        )
    ]

    return resultados_filtrados


def _find_qualifications(text: str, torid: str) -> dict:
    """Extrai qualificações estruturadas do texto do ToR (regex, sem IA)."""

    result = {
        "torid": torid,
        # Formação
        "graduacao": [],
        "graduacao_desejavel": [],
        "pos_graduacao": [],
        "pos_graduacao_desejavel": [],
        "mestrado": False,
        "mestrado_desejavel": False,
        "doutorado": False,
        "doutorado_desejavel": False,
        # Experiência
        "experiencia_exigida": False,
        "anos_experiencia": None,
        "experiencia_outro_criterio": None,
        "anos_experiencia_desejavel": None,
        # Conhecimentos
        "ferramentas": [],
        "ferramentas_desejaveis": [],
        "idiomas": [],
        "idiomas_desejaveis": [],
        # Certificações
        "certificacoes": [],
        "certificacoes_desejaveis": [],
        # Outros
        "valor": None,
        "area_principal": "",
        "requisitos_obrigatorios": [],
        "requisitos_desejaveis": [],
        "entregaveis": [],
        "competencias": [],
    }

    # ---------------------------------------------------------
    # 1. Separar requisitos obrigatórios e desejáveis
    # ---------------------------------------------------------

    texto_obrigatorio, texto_desejavel = _extrair_secoes_requisitos(text)

    texto_obrigatorio = texto_obrigatorio.lower()
    texto_desejavel = texto_desejavel.lower()

    # ---------------------------------------------------------
    # 2. Guardar as linhas brutas das duas seções
    # ---------------------------------------------------------

    result["requisitos_obrigatorios"] = [
        linha.strip()
        for linha in texto_obrigatorio.splitlines()
        if linha.strip() and len(linha.strip()) > 20
    ][:10]

    result["requisitos_desejaveis"] = [
        linha.strip()
        for linha in texto_desejavel.splitlines()
        if linha.strip() and len(linha.strip()) > 20
    ][:10]

    # ---------------------------------------------------------
    # 3. Graduação
    # ---------------------------------------------------------
    #
    # A graduação precisa ser identificada em contexto de formação.
    #
    # Não procuramos simplesmente cada curso em toda a seção,
    # porque termos como "políticas públicas" podem aparecer em
    # experiência, objeto da consultoria ou área de atuação.
    # ---------------------------------------------------------

    result["graduacao"] = _extrair_graduacoes_contextuais(texto_obrigatorio)

    result["graduacao_desejavel"] = _extrair_graduacoes_contextuais(texto_desejavel)

    # ---------------------------------------------------------
    # 4. Pós-graduação
    # ---------------------------------------------------------
    #
    # Não extraímos a área/curso da pós-graduação.
    #
    # Neste momento interessa apenas saber se o edital exige
    # algum tipo de pós-graduação, ou se isso aparece como
    # requisito desejável.
    #
    # A área específica poderá ser consultada pelo usuário
    # diretamente no edital.
    # ---------------------------------------------------------

    POS_GRADUACAO_PATTERNS = [
        "pós-graduação",
        "pos-graduação",
        "especialização",
        "lato sensu",
        "mba",
    ]

    result["pos_graduacao"] = any(
        term in texto_obrigatorio for term in POS_GRADUACAO_PATTERNS
    )

    result["pos_graduacao_desejavel"] = any(
        term in texto_desejavel for term in POS_GRADUACAO_PATTERNS
    )

    # ---------------------------------------------------------
    # 5. Mestrado
    # ---------------------------------------------------------
    #
    # "stricto sensu" NÃO significa necessariamente mestrado.
    # Pode representar mestrado ou doutorado. Portanto, só
    # reconhecemos mestrado quando ele é explicitamente citado.
    # ---------------------------------------------------------

    result["mestrado"] = any(
        termo in texto_obrigatorio
        for termo in [
            "mestrado",
            "mestre",
        ]
    )

    result["mestrado_desejavel"] = any(
        termo in texto_desejavel
        for termo in [
            "mestrado",
            "mestre",
        ]
    )

    # ---------------------------------------------------------
    # 6. Doutorado
    # ---------------------------------------------------------
    #
    # Assim como no mestrado, não inferimos doutorado a partir
    # de "stricto sensu".
    # ---------------------------------------------------------

    result["doutorado"] = any(
        termo in texto_obrigatorio
        for termo in [
            "doutorado",
            "doutor",
            "phd",
        ]
    )

    result["doutorado_desejavel"] = any(
        termo in texto_desejavel
        for termo in [
            "doutorado",
            "doutor",
            "phd",
        ]
    )

    # ---------------------------------------------------------
    # 7. Experiência
    # ---------------------------------------------------------
    #
    # Regra:
    #
    # - experiencia_exigida = True quando há experiência na seção
    #   obrigatória.
    #
    # - anos_experiencia recebe o número quando o requisito é
    #   expresso em anos ou meses.
    #
    # - Aceita formatos como:
    #
    #       3 anos
    #       03 anos
    #       3 (três) anos
    #       03 (três) anos
    #       6 meses
    #       6 (seis) meses
    #
    # - experiencia_outro_criterio recebe o texto quando existe
    #   exigência de experiência, mas ela é expressa por outro
    #   critério, como:
    #
    #       "mínimo de 3 projetos"
    #       "mínimo de 3 projetos/consultorias"
    #       "6 contratos distintos"
    #
    # - Experiência mencionada apenas nos requisitos desejáveis
    #   não torna experiencia_exigida verdadeira.
    # ---------------------------------------------------------

    experiencia_exigida = False
    anos_experiencia = None
    experiencia_outro_criterio = None

    texto_experiencia = texto_obrigatorio or ""

    # ---------------------------------------------------------
    # 7.1. Verificar se experiência é obrigatória
    # ---------------------------------------------------------

    padrao_experiencia_obrigatoria = re.compile(
        r"\bexperi[eê]ncia\b",
        re.IGNORECASE,
    )

    if padrao_experiencia_obrigatoria.search(texto_experiencia):
        experiencia_exigida = True

    # ---------------------------------------------------------
    # 7.2. Extrair anos/meses de experiência
    # ---------------------------------------------------------

    padrao_experiencia = re.compile(
        r"""
        (?:
            experiência
            .*?
            (?:
                mínima?
                |
                mínimo
                |
                no\s+mínimo
            )
            \s*(?:de\s*)?
            (\d+)
            (?:\s*\([^)]*\))?
            \s*
            (anos?|meses?)
        )
        |
        (?:
            mínima?
            |
            mínimo
            |
            no\s+mínimo
        )
        \s*(?:de\s*)?
        (\d+)
        (?:\s*\([^)]*\))?
        \s*
        (anos?|meses?)
        \s+de\s+experiência
        """,
        re.IGNORECASE | re.VERBOSE | re.DOTALL,
    )

    match_experiencia = padrao_experiencia.search(texto_experiencia)

    if match_experiencia:
        valor_texto = match_experiencia.group(1) or match_experiencia.group(3)

        unidade = match_experiencia.group(2) or match_experiencia.group(4)

        valor = int(valor_texto)

        if unidade.lower().startswith("mes"):
            anos_experiencia = valor / 12
        else:
            anos_experiencia = valor

    # ---------------------------------------------------------
    # 7.3. Caso haja experiência obrigatória sem quantidade
    # ---------------------------------------------------------
    #
    # Exemplos:
    #
    #   "experiência em monitoramento..."
    #   "experiência comprovada em projetos..."
    #   "mínimo de 3 projetos/consultorias..."
    #   "6 contratos distintos..."
    #
    # Nesse caso não inventamos uma quantidade de anos.
    # Preservamos apenas o critério relacionado à experiência.
    # ---------------------------------------------------------

    if experiencia_exigida and anos_experiencia is None:
        padroes_outro_criterio = [
            re.compile(
                r"(?i)"
                r"(?:experiência|experiência profissional)"
                r".{0,200}?"
                r"(?:mínim[oa]|no mínimo|pelo menos)"
                r".{0,100}?"
                r"\d+"
                r".{0,80}?"
                r"(?:projetos?|consultorias?|contratos?|experiências?)"
                r"[^.;\n]*"
            ),
            re.compile(
                r"(?i)"
                r"(?:mínim[oa]|no mínimo|pelo menos)"
                r".{0,50}?"
                r"\d+"
                r".{0,80}?"
                r"(?:projetos?|consultorias?|contratos?|experiências?)"
                r"[^.;\n]*"
            ),
        ]

        for padrao in padroes_outro_criterio:
            match_outro = padrao.search(texto_experiencia)

            if match_outro:
                experiencia_outro_criterio = re.sub(
                    r"\s+",
                    " ",
                    match_outro.group(0),
                ).strip(" :-–—")
                break

        # Caso exista experiência obrigatória, mas não seja possível
        # identificar uma quantidade ou outro critério estruturado,
        # preservamos uma indicação genérica.
        if experiencia_outro_criterio is None:
            experiencia_outro_criterio = "experiência profissional"

    result["experiencia_exigida"] = experiencia_exigida
    result["anos_experiencia"] = anos_experiencia
    result["experiencia_outro_criterio"] = experiencia_outro_criterio

    # ---------------------------------------------------------
    # 8. Ferramentas
    # ---------------------------------------------------------

    for ferramenta in FERRAMENTAS_LIST:
        padrao = re.compile(
            rf"(?<!\w){re.escape(ferramenta)}(?!\w)",
            flags=re.IGNORECASE,
        )

        if padrao.search(texto_obrigatorio):
            result["ferramentas"].append(ferramenta)

        if padrao.search(texto_desejavel):
            result["ferramentas_desejaveis"].append(ferramenta)

    # ---------------------------------------------------------
    # 9. Idiomas
    # ---------------------------------------------------------

    if "inglês" in texto_obrigatorio or "english" in texto_obrigatorio:
        result["idiomas"].append("Inglês")

    if "espanhol" in texto_obrigatorio or "spanish" in texto_obrigatorio:
        result["idiomas"].append("Espanhol")

    if "inglês" in texto_desejavel or "english" in texto_desejavel:
        result["idiomas_desejaveis"].append("Inglês")

    if "espanhol" in texto_desejavel or "spanish" in texto_desejavel:
        result["idiomas_desejaveis"].append("Espanhol")

    # ---------------------------------------------------------
    # 10. Certificações
    # ---------------------------------------------------------

    for certificacao in CERT_PATTERNS:
        if certificacao in texto_obrigatorio:
            result["certificacoes"].append(certificacao)

        if certificacao in texto_desejavel:
            result["certificacoes_desejaveis"].append(certificacao)

    # ---------------------------------------------------------
    # 11. Valor da contratação
    #
    # Valor não depende da seção de requisitos.
    # Portanto continua sendo procurado no documento inteiro.
    # ---------------------------------------------------------

    valor_match = re.search(
        r"R\$\s*([\d.]+,\d{2})",
        text,
    )

    if not valor_match:
        valor_match = re.search(
            r"valor\s*"
            r"(?:total\s*)?"
            r"(?:da\s*contratação\s*)?"
            r":?\s*"
            r"R\$\s*([\d.]+,\d{2})",
            text.lower(),
        )

    if valor_match:
        result["valor"] = valor_match.group(1)

    # ---------------------------------------------------------
    # 12. Entregáveis
    # ---------------------------------------------------------

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
