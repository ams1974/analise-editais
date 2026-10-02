import gzip
import re
from pathlib import Path

from core.tor_pipeline import _find_qualifications
from core.tor_texts import _slug


TEXT_DIR = Path("dados_brutos/tors_texto")


# =========================================================
# 1. Ler documento
# =========================================================

def ler_texto(caminho):
    return gzip.decompress(caminho.read_bytes()).decode("utf-8")


# =========================================================
# 2. Localizar seção de qualificações
# =========================================================

def encontrar_secao_qualificacoes(texto):
    linhas = texto.splitlines()

    inicio = None
    fim = len(linhas)

    padrao_inicio = re.compile(
        r"^\s*(?:\d+[\.\)]\s*)?"
        r"qualifica[cç][õo]es?\s+profissionais?"
        r"\s*$",
        re.IGNORECASE,
    )

    # Também aceita "Qualificação mínima", "Requisitos..."
    padrao_alternativo = re.compile(
        r"^\s*(?:\d+[\.\)]\s*)?"
        r"(?:qualifica[cç][aã]o\s+m[ií]nima|"
        r"requisitos\s+(?:obrigat[oó]rios|de\s+qualifica[cç][aã]o))"
        r".*$",
        re.IGNORECASE,
    )

    for i, linha in enumerate(linhas):
        if padrao_inicio.match(linha.strip()):
            inicio = i
            break

        if padrao_alternativo.match(linha.strip()):
            inicio = i
            break

    if inicio is None:
        return ""

    # Próximas seções típicas do ToR.
    padrao_fim = re.compile(
        r"^\s*\d+[\.\)]\s+"
        r"(?:"
        r"insumos?"
        r"|nome\s+do\s+supervisor"
        r"|cargo\s+do\s+supervisor"
        r"|localidade"
        r"|data\s+de\s+in[ií]cio"
        r"|data\s+de\s+t[eé]rmino"
        r"|produtos?"
        r"|produtos?\s+x\s+honor[aá]rios"
        r")",
        re.IGNORECASE,
    )

    for i in range(inicio + 1, len(linhas)):
        if padrao_fim.match(linhas[i].strip()):
            fim = i
            break

    return "\n".join(linhas[inicio:fim])


# =========================================================
# 3. Encontrar contexto de graduação dentro da seção
# =========================================================

def encontrar_contextos_graduacao(secao):
    linhas = secao.splitlines()

    resultados = []

    padrao = re.compile(
        r"\b("
        r"gradua[cç][aã]o"
        r"|graduado"
        r"|bacharelado"
        r"|bacharel"
        r"|n[ií]vel\s+superior"
        r"|forma[cç][aã]o\s+superior"
        r")\b",
        re.IGNORECASE,
    )

    for i, linha in enumerate(linhas):
        if not padrao.search(linha):
            continue

        inicio = max(0, i - 2)
        fim = min(len(linhas), i + 5)

        contexto = "\n".join(
            linhas[inicio:fim]
        ).strip()

        if contexto not in resultados:
            resultados.append(contexto)

    return resultados


# =========================================================
# 4. Classificar apenas o que o documento permite observar
# =========================================================

def classificar_documento(contextos):
    if not contextos:
        return "SEM CONTEXTO DE GRADUAÇÃO"

    return "COM CONTEXTO DE GRADUAÇÃO"


# =========================================================
# 5. Executar diagnóstico
# =========================================================

diagnosticos = []

for caminho in sorted(TEXT_DIR.glob("*.txt.gz")):

    torid = caminho.name[:-7]

    texto = ler_texto(caminho)

    atual = _find_qualifications(texto, torid)

    secao = encontrar_secao_qualificacoes(texto)

    contextos = encontrar_contextos_graduacao(secao)

    diagnosticos.append(
        {
            "torid": torid,
            "graduacao_atual": atual.get("graduacao", []),
            "graduacao_desejavel_atual": atual.get(
                "graduacao_desejavel",
                [],
            ),
            "secao": secao,
            "contextos": contextos,
            "status_documento": classificar_documento(
                contextos
            ),
        }
    )


# =========================================================
# 6. Relatório
# =========================================================

saida = Path("/tmp/diagnostico_graduacoes_documentos_89.txt")

with saida.open("w", encoding="utf-8") as f:

    f.write("=" * 80 + "\n")
    f.write("VALIDAÇÃO DE GRADUAÇÕES — DOCUMENTOS REAIS\n")
    f.write("=" * 80 + "\n\n")

    f.write(
        f"ToRs analisados: {len(diagnosticos)}\n"
    )

    com_contexto = sum(
        d["status_documento"]
        == "COM CONTEXTO DE GRADUAÇÃO"
        for d in diagnosticos
    )

    sem_contexto = len(diagnosticos) - com_contexto

    f.write(
        f"Com contexto de graduação: {com_contexto}\n"
    )
    f.write(
        f"Sem contexto encontrado: {sem_contexto}\n\n"
    )

    for d in diagnosticos:

        f.write("-" * 80 + "\n")
        f.write(f"ToR: {d['torid']}\n")
        f.write("-" * 80 + "\n\n")

        f.write("EXTRATOR ATUAL\n")
        f.write(
            f"  graduação: "
            f"{d['graduacao_atual']}\n"
        )
        f.write(
            f"  graduação desejável: "
            f"{d['graduacao_desejavel_atual']}\n\n"
        )

        f.write("CONTEXTO ENCONTRADO NO DOCUMENTO\n")

        if d["contextos"]:
            for numero, contexto in enumerate(
                d["contextos"],
                1,
            ):
                f.write(
                    f"\n[{numero}]\n"
                    f"{contexto}\n"
                )
        else:
            f.write(
                "  Nenhum contexto encontrado.\n"
            )

        f.write("\n")


print("=" * 80)
print("VALIDAÇÃO DE GRADUAÇÕES — DOCUMENTOS REAIS")
print("=" * 80)
print(f"ToRs analisados       : {len(diagnosticos)}")
print(f"Com contexto          : {com_contexto}")
print(f"Sem contexto          : {sem_contexto}")
print()
print(f"Relatório: {saida}")
