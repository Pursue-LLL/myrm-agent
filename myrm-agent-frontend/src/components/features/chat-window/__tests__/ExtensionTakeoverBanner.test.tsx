import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import ExtensionTakeoverBanner from '../ExtensionTakeoverBanner';

const kit = vi.hoisted(() => ({
  complete: vi.fn<() => Promise<void>>(),
  skip: vi.fn<() => Promise<void>>(),
}));

vi.mock('@/hooks/approval/useBrowserTakeoverActions', () => ({
  useBrowserTakeoverActions: () => ({ handleTakeoverComplete: kit.complete, handleTakeoverSkip: kit.skip }),
}));

type Request = Parameters<ReturnType<typeof useBrowserTakeoverStore.getState>['requestTakeover']>[0];

function requestTakeover(request: Partial<Request> = {}): void {
  act(() =>
    useBrowserTakeoverStore
      .getState()
      .requestTakeover({ reason: 'Solve the captcha', ui_mode: 'extension', ...request }),
  );
}

beforeEach(() => {
  useBrowserTakeoverStore.getState().dismiss();
  kit.complete.mockResolvedValue();
  kit.skip.mockResolvedValue();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('ExtensionTakeoverBanner visibility', () => {
  it('shows nothing while no takeover is requested', () => {
    const { container } = render(<ExtensionTakeoverBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing for a takeover that the managed desktop handles', () => {
    requestTakeover({ ui_mode: 'managed' });
    const { container } = render(<ExtensionTakeoverBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing once the request is no longer pending', () => {
    requestTakeover();
    const { container } = render(<ExtensionTakeoverBanner />);

    act(() => useBrowserTakeoverStore.setState({ pending: false }));

    expect(container).toBeEmptyDOMElement();
  });

  it('appears when the agent asks for the local browser, and goes when the takeover ends', () => {
    const { container } = render(<ExtensionTakeoverBanner />);

    requestTakeover();
    expect(screen.getByRole('alert')).toBeInTheDocument();

    act(() => useBrowserTakeoverStore.getState().completeTakeover());
    expect(container).toBeEmptyDOMElement();
  });
});

describe('ExtensionTakeoverBanner waiting for the user', () => {
  it('asks the user to finish in their own browser, and says why', () => {
    requestTakeover({ reason: 'Solve the captcha' });
    render(<ExtensionTakeoverBanner />);

    expect(screen.getByText('takeoverExtensionTitle')).toBeInTheDocument();
    expect(screen.getByText('takeoverExtensionHint')).toBeInTheDocument();
    expect(screen.getByText('Solve the captcha')).toBeInTheDocument();
    expect(screen.queryByText('takeoverCaptchaAuto')).toBeNull();
  });

  it('skips the takeover from the Skip button', () => {
    requestTakeover();
    render(<ExtensionTakeoverBanner />);

    fireEvent.click(screen.getByRole('button', { name: 'takeoverSkip' }));

    expect(kit.skip).toHaveBeenCalledTimes(1);
    expect(kit.complete).not.toHaveBeenCalled();
  });

  it('completes the takeover from the Done button', () => {
    requestTakeover();
    render(<ExtensionTakeoverBanner />);

    fireEvent.click(screen.getByRole('button', { name: 'takeoverDone' }));

    expect(kit.complete).toHaveBeenCalledTimes(1);
    expect(kit.skip).not.toHaveBeenCalled();
  });

  it('shows the page address, with the full address as its title', () => {
    requestTakeover({ url: 'https://example.com/login' });
    render(<ExtensionTakeoverBanner />);

    expect(screen.getByText('https://example.com/login')).toHaveAttribute('title', 'https://example.com/login');
  });

  it('shows neither reason nor address when there are none', () => {
    requestTakeover({ reason: '', url: '' });
    const { container } = render(<ExtensionTakeoverBanner />);

    expect(container.querySelectorAll('p')).toHaveLength(2);
  });

  it('shows the page screenshot when there is one, and a globe icon when there is not', () => {
    requestTakeover({ screenshot_base64: 'AAAA' });
    const { container, rerender } = render(<ExtensionTakeoverBanner />);

    expect(container.querySelector('img')).toHaveAttribute('src', 'data:image/jpeg;base64,AAAA');
    expect(container.querySelector('.lucide-globe')).toBeNull();

    requestTakeover({ screenshot_base64: null });
    rerender(<ExtensionTakeoverBanner />);

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.lucide-globe')).not.toBeNull();
  });
});

describe('ExtensionTakeoverBanner when completion is detected automatically', () => {
  it('says it is watching, and offers no buttons', () => {
    requestTakeover({ auto_detect_completion: true });
    render(<ExtensionTakeoverBanner />);

    expect(screen.getAllByText('takeoverCaptchaAuto')).toHaveLength(2);
    expect(screen.getByText('takeoverCaptchaAutoHint')).toBeInTheDocument();
    expect(screen.queryByText('takeoverExtensionTitle')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('ExtensionTakeoverBanner live assist', () => {
  const writeText = vi.fn<(text: string) => Promise<void>>();

  beforeEach(() => {
    writeText.mockResolvedValue();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  });

  it('offers no live assist links when there is no address for one', () => {
    requestTakeover();
    render(<ExtensionTakeoverBanner />);

    expect(screen.queryByText('takeoverOpenLiveAssist')).toBeNull();
    expect(screen.queryByText('takeoverCopyLiveAssist')).toBeNull();
  });

  it('opens the live assist page in a new tab without handing it the opener', () => {
    requestTakeover({ live_assist_url: 'https://assist.example/session/1' });
    render(<ExtensionTakeoverBanner />);

    const link = screen.getByRole('link', { name: 'takeoverOpenLiveAssist' });
    expect(link).toHaveAttribute('href', 'https://assist.example/session/1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('copies the live assist address', () => {
    requestTakeover({ live_assist_url: 'https://assist.example/session/1' });
    render(<ExtensionTakeoverBanner />);

    fireEvent.click(screen.getByRole('button', { name: 'takeoverCopyLiveAssist' }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith('https://assist.example/session/1');
  });

  it('does nothing, without failing, when the browser has no clipboard', () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    requestTakeover({ live_assist_url: 'https://assist.example/session/1' });
    render(<ExtensionTakeoverBanner />);

    fireEvent.click(screen.getByRole('button', { name: 'takeoverCopyLiveAssist' }));

    expect(writeText).not.toHaveBeenCalled();
  });
});
