import json
from datetime import date, datetime
from pathlib import Path

from core.config import (
    EDITAIS_PROCESSADOS_FILE,
    EDITAIS_TODOS_FILE,
    HISTORICO_DIR,
)


def snapshot_path(data: date | None = None) -> Path:
    d = data or date.today()
    diretorio = HISTORICO_DIR / str(d.year) / f"{d.month:02d}"
    diretorio.mkdir(parents=True, exist_ok=True)
    return diretorio / f"editais_{d.isoformat()}.json"


def carregar_editais_todos() -> list:
    if EDITAIS_TODOS_FILE.exists():
        return json.loads(EDITAIS_TODOS_FILE.read_text())
    return []


def carregar_editais_processados() -> list:
    if EDITAIS_PROCESSADOS_FILE.exists():
        return json.loads(EDITAIS_PROCESSADOS_FILE.read_text())
    return []


def salvar_snapshot(editais: list, data: date | None = None) -> Path:
    caminho = snapshot_path(data)
    caminho.write_text(json.dumps(editais, indent=2, ensure_ascii=False))
    return caminho


def atualizar_editais_todos(novos_editais: list) -> tuple[int, int]:
    """Atualiza o arquivo de todos os editais com deduplicação por ID.
    Retorna (novos, atualizados)."""
    existentes = {e["id"]: e for e in carregar_editais_todos()}
    novos = 0
    atualizados = 0

    for edital in novos_editais:
        eid = edital["id"]
        if eid in existentes:
            if edital != existentes[eid]:
                existentes[eid] = edital
                atualizados += 1
        else:
            existentes[eid] = edital
            novos += 1

    todos = sorted(
        existentes.values(), key=lambda e: e.get("startDate", ""), reverse=True
    )
    EDITAIS_TODOS_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False))
    return novos, atualizados


def detectar_novidades(atuais: list, anteriores: list) -> dict:
    """Compara dois snapshots e retorna novos, encerrados e mantidos."""
    ids_atuais = {e["id"] for e in atuais}
    ids_anteriores = {e["id"] for e in anteriores}

    novos_ids = ids_atuais - ids_anteriores
    encerrados_ids = ids_anteriores - ids_atuais
    mantidos_ids = ids_atuais & ids_anteriores

    return {
        "novos": [e for e in atuais if e["id"] in novos_ids],
        "encerrados": [e for e in anteriores if e["id"] in encerrados_ids],
        "mantidos": [e for e in atuais if e["id"] in mantidos_ids],
        "total_atuais": len(atuais),
        "total_anteriores": len(anteriores),
        "novos_count": len(novos_ids),
        "encerrados_count": len(encerrados_ids),
    }


def salvar_processados(editais: list) -> Path:
    EDITAIS_PROCESSADOS_FILE.write_text(
        json.dumps(editais, indent=2, ensure_ascii=False)
    )
    return EDITAIS_PROCESSADOS_FILE


def ultimo_snapshot() -> Path | None:
    """Retorna o caminho do snapshot mais recente."""
    snaps = sorted(HISTORICO_DIR.glob("*/*/editais_*.json"))
    return snaps[-1] if snaps else None


def carregar_ultimo_snapshot() -> list:
    snap = ultimo_snapshot()
    if snap:
        return json.loads(snap.read_text())
    return []


def carregar_editais_historico(meses: int = 12) -> list:
    from datetime import timedelta

    corte = (datetime.now() - timedelta(days=meses * 30)).strftime("%Y-%m-%d")
    todos = carregar_editais_todos()
    return [e for e in todos if e.get("startDate", "")[:10] >= corte]
