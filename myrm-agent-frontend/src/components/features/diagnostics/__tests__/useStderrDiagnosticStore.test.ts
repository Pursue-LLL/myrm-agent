import { describe, it, expect, beforeEach } from 'vitest';
import { useStderrDiagnosticStore } from '../useStderrDiagnosticStore';

describe('useStderrDiagnosticStore', () => {
  beforeEach(() => {
    useStderrDiagnosticStore.getState().resetDiagnosticState();
  });

  it('initializes with empty buffer and null active diagnostic', () => {
    const state = useStderrDiagnosticStore.getState();
    expect(state.rawBuffer).toBe('');
    expect(state.activeDiagnostic).toBeNull();
    expect(state.isFixing).toBe(false);
  });

  it('ingests stderr chunks boundedly', () => {
    useStderrDiagnosticStore.getState().ingestStderrChunk('line 1\n');
    useStderrDiagnosticStore.getState().ingestStderrChunk('line 2\n');
    expect(useStderrDiagnosticStore.getState().rawBuffer).toBe('line 1\nline 2\n');
  });

  it('classifies process exit and populates active diagnostic', () => {
    useStderrDiagnosticStore.getState().ingestStderrChunk("ModuleNotFoundError: No module named 'fastapi'\n");
    const result = useStderrDiagnosticStore.getState().classifyProcessExit(1);

    const state = useStderrDiagnosticStore.getState();
    expect(state.activeDiagnostic).toBeDefined();
    expect(state.activeDiagnostic?.category).toBe('missing_dependency');
    expect(result.fixGuides.length).toBeGreaterThan(0);
  });

  it('executes fix action and sets success feedback message', async () => {
    useStderrDiagnosticStore.getState().ingestStderrChunk("ModuleNotFoundError: No module named 'uvicorn'\n");
    useStderrDiagnosticStore.getState().classifyProcessExit(1);

    await useStderrDiagnosticStore.getState().executeFixAction('fix_install_uvicorn');

    const state = useStderrDiagnosticStore.getState();
    expect(state.isFixing).toBe(false);
    expect(state.fixSuccessMessage).toContain('uvicorn');
  });

  it('dismisses active diagnostic', () => {
    useStderrDiagnosticStore.getState().ingestStderrChunk('fatal error\n');
    useStderrDiagnosticStore.getState().classifyProcessExit(1);

    useStderrDiagnosticStore.getState().dismissDiagnostic();
    expect(useStderrDiagnosticStore.getState().activeDiagnostic).toBeNull();
  });
});
