#!/usr/bin/env python3

import json
from pathlib import Path
from collections import Counter


BASE_DIR = Path(__file__).resolve().parent
ARQUIVO = BASE_DIR / "dados" / "editais_processados.json"


def carregar_editais():
    if not ARQUIVO.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado:\n{ARQUIVO}"
        )

    with open(ARQUIVO, encoding="utf-8") as f:
        dados = json.load(f)

    if not isinstance(dados, list):
        raise ValueError(
            "O arquivo editais_processados.json deveria conter uma lista."
        )

    return dados


def analisar_requisitos(registro):
    requisitos = registro.get("requisitos") or {}

    if not isinstance(requisitos, dict):
        return {}

    return {
        "graduacao": requisitos.get("graduacao") or [],
        "pos_graduacao": requisitos.get("pos_graduacao") or [],
        "mestrado": requisitos.get("mestrado"),
        "doutorado": requisitos.get("doutorado"),
        "anos_experiencia": requisitos.get("anos_experiencia"),
        "ferramentas": requisitos.get("ferramentas") or [],
        "idiomas": requisitos.get("idiomas") or [],
        "certificacoes": requisitos.get("certificacoes") or [],
        "obrigatorios": requisitos.get("obrigatorios") or [],
        "desejaveis": requisitos.get("desejaveis") or [],
        "entregaveis": requisitos.get("entregaveis") or [],
    }


def main():
    print("=" * 80)
    print("DIAGNÓSTICO DETALHADO DAS QUALIFICAÇÕES")
    print("=" * 80)

    editais = carregar_editais()

    print(f"\nTotal de registros: {len(editais)}")

    contadores = {
        "graduacao": 0,
        "pos_graduacao": 0,
        "mestrado": 0,
        "doutorado": 0,
        "anos_experiencia": 0,
        "ferramentas": 0,
        "idiomas": 0,
        "certificacoes": 0,
        "obrigatorios": 0,
        "desejaveis": 0,
        "entregaveis": 0,
    }

    print("\n" + "=" * 80)
    print("REGISTROS COM REQUISITOS")
    print("=" * 80)

    for registro in editais:
        requisitos = analisar_requisitos(registro)

        if not requisitos:
            continue

        for campo in contadores:
            valor = requisitos.get(campo)

            if valor:
                contadores[campo] += 1

        identificador = registro.get("id")
        torid = registro.get("torid")

        print(
            f"\n--- ID {identificador} | TORID {torid} ---"
        )

        print(
            f"graduação: {requisitos['graduacao']}"
        )
        print(
            f"pós-graduação: {requisitos['pos_graduacao']}"
        )
        print(
            f"mestrado: {requisitos['mestrado']}"
        )
        print(
            f"doutorado: {requisitos['doutorado']}"
        )
        print(
            f"anos experiência: {requisitos['anos_experiencia']}"
        )
        print(
            f"ferramentas: {requisitos['ferramentas']}"
        )
        print(
            f"idiomas: {requisitos['idiomas']}"
        )
        print(
            f"certificações: {requisitos['certificacoes']}"
        )

        if requisitos["obrigatorios"]:
            print(
                f"obrigatórios: {len(requisitos['obrigatorios'])}"
            )

        if requisitos["desejaveis"]:
            print(
                f"desejáveis: {len(requisitos['desejaveis'])}"
            )

        if requisitos["entregaveis"]:
            print(
                f"entregáveis: {len(requisitos['entregaveis'])}"
            )

    print("\n" + "=" * 80)
    print("RESUMO DA EXTRAÇÃO")
    print("=" * 80)

    for campo, quantidade in contadores.items():
        print(
            f"{campo:20} {quantidade:4} / {len(editais)}"
        )


if __name__ == "__main__":
    main()
