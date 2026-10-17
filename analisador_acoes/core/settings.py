"""Configurações do usuário (chave da API, preço mínimo...) salvas em JSON na pasta do usuário.
Windows: %APPDATA%\\AnalisadorAcoes\\settings.json. A chave fica em texto simples nesse arquivo local;
ela nunca é gravada no código nem enviada a ninguém além do próprio brapi.dev."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


def config_dir() -> str:
    override = os.environ.get("ANALISADOR_ACOES_HOME")      # usado nos testes
    if override:
        return override
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "AnalisadorAcoes")
    return os.path.join(os.path.expanduser("~"), ".analisador_acoes")


def _path(path: Optional[str]) -> str:
    return path or os.path.join(config_dir(), "settings.json")


def load_settings(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(_path(path), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: Dict[str, Any], path: Optional[str] = None) -> bool:
    p = _path(path)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.chmod(p, 0o600)      # sem efeito no Windows; restringe o arquivo em Linux/macOS
        except OSError:
            pass
        return True
    except OSError:
        return False
