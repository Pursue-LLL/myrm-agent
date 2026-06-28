import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockDismiss = vi.fn();
let mockHookReturn = {
  visible: false,
  release: null as null | { version: string; body: string; publishedAt: string; htmlUrl: string },
  loading: false,
  dismiss: mockDismiss,
};

vi.mock('@/hooks/useWhatsNew', () => ({
  useWhatsNew: () => mockHookReturn,
}));

vi.mock('@/components/primitives/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="dialog-content" className={className}>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dialog-header">{children}</div>
  ),
  DialogTitle: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <h2 data-testid="dialog-title" className={className}>{children}</h2>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p data-testid="dialog-description">{children}</p>
  ),
  DialogFooter: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="dialog-footer" className={className}>{children}</div>
  ),
}));

const { WhatsNewModal } = await import(
  '@/components/features/app-shell/whats-new-modal'
);

describe('WhatsNewModal', () => {
  beforeEach(() => {
    mockDismiss.mockClear();
    mockHookReturn = {
      visible: false,
      release: null,
      loading: false,
      dismiss: mockDismiss,
    };
  });

  it('renders nothing when not visible', () => {
    const { container } = render(<WhatsNewModal />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when loading', () => {
    mockHookReturn = { ...mockHookReturn, loading: true };
    const { container } = render(<WhatsNewModal />);
    expect(container.innerHTML).toBe('');
  });

  it('renders dialog with release info when visible', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '1.2.0',
        body: '## Features\n- Added dark mode\n- Improved **performance**',
        publishedAt: '2025-01-01T00:00:00Z',
        htmlUrl: 'https://github.com/test/releases/tag/v1.2.0',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);

    expect(screen.getByTestId('dialog')).toBeInTheDocument();
    expect(screen.getByTestId('dialog-title')).toBeInTheDocument();
    expect(screen.getByText('gotIt')).toBeInTheDocument();
    expect(screen.getByText('viewOnGitHub')).toBeInTheDocument();
  });

  it('calls dismiss when "Got It" button is clicked', async () => {
    const user = userEvent.setup();
    mockHookReturn = {
      visible: true,
      release: {
        version: '1.0.0',
        body: 'Some release notes',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    await user.click(screen.getByText('gotIt'));
    expect(mockDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders markdown with inline elements', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '2.0.0',
        body: [
          '## New Features',
          '- Added `dark mode` support',
          '- **Bold** and *italic* text',
          '- Visit [docs](https://example.com)',
          '',
          'A paragraph with `inline code`.',
        ].join('\n'),
        publishedAt: '',
        htmlUrl: 'https://github.com/test',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);

    expect(screen.getByText('dark mode')).toBeInTheDocument();
    expect(screen.getByText('Bold')).toBeInTheDocument();
    expect(screen.getByText('italic')).toBeInTheDocument();
    expect(screen.getByText('docs')).toBeInTheDocument();
    expect(screen.getByText('inline code')).toBeInTheDocument();
  });

  it('renders standalone image lines', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '3.0.0',
        body: '![screenshot](https://example.com/img.png)',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    const img = document.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.src).toBe('https://example.com/img.png');
    expect(img?.alt).toBe('screenshot');
  });

  it('does not render GitHub link when htmlUrl is empty', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '4.0.0',
        body: 'Notes',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    expect(screen.queryByText('viewOnGitHub')).not.toBeInTheDocument();
  });

  it('renders mixed content correctly (heading + list + paragraph + image)', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '5.0.0',
        body: [
          '## Features',
          '- Dark mode support',
          '- Performance improvements',
          '',
          '![screenshot](https://example.com/demo.gif)',
          '',
          'Thanks for updating!',
        ].join('\n'),
        publishedAt: '2025-06-01T00:00:00Z',
        htmlUrl: 'https://github.com/test',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    expect(screen.getByText('Features')).toBeInTheDocument();
    expect(screen.getByText('Dark mode support')).toBeInTheDocument();
    expect(screen.getByText('Performance improvements')).toBeInTheDocument();
    expect(screen.getByText('Thanks for updating!')).toBeInTheDocument();
    const img = document.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.src).toBe('https://example.com/demo.gif');
  });

  it('handles XSS attempts in body safely', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '6.0.0',
        body: '<script>alert("xss")</script>\n- Safe **content**',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    const scripts = document.querySelectorAll('script');
    const injected = Array.from(scripts).some(
      (s) => s.textContent?.includes('alert'),
    );
    expect(injected).toBe(false);
    expect(screen.getByText('content')).toBeInTheDocument();
  });

  it('renders empty body as empty container', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '7.0.0',
        body: '',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    expect(screen.getByTestId('dialog')).toBeInTheDocument();
  });

  it('handles img load error by hiding the element', () => {
    mockHookReturn = {
      visible: true,
      release: {
        version: '8.0.0',
        body: '![broken](https://example.com/404.png)',
        publishedAt: '',
        htmlUrl: '',
      },
      loading: false,
      dismiss: mockDismiss,
    };

    render(<WhatsNewModal />);
    const img = document.querySelector('img') as HTMLImageElement;
    expect(img).not.toBeNull();
    img.dispatchEvent(new Event('error'));
    expect(img.style.display).toBe('none');
  });
});
