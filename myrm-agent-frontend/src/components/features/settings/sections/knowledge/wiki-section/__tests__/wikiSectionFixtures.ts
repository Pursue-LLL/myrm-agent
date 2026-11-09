import type { AgentListItem } from '@/services/agent';
import type {
  CompileRunStatus,
  ImportResultResponse,
  ImportUrlsResultResponse,
  ImportVideoResponse,
  ObsidianImportResultResponse,
  WikiHealthReport,
  WikiMaintainResponse,
  WikiQueryResponse,
  WikiSourceSnippet,
} from '@/services/wikiService';
import type { WikiIngestSnapshot } from '../../useWikiIngestSubscription';
import type { WikiStats } from '../types';

export const statsOf = (over: Partial<WikiStats> = {}): WikiStats => ({
  total_concepts: 12,
  total_articles: 7,
  total_raw_files: 30,
  wiki_path: '/tmp/wiki',
  vault_ready: true,
  legacy_migrated: true,
  cognitive_index_ready: true,
  cognitive_log_entries: 4,
  cognitive_hot_updated_at: '2026-01-02T03:04:05Z',
  ...over,
});

/** 每个徽标 / 提示都点亮的统计: 结构问题、资产索引、待综合、重复组（拦下编译）、最近维护。 */
export const richStats = (over: Partial<WikiStats> = {}): WikiStats =>
  statsOf({
    structural_issues: { broken_links: 2, invalid_frontmatter_types: 1, provenance_gaps: 3, scanned_concepts: 10 },
    asset_index: { indexed: 5, pending: 1, failed: 2, total_files: 8, enabled: false },
    synthesis_pending: 4,
    obsidian_launch_available: true,
    vault_git_enabled: true,
    vault_git_initialized: true,
    vault_git_last_commit: 'abc123',
    maintain_state: {
      last_run_at: '2026-02-01T00:00:00Z',
      last_mode: 'full',
      last_issues_found: 5,
      last_issues_fixed: 3,
      last_connections_discovered: 1,
      last_duration_ms: 1234,
      last_skipped_reason: null,
    },
    dedup_stats: {
      duplicate_groups_pending: 2,
      compile_jobs_prevented: 1,
      eligible_raw_count: 5,
      excluded_raw_count: 1,
      trashed_raw_count: 0,
      blocks_compile: true,
    },
    ...over,
  });

export const healthOf = (over: Partial<WikiHealthReport> = {}): WikiHealthReport => ({
  mode: 'structural',
  generated_at: '2026-01-01T00:00:00Z',
  open_actions_count: 0,
  issues_found: 0,
  issues: [],
  drift_sampled: false,
  duplicate_groups_pending: 0,
  synthesis_pending: 0,
  ...over,
});

export const driftIssue = {
  issue_type: 'drift',
  severity: 'warning',
  location: 'concepts/a.md',
  description: 'Drifted from its raw source',
  action_kind: 'navigate',
} as const;

export const maintainResultOf = (over: Partial<WikiMaintainResponse> = {}): WikiMaintainResponse => ({
  issues_found: 4,
  issues_fixed: 2,
  connections_discovered: 1,
  duration_ms: 50,
  open_actions_count: 0,
  raw_security_removed: 0,
  raw_security_removed_paths: [],
  issues: [],
  ai_unavailable: false,
  ...over,
});

export const compileRunOf = (over: Partial<CompileRunStatus> = {}): CompileRunStatus => ({
  state: 'paused',
  pause_reason: 'Provider quota exhausted',
  primary_error_kind: 'quota',
  ...over,
});

export const snapshotOf = (
  stats: Partial<WikiIngestSnapshot['stats']> = {},
  over: Partial<WikiIngestSnapshot> = {},
): WikiIngestSnapshot => ({
  stats: { pending: 0, processing: 0, completed: 3, failed: 0, ...stats },
  ...over,
});

export const busySnapshot = (over: Partial<WikiIngestSnapshot> = {}): WikiIngestSnapshot =>
  snapshotOf({ pending: 2, processing: 1, completed: 0 }, over);

export const snippetOf = (over: Partial<WikiSourceSnippet> = {}): WikiSourceSnippet => ({
  name: 'Concept A',
  path: 'concepts/a.md',
  section: 'summary',
  snippet: 'a snippet of the concept',
  level: 'L1',
  ...over,
});

export const queryResponseOf = (over: Partial<WikiQueryResponse> = {}): WikiQueryResponse => ({
  answer: 'The answer',
  related_articles: [],
  source_snippets: [],
  ...over,
});

export const agentOf = (id: string, name: string): AgentListItem => ({
  id,
  name,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

export const importResultOf = (over: Partial<ImportResultResponse> = {}): ImportResultResponse => ({
  success: true,
  files_scanned: 3,
  files_enqueued: 3,
  message: 'Imported 3 files',
  ...over,
});

export const obsidianResultOf = (over: Partial<ObsidianImportResultResponse> = {}): ObsidianImportResultResponse => ({
  success: true,
  files_scanned: 8,
  files_processed: 5,
  files_skipped: 1,
  tags_extracted: 2,
  images_copied: 1,
  message: 'Imported the vault',
  ...over,
});

export const urlImportResultOf = (enqueued: number): ImportUrlsResultResponse => ({
  success: true,
  total_urls: 2,
  processed_count: 2,
  enqueued_count: enqueued,
  skipped_conflict_count: 0,
  superseded_count: 0,
  security_blocked_count: 0,
  security_redacted_count: 0,
  error_count: 0,
  results: [],
  message: 'Imported the links',
});

export const videoImportResultOf = (over: Partial<ImportVideoResponse> = {}): ImportVideoResponse => ({
  success: true,
  url: 'https://video.example.com/watch',
  relative_path: 'raw/video.md',
  status: 'success',
  error: '',
  error_code: null,
  message: 'Imported the video',
  ...over,
});

/** 带 `webkitRelativePath` 的文件，与浏览器给出的一致：目录选择器给相对路径，单个文件选择给空串（jsdom 默认没有这个属性）。 */
export function fileOf(name: string, relativePath = '', content = `# ${name}`): File {
  const file = new File([content], name, { type: 'text/plain' });
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
}
