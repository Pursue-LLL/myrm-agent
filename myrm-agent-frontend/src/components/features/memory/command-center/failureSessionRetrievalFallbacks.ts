/**
 * [INPUT]
 * @/services/memory/failureSessionRetrieval (DTO types)
 *
 * [OUTPUT]
 * Realistic fallback datasets for Failure-Triggered Historical Session Retrieval Suite (Item 109).
 *
 * [POS]
 * command-center feature folder fallback mock data for offline resilience and SSR.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import type {
  FailureRetrievalResultDTO,
  FailureTriggerConfigDTO,
  HistoricalResolutionEntryDTO,
} from '@/services/memory/failureSessionRetrieval';

export const FALLBACK_RESOLUTIONS_CATALOG: HistoricalResolutionEntryDTO[] = [
  {
    entry_id: 'hist_git_push_01',
    session_id: 'sess_git_reject_20260901',
    turn_index: 4,
    error_signature: 'PermissionDeniedError git push rejected by pre-receive hook branch protected',
    outcome_type: 'successful_resolution',
    solution_snippet: 'git checkout -b feat/fix-branch && git push -u origin feat/fix-branch',
    explanation: '直接向 main 分支推送触发了只读保护，切换到特性分支并推送 PR 顺利合入。',
    confidence: 1.0,
    created_at: '2026-09-01T10:00:00Z',
  },
  {
    entry_id: 'hist_port_fail_02',
    session_id: 'sess_port_loop_20260903',
    turn_index: 2,
    error_signature: 'PortAlreadyInUseError address already in use <ADDR> port 8000',
    outcome_type: 'cautionary_failure',
    solution_snippet: 'sleep 5 && retry_start_server',
    explanation: '直接 sleep 重试依然报错，孤儿僵尸进程持续独占端口，属于无效重试死胡同。',
    confidence: 0.9,
    created_at: '2026-09-03T11:20:00Z',
  },
  {
    entry_id: 'hist_port_success_03',
    session_id: 'sess_port_resolved_20260903',
    turn_index: 5,
    error_signature: 'PortAlreadyInUseError address already in use <ADDR> port 8000',
    outcome_type: 'successful_resolution',
    solution_snippet: 'lsof -ti:8000 | xargs kill -9 && start_server',
    explanation: '使用 lsof 查获占用 8000 端口的残留孤儿进程并强制回收释放后顺利启动。',
    confidence: 0.98,
    created_at: '2026-09-03T11:25:00Z',
  },
  {
    entry_id: 'hist_db_lock_04',
    session_id: 'sess_pg_lock_20260908',
    turn_index: 6,
    error_signature: 'DatabaseLockTimeout deadlock detected on relation migration',
    outcome_type: 'successful_resolution',
    solution_snippet: 'CREATE INDEX CONCURRENTLY idx_users_email ON users(email);',
    explanation: '生产大表建索引引发长独占锁，改用 CONCURRENTLY 模式实现零锁并发建索引。',
    confidence: 0.95,
    created_at: '2026-09-08T15:40:00Z',
  },
  {
    entry_id: 'hist_conn_refuse_05',
    session_id: 'sess_docker_ready_20260912',
    turn_index: 3,
    error_signature: 'ConnectionRefusedError connect: connection refused redis:6379',
    outcome_type: 'successful_resolution',
    solution_snippet: "docker inspect -f '{{.State.Health.Status}}' redis_container && wait-for-it localhost:6379",
    explanation: '容器启动阶段健康探测尚未就绪，等待探测返回 healthy 后再建立业务连接。',
    confidence: 0.92,
    created_at: '2026-09-12T09:10:00Z',
  },
];

export const FALLBACK_SAMPLE_RESULT: FailureRetrievalResultDTO = {
  query_fingerprint: {
    error_type: 'PortAlreadyInUseError',
    tool_name: 'run_command',
    normalized_pattern: 'listen EADDRINUSE: address already in use :::8000',
    exit_code: 1,
    context_tags: ['network', 'port', 'process'],
  },
  total_matched: 2,
  successful_resolutions: [FALLBACK_RESOLUTIONS_CATALOG[2]],
  cautionary_failures: [FALLBACK_RESOLUTIONS_CATALOG[1]],
  suggested_action: '历史会话 [sess_port_resolved_20260903] 曾成功解决同类错误: lsof -ti:8000 | xargs kill -9 && start_server',
};

export const FALLBACK_CONFIG: FailureTriggerConfigDTO = {
  enabled: true,
  auto_trigger_on_error: true,
  max_matches: 3,
  min_similarity_threshold: 0.6,
  include_cautionary_failures: true,
};
