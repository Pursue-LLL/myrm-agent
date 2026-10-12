/** @vitest-environment jsdom */
import { act, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LifeStatusCapsule } from '../LifeStatusCapsule';

const stableT = (key: string, params?: { count?: number }) =>
  params?.count === undefined ? key : `${key}|count=${params.count}`;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('framer-motion', () => ({
  motion: {
    output: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <output className={className}>{children}</output>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheckCircle: () => <span data-testid="icon-check" />,
  IconX: () => <span data-testid="icon-x" />,
}));

function emitIdleStatus(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent('idle-status', { detail: { session_id: 's1', ...detail } }));
  });
}

describe('LifeStatusCapsule', () => {
  it('translates a working task by task_name and status', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'working', task_name: 'cognitive_consolidation' });
    expect(screen.getByText('idleStatus.cognitive_consolidation.working|count=0')).toBeTruthy();
  });

  it('interpolates the merged count for subsumption notifications', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'notification', task_name: 'cognitive_subsumption', data: { count: 3 } });
    expect(screen.getByText('idleStatus.cognitive_subsumption.notification|count=3')).toBeTruthy();
    expect(screen.getByTestId('icon-check')).toBeTruthy();
  });

  it('shows the generic error label with the failure icon', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'error', task_name: 'context_compaction' });
    expect(screen.getByText('idleStatus.error')).toBeTruthy();
    expect(screen.getByTestId('icon-x')).toBeTruthy();
  });

  it('falls back to the processing label for unknown tasks and ignores raw message text', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'working', task_name: 'future_task', message: 'raw backend text' });
    expect(screen.getByText('processingCapsule')).toBeTruthy();
    expect(screen.queryByText('raw backend text')).toBeNull();
  });

  it('treats prototype property names as unknown tasks', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'working', task_name: 'constructor' });
    expect(screen.getByText('processingCapsule')).toBeTruthy();
  });

  it('hides when the session goes idle', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ status: 'working', task_name: 'context_compaction' });
    emitIdleStatus({ status: 'idle' });
    expect(screen.queryByText('idleStatus.context_compaction.working|count=0')).toBeNull();
  });

  it('ignores events of other sessions', () => {
    render(<LifeStatusCapsule currentSessionId="s1" />);
    emitIdleStatus({ session_id: 'other', status: 'working', task_name: 'context_compaction' });
    expect(screen.queryByText('idleStatus.context_compaction.working|count=0')).toBeNull();
  });
});
