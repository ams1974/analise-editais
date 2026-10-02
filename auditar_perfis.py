from collections import Counter
from statistics import mean, median

from core.bridge import (
    calcular_match_detalhado,
    carregar_qualificacoes,
    enriquecer_edital,
)
from core.classifier import classificar_edital
from core.perfil import carregar_perfis


LIMIAR = 0.15

# ---------------------------------------------------------
# 1. Carregar dados
# ---------------------------------------------------------

with open("dados/editais_processados.json", encoding="utf-8") as f:
    import json

    editais = json.load(f)

perfis = carregar_perfis()
qualificacoes = carregar_qualificacoes()

print("=" * 70)
print("AUDITORIA DOS PERFIS")
print("=" * 70)

print("\nPerfis encontrados:")
for nome in perfis:
    print(f"  - {nome}")

print(f"\nTotal de editais: {len(editais)}")


# ---------------------------------------------------------
# 2. Classificar/enriquecer editais
# ---------------------------------------------------------

classificados = []

for edital in editais:
    classificado = classificar_edital(edital)
    enriquecido = enriquecer_edital(classificado, qualificacoes)
    classificados.append(enriquecido)


# ---------------------------------------------------------
# 3. Calcular scores de todos os perfis
# ---------------------------------------------------------

resultados = {}

for nome_perfil, perfil in perfis.items():
    resultados[nome_perfil] = []

    for edital in classificados:
        match = calcular_match_detalhado(edital, perfil)

        resultados[nome_perfil].append(
            {
                "id": edital.get("id"),
                "titulo": edital.get("titulo", ""),
                "score": match.get("score", 0),
                "detalhes": match,
            }
        )


# ---------------------------------------------------------
# 4. Resumo estatístico
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("RESUMO POR PERFIL")
print("=" * 70)

for nome_perfil, itens in resultados.items():
    scores = [item["score"] for item in itens]

    acima = [s for s in scores if s >= LIMIAR]
    abaixo = [s for s in scores if s < LIMIAR]

    print(f"\nPERFIL: {nome_perfil}")
    print("-" * 70)
    print(f"Total de editais : {len(scores)}")
    print(f">= {LIMIAR:.2f}         : {len(acima)}")
    print(f"<  {LIMIAR:.2f}         : {len(abaixo)}")
    print(f"Mínimo           : {min(scores):.3f}")
    print(f"Mediana          : {median(scores):.3f}")
    print(f"Média            : {mean(scores):.3f}")
    print(f"Máximo            : {max(scores):.3f}")


# ---------------------------------------------------------
# 5. Distribuição dos scores
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("DISTRIBUIÇÃO DOS SCORES")
print("=" * 70)

faixas = [
    (0.00, 0.05),
    (0.05, 0.10),
    (0.10, 0.15),
    (0.15, 0.20),
    (0.20, 0.30),
    (0.30, 0.40),
    (0.40, 0.50),
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.01),
]

for nome_perfil, itens in resultados.items():
    print(f"\n{nome_perfil}")

    for inicio, fim in faixas:
        quantidade = sum(
            inicio <= item["score"] < fim
            for item in itens
        )

        if quantidade:
            print(
                f"  {inicio:.2f}–{min(fim, 1.0):.2f}: "
                f"{quantidade}"
            )


# ---------------------------------------------------------
# 6. Cinco maiores e cinco menores
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("EXTREMOS DOS SCORES")
print("=" * 70)

for nome_perfil, itens in resultados.items():
    ordenados = sorted(
        itens,
        key=lambda item: item["score"],
        reverse=True,
    )

    print(f"\n{'=' * 70}")
    print(f"PERFIL: {nome_perfil}")
    print("=" * 70)

    print("\n5 MAIORES SCORES")
    for item in ordenados[:5]:
        print(
            f"\n{item['score']:.3f} | "
            f"{item['id']} | "
            f"{item['titulo'][:100]}"
        )

    print("\n5 MENORES SCORES")
    for item in ordenados[-5:]:
        print(
            f"\n{item['score']:.3f} | "
            f"{item['id']} | "
            f"{item['titulo'][:100]}"
        )


# ---------------------------------------------------------
# 7. Casos próximos do limiar
# ---------------------------------------------------------

print("\n" + "=" * 70)
print(f"EDITAIS PRÓXIMOS DO LIMIAR ({LIMIAR})")
print("=" * 70)

for nome_perfil, itens in resultados.items():
    proximos = sorted(
        itens,
        key=lambda item: abs(item["score"] - LIMIAR),
    )[:5]

    print(f"\nPERFIL: {nome_perfil}")

    for item in proximos:
        print(
            f"\nscore={item['score']:.3f} | "
            f"id={item['id']}"
        )
        print(f"titulo={item['titulo'][:120]}")


# ---------------------------------------------------------
# 8. Auditoria dos critérios
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("CONTRIBUIÇÃO DOS CRITÉRIOS")
print("=" * 70)

for nome_perfil, itens in resultados.items():
    print(f"\nPERFIL: {nome_perfil}")
    print("-" * 70)

    contagens = Counter()

    for item in itens:
        detalhes = item["detalhes"]

        for criterio in [
            "areas",
            "competencias",
            "temas",
            "ferramentas",
            "graduacao",
            "pos_graduacao",
            "pos_academica",
            "idiomas",
            "experiencia",
            "valor",
        ]:
            dados = detalhes.get(criterio)

            if not dados:
                continue

            if criterio in {"areas", "competencias", "temas"}:
                if dados.get("match"):
                    contagens[criterio] += 1

            elif criterio == "ferramentas":
                if dados.get("match"):
                    contagens[criterio] += 1

            elif criterio == "graduacao":
                if dados.get("match"):
                    contagens[criterio] += 1

            elif criterio == "pos_graduacao":
                if dados.get("match"):
                    contagens[criterio] += 1

            elif criterio == "pos_academica":
                if (
                    dados.get("mestrado_atendido") is True
                    or dados.get("doutorado_atendido") is True
                ):
                    contagens[criterio] += 1

            elif criterio == "idiomas":
                if dados.get("match"):
                    contagens[criterio] += 1

            elif criterio == "experiencia":
                if dados.get("atendida") is True:
                    contagens[criterio] += 1

            elif criterio == "valor":
                if dados.get("acima_minimo") is True:
                    contagens[criterio] += 1

    for criterio, quantidade in contagens.most_common():
        print(
            f"  {criterio:<20} "
            f"{quantidade:>3} / {len(itens)}"
        )


# ---------------------------------------------------------
# 9. Detalhamento dos casos que passaram pelo limiar
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("DETALHAMENTO DOS MATCHES")
print("=" * 70)

for nome_perfil, itens in resultados.items():
    print(f"\n\n{'#' * 70}")
    print(f"PERFIL: {nome_perfil}")
    print(f"{'#' * 70}")

    ordenados = sorted(
        [item for item in itens if item["score"] >= LIMIAR],
        key=lambda item: item["score"],
        reverse=True,
    )

    for item in ordenados:
        d = item["detalhes"]

        print(
            f"\n{item['score']:.3f} | "
            f"{item['id']} | "
            f"{item['titulo'][:100]}"
        )

        for criterio in [
            "areas",
            "competencias",
            "temas",
            "ferramentas",
            "graduacao",
            "pos_graduacao",
            "pos_academica",
            "idiomas",
            "experiencia",
            "valor",
        ]:
            dados = d.get(criterio)

            if not dados:
                continue

            print(f"  {criterio}:")

            if "match" in dados:
                print(f"    match: {dados['match']}")

            if "exigidas" in dados:
                print(f"    exigidas: {dados['exigidas']}")

            if "evidencias" in dados and dados["evidencias"]:
                print(f"    evidencias: {dados['evidencias']}")

            if criterio == "experiencia":
                print(
                    f"    exigida={dados.get('exigida')} "
                    f"perfil={dados.get('perfil')} "
                    f"atendida={dados.get('atendida')}"
                )

            if criterio == "valor":
                print(
                    f"    edital={dados.get('edital')} "
                    f"minimo={dados.get('minimo_perfil')} "
                    f"acima_minimo={dados.get('acima_minimo')}"
                )

        meta = d.get("metadados", {})
        print(
            f"  peso_aplicavel={meta.get('peso_aplicavel')} "
            f"score_bruto={meta.get('score_bruto')}"
        )

print("\n" + "=" * 70)
print("FIM DA AUDITORIA")
print("=" * 70)
