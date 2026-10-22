export type FusenCategory =
  | 'blocker'
  | 'ready_for_review'
  | 'cache_hint'
  | 'in_progress'
  | 'custom';

export type NoteStatus = 'active' | 'resolved' | 'expired';

export interface FusenNoteItem {
  noteId: string;
  sessionId: string;
  authorAgentId: string;
  category: FusenCategory;
  tag: string;
  content: string;
  metadata?: Record<string, string>;
  status: NoteStatus;
  resolutionNote?: string | null;
  ttlSeconds?: number | null;
  createdAt: number;
  updatedAt: number;
}

export interface FusenBlockerSummaryItem {
  isBlocked: boolean;
  blockerCount: number;
  blockers: FusenNoteItem[];
  activeTags: string[];
}

export interface LightweightFusenBoardCardProps {
  sessionId?: string;
  initialNotes?: FusenNoteItem[];
  onDismiss?: () => void;
  onNoteResolved?: (noteId: string) => void;
  onNotePosted?: (note: FusenNoteItem) => void;
}

export const INITIAL_FUSEN_NOTES: FusenNoteItem[] = [
  {
    noteId: 'fusen-blk-01',
    sessionId: 'sess-default',
    authorAgentId: 'worker-db-optimizer',
    category: 'blocker',
    tag: 'blocked_by: migration_lock',
    content: 'Waiting for SQLite WAL lock release before schema migration.',
    metadata: { severity: 'high', target_table: 'messages' },
    status: 'active',
    createdAt: Date.now() - 1000 * 60 * 3,
    updatedAt: Date.now() - 1000 * 60 * 3,
  },
  {
    noteId: 'fusen-rev-02',
    sessionId: 'sess-default',
    authorAgentId: 'worker-auth-scaffold',
    category: 'ready_for_review',
    tag: 'ready_for_review: diff_jwt_service',
    content: 'JWT refresh token rotation completed in src/auth/jwt.py. Ready for peer audit.',
    metadata: { lines_changed: '38' },
    status: 'active',
    createdAt: Date.now() - 1000 * 60 * 8,
    updatedAt: Date.now() - 1000 * 60 * 8,
  },
  {
    noteId: 'fusen-cch-03',
    sessionId: 'sess-default',
    authorAgentId: 'worker-frontend-builder',
    category: 'cache_hint',
    tag: 'cache_hit: turborepo_artifacts',
    content: 'Turborepo cache hit for tailwind bundle; skipping re-compile.',
    metadata: { time_saved: '4.2s' },
    status: 'active',
    createdAt: Date.now() - 1000 * 60 * 15,
    updatedAt: Date.now() - 1000 * 60 * 15,
  },
];
