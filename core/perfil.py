import json
import logging

from core.config import PERFIS_DIR

logger = logging.getLogger(__name__)


def carregar_perfis() -> dict[str, dict]:
    perfis = {}
    if PERFIS_DIR.exists():
        for arquivo in PERFIS_DIR.glob("*.json"):
            nome = arquivo.stem
            try:
                perfis[nome] = json.loads(arquivo.read_text())
            except (json.JSONDecodeError, KeyError):
                logger.warning("Perfil inválido ignorado: %s", arquivo.name)
    return perfis


def carregar_perfil(nome: str) -> dict | None:
    arquivo = PERFIS_DIR / f"{nome}.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text())
    return None
