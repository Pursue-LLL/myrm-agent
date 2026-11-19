import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImageResultCard } from '../ImageResultCard';

describe('ImageResultCard', () => {
  it('loads a media-library reference through the media endpoint and leaves plain URLs alone', () => {
    render(
      <ImageResultCard
        images={[{ url: 'media://media_abc' }, { url: 'https://cdn.example/fox.png' }]}
        referenceImageUrls={['media://media_ref', '/uploads/ref.png']}
      />,
    );

    const sources = screen.getAllByRole('img').map((image) => image.getAttribute('src'));
    expect(sources[0]).toMatch(/\/api\/v1\/media\/media_abc\/file$/);
    expect(sources[1]).toBe('https://cdn.example/fox.png');
    expect(sources[2]).toMatch(/\/api\/v1\/media\/media_ref\/file$/);
    expect(sources[3]).toBe('/uploads/ref.png');
  });

  it('hands the image it shows, with its reference untouched, to the edit action', () => {
    const onEditRequest = vi.fn();
    render(
      <ImageResultCard images={[{ url: 'media://media_abc', mimeType: 'image/png' }]} onEditRequest={onEditRequest} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'editThisImage' }));

    expect(onEditRequest).toHaveBeenCalledExactlyOnceWith({ url: 'media://media_abc', mimeType: 'image/png' });
  });

  it('shows no edit action without a handler, and never a regenerate action', () => {
    render(<ImageResultCard images={[{ url: 'media://media_abc' }]} />);

    expect(screen.queryByRole('button', { name: 'editThisImage' })).toBeNull();
    expect(screen.queryByTitle('regenerate')).toBeNull();
  });

  it('downloads from the resolved address', async () => {
    const fetchMock = vi.fn(async (_url: string) => ({ blob: async () => new Blob(['x']) }) as unknown as Response);
    vi.stubGlobal('fetch', fetchMock);
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    render(<ImageResultCard images={[{ url: 'media://media_abc' }]} />);

    fireEvent.click(screen.getByTitle('download'));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/media\/media_abc\/file$/);
    vi.unstubAllGlobals();
  });

  it('shows the load error instead of a broken image when an image fails to load', () => {
    render(<ImageResultCard images={[{ url: 'media://media_gone' }]} />);

    fireEvent.error(screen.getByRole('img'));

    expect(screen.getByText('loadError')).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('renders nothing for no images', () => {
    const { container } = render(<ImageResultCard images={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
