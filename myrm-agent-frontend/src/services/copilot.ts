import { fetchWithTimeout } from '@/lib/api';

export interface RunDigestStep {
  index: number;
  tool_name: string;
  step_key: string;
  status?: string | null;
}

export interface RunDigest {
  chat_id: string;
  phase: 'idle' | 'running' | 'waiting_approval' | 'completed' | 'error' | 'cancelled';
  step_count: number;
  current_tool: string | null;
  current_step_key: string | null;
  pending_approval_count: number;
  elapsed_seconds: number;
  headline: string;
  recent_steps: RunDigestStep[];
  updated_at: string;
}

export interface AdvisorMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tier: string;
  created_at: string;
}

export async function fetchRunDigest(chatId: string): Promise<RunDigest | null> {
  const res = await fetchWithTimeout(`/agents/chats/${chatId}/copilot/run-digest`);
  if (!res.ok) return null;
  const json = (await res.json()) as { data?: { digest?: RunDigest | null } };
  return json.data?.digest ?? null;
}

export async function askAdvisor(
  chatId: string,
  question: string,
  selectionSnippet?: string,
): Promise<{ reply: string; tier: string; message: AdvisorMessage } | null> {
  const res = await fetchWithTimeout(`/agents/chats/${chatId}/copilot/advisor/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      selection_snippet: selectionSnippet ?? null,
    }),
  });
  if (!res.ok) return null;
  const json = (await res.json()) as {
    data?: { reply: string; tier: string; message: AdvisorMessage };
  };
  if (!json.data) return null;
  return json.data;
}

export async function fetchAdvisorMessages(chatId: string): Promise<AdvisorMessage[]> {
  const res = await fetchWithTimeout(`/agents/chats/${chatId}/copilot/advisor/messages`);
  if (!res.ok) return [];
  const json = (await res.json()) as { data?: { messages?: AdvisorMessage[] } };
  return json.data?.messages ?? [];
}

export async function clearAdvisorMessages(chatId: string): Promise<void> {
  await fetchWithTimeout(`/agents/chats/${chatId}/copilot/advisor/messages`, {
    method: 'DELETE',
  });
}
