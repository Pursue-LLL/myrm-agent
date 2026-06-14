---
name: db-diagnostics
description: >-
  Systematic database health diagnosis workflow for PostgreSQL, MySQL, and SQLite.
  Covers connection pool, slow queries, indexing, locking, and bloat analysis.
  Produces structured diagnostic reports with prioritized optimization recommendations.
version: 1.0.0
category: operations
tags:
  - database
  - diagnostics
  - performance
  - postgresql
  - mysql
  - optimization
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Connect & Profile — verify connectivity and identify database engine"
    - "Phase 2: Connection Health — analyze active connections, pool utilization, idle sessions"
    - "Phase 3: Slow Query Analysis — identify and explain expensive queries with EXPLAIN"
    - "Phase 4: Index Audit — find missing, unused, and redundant indexes"
    - "Phase 5: Lock & Bloat Check — detect lock contention and table/index bloat"
    - "Phase 6: Report — structured findings with severity and optimization plan"
  potential_traps:
    - description: "Running diagnostic queries on production without considering their own performance impact"
      mitigation: "Use non-blocking queries; set statement_timeout; avoid full table scans in diagnostics"
      severity: high
    - description: "Diagnosing symptoms instead of root causes (e.g., blaming slow queries without checking missing indexes)"
      mitigation: "Follow the full diagnostic pipeline; never skip the index audit"
      severity: high
    - description: "Recommending index creation without considering write overhead"
      mitigation: "Always note the write-amplification trade-off for each index recommendation"
      severity: medium
  verification_steps:
    - step_id: connectivity_confirmed
      description: "Database connection is established and engine version identified"
      validation_method: "Successfully run SELECT version() or equivalent"
      is_required: true
    - step_id: all_phases_completed
      description: "All diagnostic phases are executed, none skipped"
      validation_method: "Each phase has at least one finding or an explicit 'healthy' status"
      is_required: true
    - step_id: recommendations_prioritized
      description: "Every recommendation includes severity and estimated impact"
      validation_method: "Each item tagged as Critical/High/Medium/Low with expected improvement"
      is_required: true
  success_criteria: "Complete diagnostic report covering all phases with actionable, prioritized optimizations"
  estimated_duration_seconds: 1200
---

# Database Diagnostics

## Overview

A slow database is never "just slow." There is always a specific, identifiable cause: missing indexes, lock contention, connection exhaustion, or bloated tables. This workflow ensures systematic investigation so the real bottleneck is found — not guessed at.

**Core principle:** Diagnose all layers in order. Never skip phases. A "healthy" finding is still a finding.

## Phase 1: Connect & Profile

Establish connectivity and understand what you're working with.

```bash
# PostgreSQL
psql "$DATABASE_URL" -c "SELECT version();"
psql "$DATABASE_URL" -c "SELECT pg_database_size(current_database()) AS db_size;"

# MySQL
mysql -e "SELECT VERSION();" -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS"
mysql -e "SELECT table_schema, ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb FROM information_schema.tables GROUP BY table_schema;"
```

Record:
- Engine and version
- Database size
- Number of tables
- Replication status (if applicable)

## Phase 2: Connection Health

### PostgreSQL

```sql
-- Active connections by state
SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC;

-- Long-running queries (> 30s)
SELECT pid, now() - query_start AS duration, state, left(query, 80) AS query
FROM pg_stat_activity
WHERE state != 'idle' AND now() - query_start > interval '30 seconds'
ORDER BY duration DESC;

-- Connection utilization vs max
SELECT count(*) AS current, setting::int AS max_connections,
       round(count(*)::numeric / setting::int * 100, 1) AS pct_used
FROM pg_stat_activity, pg_settings WHERE name = 'max_connections'
GROUP BY setting;
```

### MySQL

```sql
-- Connection summary
SHOW STATUS LIKE 'Threads_%';
SHOW VARIABLES LIKE 'max_connections';

-- Long-running queries
SELECT id, user, host, db, time, state, LEFT(info, 80) AS query
FROM information_schema.processlist
WHERE time > 30 AND command != 'Sleep'
ORDER BY time DESC;
```

### Warning Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Connection utilization | < 60% | 60-80% | > 80% |
| Idle connections | < 20% of total | 20-50% | > 50% |
| Queries > 30s | 0 | 1-3 | > 3 |

## Phase 3: Slow Query Analysis

### PostgreSQL

```sql
-- Top 10 slowest query patterns (requires pg_stat_statements)
SELECT left(query, 100) AS query, calls, round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2) AS avg_ms, rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 10;
```

For each slow query, run `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` and look for:

| Red Flag | Meaning |
|----------|---------|
| Seq Scan on large table | Missing index |
| Nested Loop with high row count | Consider Hash or Merge Join |
| Sort with high memory | Add index to avoid sort |
| Buffers: shared read >> shared hit | Data not in cache, table too large or poorly indexed |

### MySQL

```sql
-- Enable slow query log temporarily
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;

-- Analyze with EXPLAIN
EXPLAIN FORMAT=JSON SELECT ...;
```

Look for: `type: ALL` (full table scan), `Using filesort`, `Using temporary`.

## Phase 4: Index Audit

### PostgreSQL

```sql
-- Unused indexes (0 scans since last stats reset)
SELECT schemaname, relname AS table, indexrelname AS index,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size
FROM pg_stat_user_indexes i
JOIN pg_index USING (indexrelid)
WHERE idx_scan = 0 AND NOT indisunique
ORDER BY pg_relation_size(i.indexrelid) DESC;

-- Missing indexes: tables with high sequential scan ratio
SELECT relname, seq_scan, idx_scan,
       CASE WHEN seq_scan + idx_scan > 0
            THEN round(seq_scan::numeric / (seq_scan + idx_scan) * 100, 1)
            ELSE 0 END AS seq_scan_pct,
       pg_size_pretty(pg_relation_size(relid)) AS size
FROM pg_stat_user_tables
WHERE seq_scan > 100 AND pg_relation_size(relid) > 10485760
ORDER BY seq_scan_pct DESC;

-- Duplicate/redundant indexes
SELECT a.indexrelid::regclass AS index_a, b.indexrelid::regclass AS index_b
FROM pg_index a, pg_index b
WHERE a.indrelid = b.indrelid AND a.indexrelid != b.indexrelid
  AND a.indkey::text = left(b.indkey::text, length(a.indkey::text))
  AND a.indexrelid::regclass::text < b.indexrelid::regclass::text;
```

### MySQL

```sql
-- Unused indexes (requires performance_schema)
SELECT object_schema, object_name, index_name
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE index_name IS NOT NULL AND count_star = 0
  AND object_schema NOT IN ('mysql', 'sys', 'performance_schema');

-- Missing indexes: tables with full scans
SELECT object_schema, object_name, count_read AS full_scans
FROM performance_schema.table_io_waits_summary_by_table
WHERE count_read > 1000
ORDER BY count_read DESC LIMIT 20;
```

### Index Recommendation Rules

- Recommend adding index ONLY when: seq_scan_pct > 80% AND table > 10MB
- Recommend dropping index ONLY when: zero scans AND index > 1MB AND not unique
- Always note the write-performance trade-off for new indexes

## Phase 5: Lock & Bloat Check

### PostgreSQL — Locks

```sql
-- Current lock contention
SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query,
       blocking.pid AS blocking_pid, blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid
JOIN pg_locks kl ON kl.locktype = bl.locktype AND kl.relation = bl.relation AND kl.pid != bl.pid
JOIN pg_stat_activity blocking ON blocking.pid = kl.pid
WHERE NOT bl.granted;
```

### PostgreSQL — Table Bloat

```sql
-- Dead tuple ratio (need VACUUM if > 10%)
SELECT relname, n_live_tup, n_dead_tup,
       CASE WHEN n_live_tup > 0
            THEN round(n_dead_tup::numeric / n_live_tup * 100, 1)
            ELSE 0 END AS dead_pct,
       last_autovacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY dead_pct DESC LIMIT 20;
```

### MySQL — Locks

```sql
-- MySQL 8.0+: InnoDB lock waits (innodb_lock_waits removed in 8.0.1)
SELECT waiting.trx_id AS waiting_trx, waiting.trx_query AS waiting_query,
       blocking.trx_id AS blocking_trx, blocking.trx_query AS blocking_query
FROM performance_schema.data_lock_waits w
JOIN information_schema.innodb_trx waiting
  ON waiting.trx_id = w.REQUESTING_ENGINE_TRANSACTION_ID
JOIN information_schema.innodb_trx blocking
  ON blocking.trx_id = w.BLOCKING_ENGINE_TRANSACTION_ID;

-- MySQL 5.7 (legacy): use information_schema.innodb_lock_waits instead
-- SELECT ... FROM information_schema.innodb_lock_waits w
--   JOIN information_schema.innodb_trx waiting ON waiting.trx_id = w.requesting_trx_id
--   JOIN information_schema.innodb_trx blocking ON blocking.trx_id = w.blocking_trx_id;
```

### Bloat Warning Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Dead tuple ratio | < 5% | 5-20% | > 20% |
| Last autovacuum | < 1 day | 1-7 days | > 7 days or never |
| Lock wait count | 0 | 1-5 | > 5 |

## Phase 6: Report

Structure the diagnostic report:

```
## Database Health Report

### Environment
- Engine: PostgreSQL 16.2
- Size: 12.4 GB
- Tables: 87

### Executive Summary
[1-2 sentences: overall health + most critical finding]

### Findings by Phase

#### Connection Health: [HEALTHY / WARNING / CRITICAL]
[Details and metrics]

#### Slow Queries: [HEALTHY / WARNING / CRITICAL]
[Top offenders with EXPLAIN analysis]

#### Index Health: [HEALTHY / WARNING / CRITICAL]
[Missing, unused, redundant indexes]

#### Lock & Bloat: [HEALTHY / WARNING / CRITICAL]
[Contention and bloat status]

### Optimization Plan (Prioritized)

| Priority | Action | Expected Impact | Risk |
|----------|--------|----------------|------|
| 1 | [Most impactful fix] | [Estimated improvement] | [Low/Med/High] |
| 2 | ... | ... | ... |

### Data Quality Notes
[Any caveats: pg_stat_statements not enabled, limited access, etc.]
```
