import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { randomUUID } from 'crypto';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

export const TEST_BASH_EPHEMERAL = {
  test_bash: {
    system_prompt: 'You are a bash execution worker.',
    tools: ['bash_code_execute_tool'],
  },
} as const;

export const DELEGATE_SLEEP_QUERY =
  "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，wait 设为 false，让它执行 bash 命令: `sleep 120`。注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，绝对不要在文本中输出 XML 格式的工具调用！";

export async function seedSubagentChat(request: APIRequestContext): Promise<string> {
  const chatId = randomUUID();
  const saveRes = await request.post(`${apiBase}/api/v1/chats/`, {
    data: {
      chat_id: chatId,
      title: `E2E Subagent Dashboard ${Date.now()}`,
      action_mode: 'agent',
      agent_id: 'builtin-general',
      ephemeral_subagents: TEST_BASH_EPHEMERAL,
      messages: [],
    },
  });
  expect(saveRes.ok(), `seed chat failed: ${await saveRes.text()}`).toBeTruthy();
  return chatId;
}

export async function waitForRunningSubagent(
  request: APIRequestContext,
  chatId: string,
  timeoutMs = 120_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request.get(`${apiBase}/api/v1/chats/${chatId}/subagents`);
    if (res.ok()) {
      const body = (await res.json()) as { data?: Array<{ task_id?: string; status?: string }> };
      const running = (body.data ?? []).find((row) => row.status === 'running' && row.task_id);
      if (running?.task_id) {
        return running.task_id;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(`Timed out waiting for running subagent on chat ${chatId}`);
}

export async function waitForDashboardTriggerNatural(page: Page, timeoutMs = 30_000): Promise<boolean> {
  const trigger = page.getByTestId('subagent-dashboard-trigger');
  try {
    await expect(trigger).toBeVisible({ timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

/** Fallback when chat-stream SSE has not painted the dashboard yet; mirrors notifications SSE payload shape. */
export async function injectSubagentsUpdatedFromRest(
  page: Page,
  request: APIRequestContext,
  chatId: string,
): Promise<void> {
  const res = await request.get(`${apiBase}/api/v1/chats/${chatId}/subagents`);
  expect(res.ok(), `GET subagents failed: ${await res.text()}`).toBeTruthy();
  const body = (await res.json()) as { data?: Array<Record<string, unknown>> };
  const rows = body.data ?? [];
  await page.evaluate(
    ({ sessionId, tree }) => {
      window.dispatchEvent(
        new CustomEvent('subagents_updated', {
          detail: { chat_id: sessionId, tree },
        }),
      );
    },
    { sessionId: chatId, tree: rows },
  );
}
