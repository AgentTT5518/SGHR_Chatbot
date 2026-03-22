"""
Unit tests for backend.lib.session_signer — HMAC session signing & verification.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.lib.session_signer import (
    create_signed_session,
    sign_existing,
    verify_session_id,
)


class TestCreateSignedSession:
    def test_creates_uuid_dot_signature_format(self):
        signed = create_signed_session()
        parts = signed.split(".")
        assert len(parts) == 2
        # UUID part should look like a UUID (36 chars with hyphens)
        assert len(parts[0]) == 36
        # Signature is 16-char hex
        assert len(parts[1]) == 16

    def test_each_call_returns_unique_session(self):
        s1 = create_signed_session()
        s2 = create_signed_session()
        assert s1 != s2


class TestVerifySessionId:
    def test_valid_signed_session(self):
        signed = create_signed_session()
        raw = verify_session_id(signed)
        assert raw is not None
        assert "." not in raw
        assert raw == signed.rsplit(".", 1)[0]

    def test_tampered_signature_rejected(self):
        signed = create_signed_session()
        uuid_part = signed.rsplit(".", 1)[0]
        tampered = f"{uuid_part}.0000000000000000"
        assert verify_session_id(tampered) is None

    def test_tampered_uuid_rejected(self):
        signed = create_signed_session()
        sig_part = signed.rsplit(".", 1)[1]
        tampered = f"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.{sig_part}"
        assert verify_session_id(tampered) is None

    def test_none_returns_none(self):
        assert verify_session_id(None) is None

    def test_empty_string_returns_none(self):
        assert verify_session_id("") is None

    def test_unsigned_legacy_id_accepted_in_grace_period(self):
        with patch("backend.lib.session_signer.settings") as mock_settings:
            mock_settings.session_signing_enforced = False
            mock_settings.effective_secret_key = "test-key"
            result = verify_session_id("legacy-unsigned-uuid")
        assert result == "legacy-unsigned-uuid"

    def test_unsigned_legacy_id_rejected_when_enforced(self):
        with patch("backend.lib.session_signer.settings") as mock_settings:
            mock_settings.session_signing_enforced = True
            mock_settings.effective_secret_key = "test-key"
            result = verify_session_id("legacy-unsigned-uuid")
        assert result is None


class TestSignExisting:
    def test_signs_and_verifies_round_trip(self):
        raw_id = "test-session-123"
        signed = sign_existing(raw_id)
        assert "." in signed
        assert verify_session_id(signed) == raw_id

    def test_consistent_signature(self):
        raw_id = "test-session-456"
        s1 = sign_existing(raw_id)
        s2 = sign_existing(raw_id)
        assert s1 == s2
