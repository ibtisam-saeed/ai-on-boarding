"""Scratch file for manually verifying the Ruff CI integration (Phase 2) against a
real pull request. Contains one deliberate non-autofixable violation (RUF012) and
one deliberate autofixable violation (I001, unsorted imports). Safe to delete once
verification is done.

Placed inside sdd_django_demo/ (not nested in api/ or embargo/) so ruff.yml's
`ruff check sdd_django_demo` actually lints it, without Django's app loading or
pytest's test discovery trying to import it as part of either app.
"""
from pathlib import Path
import sys
import os


class Settings:
    ALLOWED_HOSTS = []


def where_am_i():
    return os.path.dirname(sys.executable) or str(Path.cwd())
