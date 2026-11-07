import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { AgentSessionPolicy } from '@/services/agent';
import { AgentEditBrowserSettings } from '../AgentEditBrowserSettings';
import { AgentEditResponsibilityFields } from '../AgentEditResponsibilityFields';
import { AgentEditSessionPolicy } from '../AgentEditSessionPolicy';
import { EMPTY_EXTRA_FIELDS } from '../agentEditFormModel';

beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(cleanup);

const choose = async (trigger: HTMLElement, optionPrefix: string) => {
  fireEvent.click(trigger);
  const options = await screen.findAllByRole('option');
  fireEvent.click(options.find((o) => o.textContent?.startsWith(optionPrefix)) as HTMLElement);
  await act(async () => {});
};

describe('AgentEditBrowserSettings', () => {
  const renderSettings = (value: Partial<typeof EMPTY_EXTRA_FIELDS> = {}) => {
    const onChange = vi.fn();
    render(<AgentEditBrowserSettings value={{ ...EMPTY_EXTRA_FIELDS, ...value }} onChange={onChange} />);
    return { onChange, triggers: screen.getAllByRole('combobox') };
  };

  it('shows the current choices without warnings by default', () => {
    renderSettings();
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
    for (const key of ['Extension', 'Connect', 'Remote']) {
      expect(screen.queryByText(new RegExp(`form\\.browserSource${key}(Warning|Info)`))).toBeNull();
    }
  });

  it.each([
    ['extension', 'form.browserSourceExtensionWarning', 'text-amber-600'],
    ['connect', 'form.browserSourceConnectInfo', 'text-blue-600'],
    ['remote', 'form.browserSourceRemoteWarning', 'text-amber-600'],
  ])('explains the %s browser source', (browserSource, message, tone) => {
    renderSettings({ browserSource });
    expect(screen.getByText(message)).toHaveClass(tone);
  });

  it('reports the chosen browser source, dialog policy and recording mode as separate patches', async () => {
    const { onChange, triggers } = renderSettings();
    await choose(triggers[0], 'form.browserSourceLaunch');
    await choose(triggers[1], 'form.dialogPolicyWaitForAgent');
    await choose(triggers[2], 'form.sessionRecordingAlways');
    expect(onChange.mock.calls).toEqual([
      [{ browserSource: 'launch' }],
      [{ dialogPolicy: 'wait_for_agent' }],
      [{ sessionRecording: 'always' }],
    ]);
  });

  it('lists every option with its description line', async () => {
    const { triggers } = renderSettings();
    fireEvent.click(triggers[0]);
    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(5);
    expect(options.every((o) => o.querySelector('span.text-xs.text-muted-foreground') !== null)).toBe(true);
    expect(options[1]).toHaveTextContent('form.browserSourceExtensionform.browserSourceExtensionDesc');
  });
});

describe('AgentEditSessionPolicy', () => {
  const POLICY: AgentSessionPolicy = { mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 };
  const renderPolicy = (enabled: boolean, sessionPolicy: AgentSessionPolicy = POLICY) => {
    const onChange = vi.fn();
    render(<AgentEditSessionPolicy value={{ sessionPolicyEnabled: enabled, sessionPolicy }} onChange={onChange} />);
    return onChange;
  };

  it('only shows the switch while disabled and enables it on toggle', () => {
    const onChange = renderPolicy(false);
    expect(screen.queryByRole('combobox')).toBeNull();
    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ sessionPolicyEnabled: true });
  });

  it('disables the policy from the switch', () => {
    const onChange = renderPolicy(true);
    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ sessionPolicyEnabled: false });
  });

  it('shows the reset hour for the daily mode and patches the mode and hour', async () => {
    const onChange = renderPolicy(true);
    const [modeTrigger, hourTrigger] = screen.getAllByRole('combobox');
    expect(screen.queryByRole('spinbutton')).toBeNull();

    await choose(modeTrigger, 'form.sessionPolicy.modeIdle');
    expect(onChange).toHaveBeenLastCalledWith({ sessionPolicy: { ...POLICY, mode: 'idle' } });

    await choose(hourTrigger, '07:00');
    expect(onChange).toHaveBeenLastCalledWith({ sessionPolicy: { ...POLICY, daily_reset_hour: 7 } });
  });

  it('offers all 24 UTC hours', async () => {
    renderPolicy(true);
    fireEvent.click(screen.getAllByRole('combobox')[1]);
    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(24);
    expect(options[0]).toHaveTextContent('00:00 UTC');
    expect(options[23]).toHaveTextContent('23:00 UTC');
  });

  it('edits the idle timeout within 1 to 10080 minutes', () => {
    const onChange = renderPolicy(true, { ...POLICY, mode: 'idle' });
    expect(screen.queryAllByRole('combobox')).toHaveLength(1);
    const input = screen.getByRole('spinbutton');
    expect(input).toHaveValue(120);
    expect(screen.getByText('form.sessionPolicy.idleMinutesHint')).toBeInTheDocument();

    for (const [typed, minutes] of [
      ['45', 45],
      ['0', 1],
      ['', 1],
      ['20000', 10080],
    ] as const) {
      fireEvent.change(input, { target: { value: typed } });
      expect(onChange).toHaveBeenLastCalledWith({
        sessionPolicy: { mode: 'idle', daily_reset_hour: 4, idle_minutes: minutes },
      });
    }
  });

  it('hides the mode parameters for the persistent mode', () => {
    renderPolicy(true, { ...POLICY, mode: 'persistent' });
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
    expect(screen.queryByRole('spinbutton')).toBeNull();
  });
});

describe('AgentEditResponsibilityFields', () => {
  const VALUE = { responsibilityScope: 'Owns triage', ownerLabel: 'Bob', acceptanceCriteriaText: 'one\ntwo' };

  it('renders the stored values with their length limits', () => {
    render(<AgentEditResponsibilityFields value={VALUE} onChange={vi.fn()} />);
    const scope = screen.getByDisplayValue('Owns triage');
    expect(scope).toHaveAttribute('id', 'responsibility_scope');
    expect(scope).toHaveAttribute('maxlength', '2000');
    expect(screen.getByDisplayValue('Bob')).toHaveAttribute('maxlength', '100');
    expect(screen.getByDisplayValue(/one\s*two/)).toHaveAttribute('id', 'acceptance_criteria');
  });

  it('reports each field as its own patch', () => {
    const onChange = vi.fn();
    render(<AgentEditResponsibilityFields value={VALUE} onChange={onChange} />);
    fireEvent.change(screen.getByDisplayValue('Owns triage'), { target: { value: 'Owns billing' } });
    fireEvent.change(screen.getByDisplayValue('Bob'), { target: { value: 'Alice' } });
    fireEvent.change(screen.getByDisplayValue(/one\s*two/), { target: { value: 'x\ny' } });
    expect(onChange.mock.calls).toEqual([
      [{ responsibilityScope: 'Owns billing' }],
      [{ ownerLabel: 'Alice' }],
      [{ acceptanceCriteriaText: 'x\ny' }],
    ]);
  });
});
