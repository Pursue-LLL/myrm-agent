"""Tests for SqliteDeliveryNotifyLedger."""

from __future__ import annotations

from app.channels.reliability.delivery_notify_ledger import SqliteDeliveryNotifyLedger


def test_mark_and_was_notified(tmp_path) -> None:
    db_path = tmp_path / "ledger.db"
    ledger = SqliteDeliveryNotifyLedger(db_path)
    assert ledger.was_notified("delivery-1") is False
    ledger.mark_notified("delivery-1")
    assert ledger.was_notified("delivery-1") is True
    ledger.close()


def test_persists_across_instances(tmp_path) -> None:
    db_path = tmp_path / "ledger.db"
    ledger_a = SqliteDeliveryNotifyLedger(db_path)
    ledger_a.mark_notified("persist-me")
    ledger_a.close()

    ledger_b = SqliteDeliveryNotifyLedger(db_path)
    assert ledger_b.was_notified("persist-me") is True
    ledger_b.close()
