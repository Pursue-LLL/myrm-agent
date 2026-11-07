import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentEditAvatarField } from '../AgentEditAvatarField';
import { AGENT_ICON_REGISTRY } from '../agent-icons';

const toastError = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/shared/useToast', () => ({ toast: { error: toastError } }));

const ICON_IDS = Object.keys(AGENT_ICON_REGISTRY);
const flush = () => act(async () => {});

interface FetchResponse {
  ok: boolean;
  json: () => Promise<{ data: { avatar_url: string } }>;
}

const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<FetchResponse>>();

function renderField(props: Partial<React.ComponentProps<typeof AgentEditAvatarField>> = {}) {
  const onAvatarChange = vi.fn();
  const view = render(<AgentEditAvatarField name="Bot" avatarUrl="" onAvatarChange={onAvatarChange} {...props} />);
  const fileInput = view.container.querySelector('input[type="file"]') as HTMLInputElement;
  const pick = (name = 'a.png') =>
    fireEvent.change(fileInput, { target: { files: [new File(['x'], name, { type: 'image/png' })] } });
  return { ...view, onAvatarChange, fileInput, pick };
}

beforeEach(() => {
  toastError.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  URL.createObjectURL = vi.fn(() => 'blob:preview');
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AgentEditAvatarField', () => {
  it('shows the initial of the name, falling back to a placeholder name', () => {
    const { rerender, onAvatarChange } = renderField({ name: 'Bot' });
    expect(screen.getByText('B')).toBeInTheDocument();
    rerender(<AgentEditAvatarField name="" onAvatarChange={onAvatarChange} />);
    expect(screen.getByText('N')).toBeInTheDocument();
  });

  it('offers every built-in icon and highlights the selected one', () => {
    const { container, onAvatarChange } = renderField({ avatarUrl: `icon:${ICON_IDS[1]}` });
    const icons = [...container.querySelectorAll('div.flex-wrap > button')];
    expect(icons).toHaveLength(ICON_IDS.length);
    expect(icons[1]).toHaveClass('ring-2');
    expect(icons[0]).not.toHaveClass('ring-2');

    fireEvent.click(icons[2]);
    expect(onAvatarChange).toHaveBeenCalledWith(`icon:${ICON_IDS[2]}`);
  });

  it('opens the file picker from the avatar button', () => {
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
    renderField();
    fireEvent.click(screen.getByRole('button', { name: 'avatar.hint' }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it('ignores an empty file selection', () => {
    const { fileInput, onAvatarChange } = renderField({ agentId: 'a1' });
    fireEvent.change(fileInput, { target: { files: [] } });
    expect(onAvatarChange).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps only the local preview for an unsaved agent', async () => {
    const { pick, onAvatarChange } = renderField({ agentId: null });
    pick();
    await flush();
    expect(onAvatarChange).toHaveBeenCalledTimes(1);
    expect(onAvatarChange).toHaveBeenCalledWith('blob:preview');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('previews immediately, uploads for a saved agent and applies the stored URL', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ data: { avatar_url: 'https://cdn/x.png' } }) });
    const { pick, onAvatarChange, fileInput } = renderField({ agentId: 'a1' });
    pick('face.png');
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/user-agents\/a1\/avatar$/);
    expect(init.method).toBe('POST');
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
    expect(onAvatarChange.mock.calls).toEqual([['blob:preview'], ['https://cdn/x.png']]);
    expect(toastError).not.toHaveBeenCalled();
    expect(fileInput.value).toBe('');
  });

  it('shows a spinner instead of the upload icon while uploading', async () => {
    let finish: (response: FetchResponse) => void = () => {};
    fetchMock.mockReturnValue(new Promise<FetchResponse>((resolve) => (finish = resolve)));
    const { pick, container } = renderField({ agentId: 'a1' });
    expect(container.querySelector('.lucide-upload')).not.toBeNull();

    pick();
    await flush();
    expect(container.querySelector('.lucide-upload')).toBeNull();
    expect(container.querySelector('svg.animate-spin')).not.toBeNull();

    finish({ ok: true, json: async () => ({ data: { avatar_url: 'https://cdn/y.png' } }) });
    await flush();
    expect(container.querySelector('.lucide-upload')).not.toBeNull();
  });

  it.each([
    [
      'a rejected response',
      () => fetchMock.mockResolvedValue({ ok: false, json: async () => ({ data: { avatar_url: '' } }) }),
    ],
    ['a network failure', () => fetchMock.mockRejectedValue(new Error('offline'))],
  ])('reports %s and keeps the preview', async (_, arrange) => {
    arrange();
    const { pick, onAvatarChange, fileInput } = renderField({ agentId: 'a1' });
    pick();
    await flush();
    expect(toastError).toHaveBeenCalledWith('avatar.error');
    expect(onAvatarChange.mock.calls).toEqual([['blob:preview']]);
    expect(fileInput.value).toBe('');
  });
});
