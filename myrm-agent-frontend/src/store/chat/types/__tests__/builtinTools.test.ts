import { describe, expect, it } from 'vitest';

import {
  getBuiltinToolDisplayLabel,
  resolveToolSnapshotDisplayName,
} from '../builtinTools';

describe('builtinTools display helpers', () => {
  it('returns localized cron label from builtin_tool_id', () => {
    expect(
      resolveToolSnapshotDisplayName(
        { name: 'cron_manage_tool', builtin_tool_id: 'cron' },
        'zh',
      ),
    ).toBe('定时任务');
    expect(getBuiltinToolDisplayLabel('cron', 'en')).toBe('Scheduled Tasks');
  });

  it('falls back to internal tool name when no product id', () => {
    expect(
      resolveToolSnapshotDisplayName({ name: 'bash_code_execute_tool' }, 'en'),
    ).toBe('bash_code_execute_tool');
  });

  it('prefers known tool override over builtin_tool_id', () => {
    expect(
      resolveToolSnapshotDisplayName(
        { name: 'conversation_search', builtin_tool_id: 'memory' },
        'en',
        'Conversation search',
      ),
    ).toBe('Conversation search');
  });
});
