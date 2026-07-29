"""Search provider config normalization and migration.

[INPUT]
- searchServices config list (POS: Legacy role primary/fallback entries)

[OUTPUT]
- migrate_search_service_configs: Normalize to priority-ordered configs

[POS]
One-time search catalog config migration for Omni searchServices schema.
"""

from __future__ import annotations


def migrate_search_service_configs(configs: list[dict[str, object]]) -> list[dict[str, object]]:
    """One-time migration: legacy role primary/fallback → priority integers."""
    if not configs:
        return configs

    needs_migration = any(isinstance(item, dict) and "role" in item and "priority" not in item for item in configs)
    if not needs_migration:
        return configs

    migrated: list[dict[str, object]] = []
    for item in configs:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if "priority" not in row and "role" in row:
            role = str(row.get("role", "primary"))
            row["priority"] = 1 if role == "primary" else 2
            row.pop("role", None)
        migrated.append(row)

    # Assign priorities for any remaining rows without priority
    next_priority = max((int(r.get("priority", 0)) for r in migrated if isinstance(r.get("priority"), int)), default=0) + 1
    for row in migrated:
        if "priority" not in row:
            row["priority"] = next_priority
            next_priority += 1
    return migrated
