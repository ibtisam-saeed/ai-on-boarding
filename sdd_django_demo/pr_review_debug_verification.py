"""Scratch file for manually verifying the Claude-assisted review with
show_full_output enabled (debugging why a real run's posted comment body was
missing the _Location: line despite a matching fingerprint - see PR #9 and
openspec/changes/add-pr-review-agent/traceability.md). This is the golden PR
fixture from tooling/pr-review/review/tests/fixtures/golden_pr_snippet.py,
copied here so it is part of a real diff. Contains three deliberately planted
issues, each cleanly mapped to exactly one skill, and none of them things Ruff
would ever flag - see that directory's golden_pr_README.md for the expected
findings. Safe to delete once verification is done.

Placed inside sdd_django_demo/ (not nested in api/ or embargo/) so it sits
alongside the Phase 2 scratch file's pattern, without Django's app loading or
pytest's test discovery trying to import it as part of either app.
"""
from django.db import connection

SECRET_API_KEY = "not-a-real-secret-placeholder-abcdef123456"  # planted: security


def get_user_orders(user_id):
    # planted: architecture - hand-written SQL reimplementing what the ORM
    # (Order.objects.filter(user_id=...)) already provides, mixing data access
    # directly into what should be a thin view function. Parameterized, so this is
    # NOT a security/injection issue - purely a "shouldn't be written this way" one.
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM orders WHERE user_id = %s", [user_id])
        return cursor.fetchall()


def process(x):
    # planted: code-quality - "process"/"x" give no indication this computes a
    # discount-adjusted total. Ruff has no rule for unclear naming.
    y = x * 0.9 if x > 100 else x
    return y