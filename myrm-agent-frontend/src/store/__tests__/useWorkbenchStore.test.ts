import { beforeEach, describe, expect, it } from 'vitest';
import { useWorkbenchStore } from '../useWorkbenchStore';

describe('useWorkbenchStore', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      isOpen: false,
      placement: 'right',
      width: 480,
      height: 320,
      activeTab: 'files',
      terminalLogs: [],
    });
  });

  it('initializes with default state values', () => {
    const state = useWorkbenchStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.placement).toBe('right');
    expect(state.width).toBe(480);
    expect(state.height).toBe(320);
    expect(state.activeTab).toBe('files');
    expect(state.terminalLogs).toHaveLength(0);
  });

  it('toggles and sets open state', () => {
    const { toggleOpen, setOpen } = useWorkbenchStore.getState();

    toggleOpen();
    expect(useWorkbenchStore.getState().isOpen).toBe(true);

    toggleOpen();
    expect(useWorkbenchStore.getState().isOpen).toBe(false);

    setOpen(true);
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
  });

  it('clamps width and height within safe boundaries', () => {
    const { setWidth, setHeight } = useWorkbenchStore.getState();

    setWidth(100); // below min 320
    expect(useWorkbenchStore.getState().width).toBe(320);

    setWidth(2000); // above max 960
    expect(useWorkbenchStore.getState().width).toBe(960);

    setHeight(50); // below min 200
    expect(useWorkbenchStore.getState().height).toBe(200);

    setHeight(1000); // above max 640
    expect(useWorkbenchStore.getState().height).toBe(640);
  });

  it('updates placement and active tab', () => {
    const { setPlacement, setActiveTab } = useWorkbenchStore.getState();

    setPlacement('bottom');
    expect(useWorkbenchStore.getState().placement).toBe('bottom');

    setActiveTab('terminal');
    expect(useWorkbenchStore.getState().activeTab).toBe('terminal');
  });

  it('records terminal logs and clears them', () => {
    const { addTerminalLog, clearTerminalLogs } = useWorkbenchStore.getState();

    addTerminalLog({
      command: 'npm run test',
      output: 'PASS src/app.test.ts',
      exitCode: 0,
    });

    const logs = useWorkbenchStore.getState().terminalLogs;
    expect(logs).toHaveLength(1);
    expect(logs[0].command).toBe('npm run test');
    expect(logs[0].output).toBe('PASS src/app.test.ts');
    expect(logs[0].exitCode).toBe(0);

    clearTerminalLogs();
    expect(useWorkbenchStore.getState().terminalLogs).toHaveLength(0);
  });

  it('drops the terminal history when the workspace session resets', () => {
    const { addTerminalLog, resetWorkspaceSession } = useWorkbenchStore.getState();
    addTerminalLog({ command: 'ls', output: 'app.py', exitCode: 0 });

    resetWorkspaceSession();

    expect(useWorkbenchStore.getState().terminalLogs).toHaveLength(0);
  });

  it('advances the session epoch on every reset so replies for a previous session can be told apart', () => {
    const { resetWorkspaceSession } = useWorkbenchStore.getState();
    const before = useWorkbenchStore.getState().sessionEpoch;

    resetWorkspaceSession();
    resetWorkspaceSession();

    expect(useWorkbenchStore.getState().sessionEpoch).toBe(before + 2);
  });
});
