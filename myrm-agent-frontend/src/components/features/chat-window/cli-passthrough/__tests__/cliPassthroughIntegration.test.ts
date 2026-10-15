import { describe, it, expect, beforeEach } from 'vitest';
import {
  parseCliPassThroughInput,
  auditCliCommand,
  formatCliOutputForContext,
} from '../cliPassthroughEngine';
import { useCliPassthroughStore } from '../useCliPassthroughStore';

describe('cliPassthroughIntegration', () => {
  beforeEach(() => {
    useCliPassthroughStore.getState().resetStore();
  });

  it('completes end-to-end lifecycle for visible_to_context command (!cmd)', async () => {
    const rawInput = '! npm run test:unit';

    // 1. Parsing
    const parsed = parseCliPassThroughInput(rawInput);
    expect(parsed.isCliCommand).toBe(true);
    expect(parsed.mode).toBe('visible_to_context');
    expect(parsed.command).toBe('npm run test:unit');

    // 2. Audit
    const audit = auditCliCommand(parsed.command ?? '');
    expect(audit.allowed).toBe(true);

    // 3. Execution
    const customExecutor = async (cmd: string) => ({
      output: `Executed: ${cmd}\n32 tests passed`,
      exitCode: 0,
    });

    const record = await useCliPassthroughStore
      .getState()
      .executeCommand(rawInput, customExecutor);

    expect(record).toBeDefined();
    expect(record?.status).toBe('success');
    expect(record?.mode).toBe('visible_to_context');

    if (!record || record.exitCode === null) {
      throw new Error('Expected record to be defined with valid exitCode');
    }

    // 4. Formatting for upstream context injection
    const contextPayload = formatCliOutputForContext(
      record.command,
      record.output,
      record.exitCode,
    );

    expect(contextPayload).toContain('[USER_CMD_EXEC]');
    expect(contextPayload).toContain('$ npm run test:unit');
    expect(contextPayload).toContain('STATUS: SUCCESS');
    expect(contextPayload).toContain('32 tests passed');
    expect(contextPayload).toContain('[/USER_CMD_EXEC]');
  });

  it('completes end-to-end lifecycle for user_inspection_only command (!!cmd)', async () => {
    const rawInput = '!! git diff --stat';

    // 1. Parsing
    const parsed = parseCliPassThroughInput(rawInput);
    expect(parsed.isCliCommand).toBe(true);
    expect(parsed.mode).toBe('user_inspection_only');

    // 2. Execution
    const record = await useCliPassthroughStore.getState().executeCommand(rawInput);
    expect(record?.status).toBe('success');
    expect(record?.mode).toBe('user_inspection_only');

    // 3. Guarantee that user_inspection_only stays strictly in the local drawer
    const storeState = useCliPassthroughStore.getState();
    expect(storeState.isDrawerOpen).toBe(true);
    expect(storeState.activeCommand?.output).toBeDefined();
  });

  it('intercepts malicious command without triggering executor', async () => {
    const dangerousInput = '! rm -rf /';
    let executorCalled = false;
    const trackingExecutor = async () => {
      executorCalled = true;
      return { output: 'danger', exitCode: 0 };
    };

    const record = await useCliPassthroughStore
      .getState()
      .executeCommand(dangerousInput, trackingExecutor);

    expect(executorCalled).toBe(false);
    expect(record?.status).toBe('blocked_by_guard');
    expect(record?.guardReason).toContain('高危操作拦截');
  });

  it('chains multiple command runs and retains sequential history', async () => {
    await useCliPassthroughStore.getState().executeCommand('! echo 1');
    await useCliPassthroughStore.getState().executeCommand('!! echo 2');
    await useCliPassthroughStore.getState().executeCommand('! echo 3');

    const history = useCliPassthroughStore.getState().history;
    expect(history.length).toBe(3);
    expect(history[0].command).toBe('echo 3');
    expect(history[1].command).toBe('echo 2');
    expect(history[2].command).toBe('echo 1');
  });
});
