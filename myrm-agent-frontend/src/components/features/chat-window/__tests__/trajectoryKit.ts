/**
 * Builders for the trajectory diff tests. Imported by test files only, so it must not pull in the components.
 */
import type { SessionTrajectoryResponse, TrajectoryStep, TurnTrajectory } from '@/services/chat';

export const step = (
  toolName: string,
  toolArgs: Record<string, unknown> = {},
  overrides: Partial<TrajectoryStep> = {},
): TrajectoryStep => ({
  step_index: 0,
  tool_name: toolName,
  tool_args: toolArgs,
  tool_result_summary: null,
  is_error: false,
  duration_ms: 12,
  tokens_used: 0,
  ...overrides,
});

export const turn = (turnId: string, userPrompt: string, steps: TrajectoryStep[]): TurnTrajectory => ({
  turn_id: turnId,
  user_prompt: userPrompt,
  assistant_reply: null,
  steps: steps.map((s, index) => ({ ...s, step_index: s.step_index || index })),
  total_steps: steps.length,
  total_tokens: steps.reduce((sum, s) => sum + s.tokens_used, 0),
  created_at: null,
});

export const trajectory = (
  sessionId: string,
  title: string | null,
  turns: TurnTrajectory[],
  overrides: Partial<SessionTrajectoryResponse> = {},
): SessionTrajectoryResponse => ({
  session_id: sessionId,
  title,
  turns,
  total_turns: turns.length,
  total_tool_calls: turns.reduce((sum, t) => sum + t.steps.length, 0),
  total_tokens: turns.reduce((sum, t) => sum + t.total_tokens, 0),
  ...overrides,
});
