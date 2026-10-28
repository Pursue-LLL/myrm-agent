import { describe, expect, it } from 'vitest';

import { BROWSER_SESSION_ACTIONS, resolveBrowserSession } from '../browserSession';

describe('resolveBrowserSession', () => {
  it.each(BROWSER_SESSION_ACTIONS)('recognises %s on the browser tool', (action) => {
    expect(resolveBrowserSession('browser_manage', { action, value: 'example.com' })).toEqual({
      action,
      domain: 'example.com',
    });
  });

  it('treats a missing site as "all sites"', () => {
    expect(resolveBrowserSession('browser_manage', { action: 'list_sessions' })).toEqual({
      action: 'list_sessions',
      domain: '',
    });
  });

  it('ignores other browser actions and other tools', () => {
    expect(resolveBrowserSession('browser_manage', { action: 'navigate', value: 'example.com' })).toBeNull();
    expect(resolveBrowserSession('browser_manage', {})).toBeNull();
    expect(resolveBrowserSession('bash_code_execute_tool', { action: 'save_session' })).toBeNull();
  });
});
