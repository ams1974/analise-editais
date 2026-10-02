import gzip
import json
import re
from pathlib import Path

from core.tor_pipeline import _find_qualifications
from core.tor_texts import _slug


QUAL_PATH = Path("dados_brutos/qualificacoes_extraidas.json")
TEXT_DIR = Path("dados_brutos/tors_texto")


CAMPOS = [
    "graduacao",
    "graduacao_desejavel",
    "pos_graduacao",
    "pos_graduacao_desejavel",
    "mestrado",
    "mestrado_desejavel",
    "doutorado",
    "doutorado_desejavel",
    "experiencia_exigida",
    "anos_experiencia",
    "anos_experiencia_desejavel",
    "ferramentas",
    "ferramentas_desejaveis",
    "idiomas",
    "idiomas_desejaveis",
]


def normalizar(valor):
    if isinstance(valor, str):
        return re.sub(r"\s+", " ", valor).strip().casefold()

    if isinstance(valor, list):
        return sorted(
            normalizar(x)
            for x in valor
            if x not in (None, "", False)
        )

    return valor


def preenchido(valor):
    return valor not in (None, "", [], False)


def ler_texto(torid):
    caminho = TEXT_DIR / f"{_slug(torid)}.txt.gz"

    if not caminho.exists():
        return None

    return gzip.decompress(caminho.read_bytes()).decode("utf-8")


def registrar_diferenca(
    diferencas,
    campo,
    historico,
    atual,
):
    if normalizar(historico) != normalizar(atual):
        diferencas.append(
            {
                "campo": campo,
                "historico": historico,
                "atual": atual,
            }
        )


# =========================================================
# 1. Carregar qualificações históricas
# =========================================================

with QUAL_PATH.open(encoding="utf-8") as f:
    qualificacoes = json.load(f)


por_torid = {
    str(item.get("torid")): item
    for item in qualificacoes
}


# =========================================================
# 2. Encontrar os textos disponíveis
# =========================================================

textos = {}

for caminho in sorted(TEXT_DIR.glob("*.txt.gz")):
    nome = caminho.name[:-7]  # remove .txt.gz

    # O nome do arquivo é o slug do torid.
    # Procuramos o registro correspondente pelo mesmo slug.
    for torid, registro in por_torid.items():
        if _slug(torid) == nome:
            textos[torid] = gzip.decompress(
                caminho.read_bytes()
            ).decode("utf-8")
            break


# =========================================================
# 3. Diagnóstico geral
# =========================================================

print("=" * 80)
print("DIAGNÓSTICO DOS TEXTOS HISTÓRICOS")
print("=" * 80)

print(f"Qualificações no JSON : {len(qualificacoes)}")
print(f"Textos encontrados    : {len(textos)}")
print(f"Textos sem registro   : {len(textos) - len(set(textos) & set(por_torid))}")
print()


# =========================================================
# 4. Executar o extrator atual
# =========================================================

diagnosticos = []

for torid, texto in sorted(textos.items()):
    historico = por_torid.get(torid)

    if not historico:
        continue

    atual = _find_qualifications(texto, torid)

    diferencas = []

    for campo in CAMPOS:
        valor_historico = historico.get(campo)
        valor_atual = atual.get(campo)

        registrar_diferenca(
            diferencas,
            campo,
            valor_historico,
            valor_atual,
        )

    diagnosticos.append(
        {
            "torid": torid,
            "diferencas": diferencas,
            "historico": historico,
            "atual": atual,
            "texto": texto,
        }
    )


# =========================================================
# 5. Resumo por campo
# =========================================================

print("=" * 80)
print("DIFERENÇAS POR CAMPO")
print("=" * 80)

for campo in CAMPOS:
    casos = [
        d
        for d in diagnosticos
        if any(
            x["campo"] == campo
            for x in d["diferencas"]
        )
    ]

    print(f"{campo:30} {len(casos):3}/{len(diagnosticos)}")


# =========================================================
# 6. Onde o histórico tem informação e o atual perdeu
# =========================================================

print()
print("=" * 80)
print("INFORMAÇÃO HISTÓRICA PERDIDA PELO EXTRATOR ATUAL")
print("=" * 80)

for campo in CAMPOS:
    casos = []

    for d in diagnosticos:
        historico = d["historico"].get(campo)
        atual = d["atual"].get(campo)

        if preenchido(historico) and not preenchido(atual):
            casos.append(d["torid"])

    print(f"{campo:30} {len(casos):3}")

    if casos:
        print("   ", ", ".join(casos))


# =========================================================
# 7. Informação nova produzida pelo atual
# =========================================================

print()
print("=" * 80)
print("INFORMAÇÃO PRODUZIDA PELO ATUAL QUE NÃO ESTÁ NO HISTÓRICO")
print("=" * 80)

for campo in CAMPOS:
    casos = []

    for d in diagnosticos:
        historico = d["historico"].get(campo)
        atual = d["atual"].get(campo)

        if not preenchido(historico) and preenchido(atual):
            casos.append(d["torid"])

    print(f"{campo:30} {len(casos):3}")

    if casos:
        print("   ", ", ".join(casos))


# =========================================================
# 8. Comparação detalhada por ToR
# =========================================================

print()
print("=" * 80)
print("DETALHAMENTO DOS ToRs COM DIFERENÇAS")
print("=" * 80)

for d in diagnosticos:
    if not d["diferencas"]:
        continue

    print()
    print("-" * 80)
    print("ToR:", d["torid"])

    for diferenca in d["diferencas"]:
        print()
        print("CAMPO:", diferenca["campo"])
        print("  HISTÓRICO:")
        print("   ", repr(diferenca["historico"]))
        print("  ATUAL:")
        print("   ", repr(diferenca["atual"]))


# =========================================================
# 9. Resumo dos casos sem nenhuma diferença
# =========================================================

iguais = [
    d["torid"]
    for d in diagnosticos
    if not d["diferencas"]
]

print()
print("=" * 80)
print("RESUMO")
print("=" * 80)

print("ToRs comparados :", len(diagnosticos))
print("Sem diferenças  :", len(iguais))
print("Com diferenças  :", len(diagnosticos) - len(iguais))

print()
print("ToRs sem diferenças:")

for torid in iguais:
    print(" ", torid)
