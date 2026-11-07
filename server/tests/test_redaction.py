"""PRD section 10 and acceptance criterion 6 — synthetic secrets never appear
raw in logs, prompts, reports or stored screenshots."""

from __future__ import annotations

import pytest

from pt_agent.evidence import (
    REDACTED,
    RedactionError,
    assert_clean,
    fingerprint,
    redact,
)

ORG_KEY = b"test-org-hmac-key-32-bytes-long!!"


def test_password_redacted():
    r = redact("login: user=admin password=SuperSecret123", org_key=ORG_KEY)
    assert "SuperSecret123" not in r.text
    assert REDACTED in r.text
    assert r.had_secrets


def test_aws_key_redacted_and_fingerprinted():
    r = redact("key AKIAIOSFODNN7EXAMPLE here", org_key=ORG_KEY)
    assert "AKIAIOSFODNN7EXAMPLE" not in r.text
    assert "aws_key" in r.fingerprints


def test_authorization_header_redacted():
    r = redact("Authorization: Bearer abcdef123456\n", org_key=ORG_KEY)
    assert "abcdef123456" not in r.text


def test_private_key_redacted():
    blob = "-----BEGIN PRIVATE KEY-----\nMIIBVgIBADANBg\n-----END PRIVATE KEY-----"
    r = redact(blob, org_key=ORG_KEY)
    assert "MIIBVgIBADANBg" not in r.text


def test_fingerprint_is_hmac_not_plain_hash():
    # Same value, different keys -> different fingerprints (keyed HMAC).
    a = fingerprint("weakpass", org_key=b"key-one-xxxxxxxxxxxxxxxxxxxxxxxx")
    b = fingerprint("weakpass", org_key=b"key-two-xxxxxxxxxxxxxxxxxxxxxxxx")
    assert a != b
    assert len(a) == 64  # sha256 hex


def test_fingerprint_requires_key():
    with pytest.raises(RedactionError):
        fingerprint("x", org_key=b"")


def test_assert_clean_raises_on_leftover():
    with pytest.raises(RedactionError):
        assert_clean("token=AKIAIOSFODNN7EXAMPLE")


def test_assert_clean_passes_on_redacted():
    r = redact("api_key=plaintextsecret", org_key=ORG_KEY)
    assert_clean(r.text)  # should not raise


def test_assert_clean_does_not_bridge_across_placeholder():
    """Regression: 'password=[REDACTED] seen' must not be flagged."""
    r = redact("password=Hunter22 seen", org_key=ORG_KEY)
    assert "Hunter22" not in r.text
    assert_clean(r.text)


def test_assert_clean_still_catches_second_secret():
    with pytest.raises(RedactionError):
        assert_clean("password=[REDACTED] token=stillhere123")
