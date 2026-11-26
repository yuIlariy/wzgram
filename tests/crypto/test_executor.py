import os

from pyrogram.crypto.executor import _default_crypto_workers


def test_crypto_workers_cap_at_eight_on_big_hosts(monkeypatch):
    monkeypatch.delenv("WZGRAM_CRYPTO_WORKERS", raising=False)

    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    assert _default_crypto_workers() == 8

    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    assert _default_crypto_workers() == 4

    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    assert _default_crypto_workers() == 2


def test_crypto_workers_env_override(monkeypatch):
    monkeypatch.setenv("WZGRAM_CRYPTO_WORKERS", "3")
    assert _default_crypto_workers() == 3

    monkeypatch.setenv("WZGRAM_CRYPTO_WORKERS", "junk")
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    assert _default_crypto_workers() == 8
