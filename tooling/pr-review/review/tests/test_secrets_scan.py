"""Tests for review.secrets_scan, written from the pr-review spec's "Never disclose
secret values in a finding" requirement.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from review.secrets_scan import REDACTED, redact, scan  # noqa: E402


def test_aws_access_key_is_detected_and_redacted():
    text = "Found credential AKIAABCDEFGHIJKLMNOP in settings.py"
    matched = scan(text)
    assert "aws_access_key_id" in matched
    redacted, hits = redact(text)
    assert "AKIAABCDEFGHIJKLMNOP" not in redacted
    assert REDACTED in redacted
    assert hits == ["aws_access_key_id"]


def test_generic_secret_assignment_is_detected_and_redacted():
    text = 'settings.py line 12: SECRET_KEY = "correct-horse-battery-staple"'
    redacted, hits = redact(text)
    assert "correct-horse-battery-staple" not in redacted
    assert hits == ["generic_secret_assignment"]


def test_private_key_block_is_detected():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    assert "private_key_block" in scan(text)


def test_text_with_no_secret_shape_is_left_unchanged():
    text = "This function is missing a null check before accessing user.profile."
    redacted, hits = redact(text)
    assert redacted == text
    assert hits == []
