"""Per-item import ledger for the ima lane.

[INPUT]
- app.database.models::WikiSourceLedgerEntry (POS: ledger ORM row)

[OUTPUT]
- LedgerStatus / InventoryItem / LedgerRow / LedgerCounts
- ImaLedger: upsert_inventory / claim / record_* / mark_remote_deleted / retry_failed / counts / list_rows / synced_paths / has_item

[POS]
Single owner of ledger status transitions. Identity is the item key; ``remote_version`` is the change signal.
Everything the user sees or acts on (counts, reports, retry, compile) is limited to the containers currently
selected, while rows of a deselected library stay in place. A removed raw file is a user decision (``dismissed``)
and is never resurrected; a remote disappearance is informational (``remote_deleted``) and never deletes local evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WikiSourceLedgerEntry

SOURCE = "ima"
MAX_ATTEMPTS = 3


class LedgerStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    TOO_LARGE = "too_large"
    BLOCKED = "blocked"
    DISMISSED = "dismissed"
    REMOTE_DELETED = "remote_deleted"  # unlisted under its old library/folder/title: deleted, renamed or moved
    DUPLICATE = "duplicate"


# Statuses whose item still needs the user's attention (surfaced in the import report).
ATTENTION_STATUSES = (LedgerStatus.FAILED, LedgerStatus.UNSUPPORTED, LedgerStatus.TOO_LARGE, LedgerStatus.BLOCKED)


@dataclass(frozen=True, slots=True)
class InventoryItem:
    item_key: str
    container_id: str
    container_name: str
    remote_id: str
    title: str
    folder_path: str
    media_type: int | None
    remote_version: str
    # Key to use when ``item_key`` already belongs to another item seen in the same pass (same title in one folder).
    fallback_key: str = ""


@dataclass(frozen=True, slots=True)
class LedgerRow:
    item_key: str
    container_id: str
    container_name: str
    remote_id: str
    title: str
    folder_path: str
    media_type: int | None
    remote_version: str
    synced_version: str
    status: str
    fidelity: str
    fidelity_notes: tuple[str, ...]
    raw_path: str
    attempts: int
    error_kind: str


@dataclass(frozen=True, slots=True)
class LedgerCounts:
    by_status: dict[str, int]
    partial: int
    total_chars: int

    @property
    def total(self) -> int:
        return sum(self.by_status.values())

    def of(self, status: LedgerStatus) -> int:
        return self.by_status.get(status.value, 0)


def _to_row(entry: WikiSourceLedgerEntry) -> LedgerRow:
    return LedgerRow(
        item_key=entry.item_key,
        container_id=entry.container_id,
        container_name=entry.container_name,
        remote_id=entry.remote_id,
        title=entry.title,
        folder_path=entry.folder_path,
        media_type=entry.media_type,
        remote_version=entry.remote_version,
        synced_version=entry.synced_version,
        status=entry.status,
        fidelity=entry.fidelity,
        fidelity_notes=tuple(note for note in entry.fidelity_notes.split(",") if note),
        raw_path=entry.raw_path,
        attempts=entry.attempts,
        error_kind=entry.error_kind,
    )


class ImaLedger:
    """Ledger operations for one agent scope. Callers own the session and its commit."""

    def __init__(self, agent_scope: str) -> None:
        self._scope = agent_scope

    def _where(self, containers: Sequence[str] | None = None) -> tuple[ColumnElement[bool], ...]:
        scope = (WikiSourceLedgerEntry.agent_scope == self._scope, WikiSourceLedgerEntry.source == SOURCE)
        if containers is None:
            return scope
        return (*scope, WikiSourceLedgerEntry.container_id.in_(list(containers)))

    async def upsert_inventory(
        self,
        db: AsyncSession,
        items: Sequence[InventoryItem],
        *,
        generation: int,
        raw_exists: Callable[[str], bool],
    ) -> int:
        """Record a batch of inventoried items and return how many are new.

        Two items can share one key (same title in one folder). An item that already owns a row keeps it, so the
        order of a listing never moves documents between rows. Otherwise the first item seen in a pass takes the
        key and later ones move to their ``fallback_key``; the claim is read back from rows this pass already
        stamped, so a page that is fetched again after a restart resolves to the same keys.
        """
        if not items:
            return 0
        keys = {key for item in items for key in (item.item_key, item.fallback_key) if key}
        existing = {
            entry.item_key: entry
            for entry in (
                await db.execute(select(WikiSourceLedgerEntry).where(*self._where(), WikiSourceLedgerEntry.item_key.in_(keys)))
            ).scalars()
        }

        def holder_of(key: str) -> str | None:
            """The remote item that already claimed *key* in this pass (new rows are registered as they are built)."""
            entry = existing.get(key)
            return entry.remote_id if entry is not None and entry.seen_generation == generation else None

        def key_of(item: InventoryItem, remote_id: str) -> str:
            for key in (item.item_key, item.fallback_key):
                entry = existing.get(key)
                if entry is not None and entry.remote_id == remote_id:
                    return key
            if item.fallback_key and holder_of(item.item_key) not in (None, remote_id):
                return item.fallback_key
            return item.item_key

        added = 0
        for item in items:
            remote_id = item.remote_id[:256]
            key = key_of(item, remote_id)
            entry = existing.get(key)
            if entry is None:
                existing[key] = entry = WikiSourceLedgerEntry(
                    agent_scope=self._scope,
                    source=SOURCE,
                    item_key=key,
                    container_id=item.container_id,
                    container_name=item.container_name[:256],
                    remote_id=remote_id,
                    title=item.title[:512],
                    folder_path=item.folder_path[:512],
                    media_type=item.media_type,
                    remote_version=item.remote_version[:128],
                    status=LedgerStatus.PENDING.value,
                    seen_generation=generation,
                )
                db.add(entry)
                added += 1
                continue
            self._refresh(entry, item, generation=generation, raw_exists=raw_exists)
        return added

    @staticmethod
    def _refresh(
        entry: WikiSourceLedgerEntry,
        item: InventoryItem,
        *,
        generation: int,
        raw_exists: Callable[[str], bool],
    ) -> None:
        entry.seen_generation = generation
        entry.container_name = item.container_name[:256]
        entry.remote_id = item.remote_id[:256]
        entry.title = item.title[:512]
        entry.folder_path = item.folder_path[:512]
        entry.media_type = item.media_type
        if entry.status == LedgerStatus.DISMISSED:
            return
        if entry.raw_path and entry.synced_version and not raw_exists(entry.raw_path):
            entry.status = LedgerStatus.DISMISSED.value
            return
        if entry.remote_version != item.remote_version[:128]:
            entry.remote_version = item.remote_version[:128]
            if entry.status != LedgerStatus.PENDING:
                entry.status = LedgerStatus.PENDING.value
                entry.attempts = 0
                entry.error_kind = ""
        elif entry.status == LedgerStatus.REMOTE_DELETED:
            restored = entry.raw_path and entry.synced_version == entry.remote_version
            entry.status = (LedgerStatus.SYNCED if restored else LedgerStatus.PENDING).value

    async def claim(
        self,
        db: AsyncSession,
        *,
        limit: int,
        containers: Sequence[str],
        exclude: Iterable[str] = (),
    ) -> list[LedgerRow]:
        """Next rows to import from *containers*: pending first, then failed rows that still have attempts left."""
        excluded = list(exclude)
        rows: list[LedgerRow] = []
        for status, extra in (
            (LedgerStatus.PENDING, ()),
            (LedgerStatus.FAILED, (WikiSourceLedgerEntry.attempts < MAX_ATTEMPTS,)),
        ):
            if len(rows) >= limit:
                break
            query = (
                select(WikiSourceLedgerEntry)
                .where(
                    *self._where(),
                    WikiSourceLedgerEntry.status == status.value,
                    WikiSourceLedgerEntry.container_id.in_(list(containers)),
                    *extra,
                )
                .order_by(WikiSourceLedgerEntry.created_at, WikiSourceLedgerEntry.item_key)
                .limit(limit - len(rows))
            )
            if excluded:
                query = query.where(WikiSourceLedgerEntry.item_key.not_in(excluded))
            rows.extend(_to_row(entry) for entry in (await db.execute(query)).scalars())
        return rows

    async def _update(self, db: AsyncSession, item_key: str, **values: object) -> None:
        await db.execute(
            update(WikiSourceLedgerEntry).where(*self._where(), WikiSourceLedgerEntry.item_key == item_key).values(**values)
        )

    async def record_synced(
        self,
        db: AsyncSession,
        row: LedgerRow,
        *,
        raw_path: str,
        fidelity: str,
        notes: Sequence[str],
        char_count: int,
    ) -> None:
        await self._update(
            db,
            row.item_key,
            status=LedgerStatus.SYNCED.value,
            synced_version=row.remote_version,
            raw_path=raw_path[:512],
            fidelity=fidelity,
            fidelity_notes=",".join(notes)[:128],
            char_count=char_count,
            attempts=0,
            error_kind="",
        )

    async def record_terminal(self, db: AsyncSession, row: LedgerRow, status: LedgerStatus, *, reason: str = "") -> None:
        """Deterministic outcomes that retrying cannot change (unsupported / too large / blocked / duplicate)."""
        await self._update(db, row.item_key, status=status.value, error_kind=reason[:24], attempts=0)

    async def record_failure(self, db: AsyncSession, row: LedgerRow, *, kind: str, final: bool = False) -> None:
        """A failed attempt; ``final`` exhausts the retry budget for failures that retrying cannot fix."""
        await self._update(
            db,
            row.item_key,
            status=LedgerStatus.FAILED.value,
            attempts=MAX_ATTEMPTS if final else row.attempts + 1,
            error_kind=kind[:24],
        )

    async def mark_remote_deleted(self, db: AsyncSession, *, generation: int, container_ids: Sequence[str]) -> int:
        """Rows in fully-inventoried containers that this generation did not see are gone remotely."""
        if not container_ids:
            return 0
        result = await db.execute(
            update(WikiSourceLedgerEntry)
            .where(
                *self._where(),
                WikiSourceLedgerEntry.container_id.in_(list(container_ids)),
                WikiSourceLedgerEntry.seen_generation < generation,
                WikiSourceLedgerEntry.status.not_in([LedgerStatus.REMOTE_DELETED.value, LedgerStatus.DISMISSED.value]),
            )
            .values(status=LedgerStatus.REMOTE_DELETED.value)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def retry_failed(self, db: AsyncSession, containers: Sequence[str]) -> int:
        result = await db.execute(
            update(WikiSourceLedgerEntry)
            .where(*self._where(containers), WikiSourceLedgerEntry.status == LedgerStatus.FAILED.value)
            .values(status=LedgerStatus.PENDING.value, attempts=0, error_kind="")
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def counts(self, db: AsyncSession, containers: Sequence[str]) -> LedgerCounts:
        scope = self._where(containers)
        grouped = (
            await db.execute(
                select(WikiSourceLedgerEntry.status, func.count()).where(*scope).group_by(WikiSourceLedgerEntry.status)
            )
        ).all()
        synced_where = (*scope, WikiSourceLedgerEntry.status == LedgerStatus.SYNCED.value)
        partial = (
            await db.execute(select(func.count()).where(*synced_where, WikiSourceLedgerEntry.fidelity == "partial"))
        ).scalar_one()
        chars = (
            await db.execute(select(func.coalesce(func.sum(WikiSourceLedgerEntry.char_count), 0)).where(*synced_where))
        ).scalar_one()
        return LedgerCounts(
            by_status={status: int(count) for status, count in grouped}, partial=int(partial), total_chars=int(chars)
        )

    async def list_rows(
        self,
        db: AsyncSession,
        *,
        containers: Sequence[str],
        statuses: Sequence[LedgerStatus] = (),
        partial_only: bool = False,
        limit: int = 100,
    ) -> list[LedgerRow]:
        query = select(WikiSourceLedgerEntry).where(*self._where(containers))
        if statuses:
            query = query.where(WikiSourceLedgerEntry.status.in_([status.value for status in statuses]))
        if partial_only:
            query = query.where(
                WikiSourceLedgerEntry.status == LedgerStatus.SYNCED.value, WikiSourceLedgerEntry.fidelity == "partial"
            )
        query = query.order_by(WikiSourceLedgerEntry.updated_at.desc(), WikiSourceLedgerEntry.item_key).limit(limit)
        return [_to_row(entry) for entry in (await db.execute(query)).scalars()]

    async def synced_paths(self, db: AsyncSession, containers: Sequence[str]) -> list[str]:
        rows = await db.execute(
            select(WikiSourceLedgerEntry.raw_path).where(
                *self._where(containers),
                WikiSourceLedgerEntry.status == LedgerStatus.SYNCED.value,
                WikiSourceLedgerEntry.raw_path != "",
            )
        )
        return [path for (path,) in rows.all()]

    async def has_item(self, db: AsyncSession, item_key: str) -> bool:
        """Whether a row with this key exists and still stands (used to avoid importing a linked note twice)."""
        found = await db.execute(
            select(WikiSourceLedgerEntry.item_key).where(
                *self._where(),
                WikiSourceLedgerEntry.item_key == item_key,
                WikiSourceLedgerEntry.status != LedgerStatus.REMOTE_DELETED.value,
            )
        )
        return found.first() is not None
