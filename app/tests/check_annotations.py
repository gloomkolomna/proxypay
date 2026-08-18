"""Проверка аннотаций типов на «eager»-ошибки Python 3.12 (PEP 649 в 3.14 ленив).

На 3.14 аннотации вычисляются лениво, поэтому NameError вида
`name 'Response' is not defined` локально не воспроизводится, но роняет прод
на 3.12 (см. инцидент 2026-08-18: auth.py, gunicorn exit 3).
typing.get_type_hints форсирует вычисление аннотаций — ловит такие имена.

Запуск: venv/Scripts/python app/tests/check_annotations.py
"""

import importlib
import os
import pkgutil
import sys
import typing
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import main  # noqa: E402  (проверяемый монолит целиком)
import routes  # noqa: E402
import services  # noqa: E402

MODULES = [main]
for _m in pkgutil.walk_packages(routes.__path__, prefix="routes."):
    MODULES.append(importlib.import_module(_m.name))
for _m in pkgutil.walk_packages(services.__path__, prefix="services."):
    MODULES.append(importlib.import_module(_m.name))
for _name in ("games", "security", "moneta", "db", "models", "auth"):
    MODULES.append(importlib.import_module(_name))

failures = []
for module in MODULES:
    for name, obj in vars(module).items():
        if getattr(obj, "__module__", None) != module.__name__:
            continue  # импортированное извне — не наш код
        try:
            if not callable(obj):
                continue
            typing.get_type_hints(obj)
        except Exception as exc:
            failures.append(f"{module.__name__}.{name}: {type(exc).__name__}: {exc}")

if failures:
    print("EAGER-ANNOTATION FAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print(f"OK: аннотации всех {len(MODULES)} модулей вычисляются без ошибок")
