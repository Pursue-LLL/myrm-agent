/**
 * TypeScript types and defaults for Visual Multi-Agent Kanban Orchestrator and Card Lifecycle Dispatcher (Item 76).
 */

export type KanbanLane = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done' | 'blocked';

export type CardPriority = 'low' | 'medium' | 'high' | 'critical';

export interface CardArtifact {
  artifact_id: string;
  name: string;
  artifact_type: string;
  file_path?: string;
  content_preview?: string;
  mounted_at: number;
}

export interface KanbanCard {
  card_id: string;
  board_id: string;
  title: string;
  description: string;
  lane: KanbanLane;
  priority: CardPriority;
  assigned_agent: string;
  depends_on: string[];
  blocked_by: string[];
  sandbox_subdir: string;
  artifacts: CardArtifact[];
  created_at: number;
  updated_at: number;
  completed_at?: number;
}

export interface KanbanBoardState {
  board_id: string;
  session_id: string;
  title: string;
  cards: Record<string, KanbanCard>;
  created_at: number;
  updated_at: number;
}

export interface CreateCardInput {
  title: string;
  description: string;
  assigned_agent: string;
  depends_on: string[];
  priority: CardPriority;
}

export interface LaneDefinition {
  id: KanbanLane;
  label: string;
  color: string;
  bgLight: string;
}

export const KANBAN_LANES: LaneDefinition[] = [
  { id: 'backlog', label: 'Backlog', color: 'text-zinc-500', bgLight: 'bg-zinc-500/10 border-zinc-500/20' },
  { id: 'todo', label: 'Ready (To-Do)', color: 'text-sky-500', bgLight: 'bg-sky-500/10 border-sky-500/20' },
  { id: 'in_progress', label: 'In Progress', color: 'text-blue-500', bgLight: 'bg-blue-500/10 border-blue-500/20' },
  { id: 'review', label: 'In Review', color: 'text-purple-500', bgLight: 'bg-purple-500/10 border-purple-500/20' },
  { id: 'blocked', label: 'Blocked (Waiting DAG)', color: 'text-amber-500', bgLight: 'bg-amber-500/10 border-amber-500/20' },
  { id: 'done', label: 'Completed (Done)', color: 'text-emerald-500', bgLight: 'bg-emerald-500/10 border-emerald-500/20' },
];

export const DEFAULT_BOARD_STATE: KanbanBoardState = {
  board_id: 'board-demo-default',
  session_id: 'chat-demo',
  title: 'Multi-Agent Production Kanban',
  cards: {
    'card-spec-1': {
      card_id: 'card-spec-1',
      board_id: 'board-demo-default',
      title: 'API Spec & Contract Definition',
      description: 'Define OpenAPI models and Pydantic schemas for multi-agent dispatch.',
      lane: 'done',
      priority: 'high',
      assigned_agent: '@architect',
      depends_on: [],
      blocked_by: [],
      sandbox_subdir: 'tasks/card-spec-1',
      artifacts: [
        {
          artifact_id: 'art-spec-1',
          name: 'openapi_schema.json',
          artifact_type: 'file',
          file_path: 'tasks/card-spec-1/openapi_schema.json',
          content_preview: '{"openapi": "3.1.0", "info": {"title": "Kanban API"}}',
          mounted_at: Date.now() - 36000,
        },
      ],
      created_at: Date.now() - 40000,
      updated_at: Date.now() - 36000,
      completed_at: Date.now() - 36000,
    },
    'card-backend-2': {
      card_id: 'card-backend-2',
      board_id: 'board-demo-default',
      title: 'Service & DAG Engine Implementation',
      description: 'Implement KanbanTaskDagEngine and auto-unblock cascade logic.',
      lane: 'in_progress',
      priority: 'critical',
      assigned_agent: '@backend-dev',
      depends_on: ['card-spec-1'],
      blocked_by: [],
      sandbox_subdir: 'tasks/card-backend-2',
      artifacts: [],
      created_at: Date.now() - 35000,
      updated_at: Date.now() - 20000,
    },
    'card-frontend-3': {
      card_id: 'card-frontend-3',
      board_id: 'board-demo-default',
      title: 'Swimlane Kanban UI Component',
      description: 'Build responsive 6-swimlane view with dependency pills and drawer.',
      lane: 'todo',
      priority: 'high',
      assigned_agent: '@frontend-dev',
      depends_on: ['card-spec-1'],
      blocked_by: [],
      sandbox_subdir: 'tasks/card-frontend-3',
      artifacts: [],
      created_at: Date.now() - 30000,
      updated_at: Date.now() - 15000,
    },
    'card-test-4': {
      card_id: 'card-test-4',
      board_id: 'board-demo-default',
      title: 'Integration Test Suite & Quality Gate',
      description: 'End-to-end multi-agent orchestration and auto-unblock verification.',
      lane: 'blocked',
      priority: 'medium',
      assigned_agent: '@tester',
      depends_on: ['card-backend-2', 'card-frontend-3'],
      blocked_by: ['card-backend-2'],
      sandbox_subdir: 'tasks/card-test-4',
      artifacts: [],
      created_at: Date.now() - 25000,
      updated_at: Date.now() - 25000,
    },
  },
  created_at: Date.now() - 50000,
  updated_at: Date.now() - 15000,
};
