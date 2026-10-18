/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LARGE_FILE_THRESHOLD } from '@/lib/constants/artifact';
import { SvgPreview } from '../MediaPreview';

const SMALL_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4" /></svg>';
const CIRCLE_NODE = '<circle cx="5" cy="5" r="4" />';

/** 构造超过 LARGE_FILE_THRESHOLD 的 SVG（阈值判定只看字符长度） */
function buildLargeSvg(extra = ''): string {
  const count = Math.ceil(LARGE_FILE_THRESHOLD / CIRCLE_NODE.length) + 1;
  return `<svg xmlns="http://www.w3.org/2000/svg">${CIRCLE_NODE.repeat(count)}${extra}</svg>`;
}

describe('SvgPreview', () => {
  const createObjectURLMock = vi.fn().mockReturnValue('blob:svg-raster');
  const revokeObjectURLMock = vi.fn();

  beforeEach(() => {
    createObjectURLMock.mockClear();
    createObjectURLMock.mockReturnValue('blob:svg-raster');
    revokeObjectURLMock.mockClear();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;
  });

  it('renders a small SVG inline without creating a blob URL', () => {
    const { container } = render(<SvgPreview content={SMALL_SVG} />);

    expect(createObjectURLMock).not.toHaveBeenCalled();
    expect(container.querySelector('svg')).not.toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('sanitizes embedded scripts out of inline SVG content', () => {
    const svgWithScript = `<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>${CIRCLE_NODE}</svg>`;
    const { container } = render(<SvgPreview content={svgWithScript} />);

    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('circle')).not.toBeNull();
  });

  it('rasterizes a large SVG through a blob-backed image', () => {
    const { container } = render(<SvgPreview content={buildLargeSvg()} />);

    expect(createObjectURLMock).toHaveBeenCalledTimes(1);
    expect(createObjectURLMock.mock.calls[0][0]).toBeInstanceOf(Blob);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('blob:svg-raster');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('treats content exactly at the threshold as large', () => {
    render(<SvgPreview content={'a'.repeat(LARGE_FILE_THRESHOLD)} />);

    expect(createObjectURLMock).toHaveBeenCalledTimes(1);
  });

  it('revokes the blob URL on unmount', () => {
    const { unmount } = render(<SvgPreview content={buildLargeSvg()} />);

    unmount();

    expect(revokeObjectURLMock).toHaveBeenCalledExactlyOnceWith('blob:svg-raster');
  });

  it('revokes the previous blob URL and creates a new one when content changes', () => {
    const { rerender } = render(<SvgPreview content={buildLargeSvg()} />);
    createObjectURLMock.mockReturnValue('blob:svg-raster-v2');

    rerender(<SvgPreview content={buildLargeSvg('<!-- v2 -->')} />);

    expect(revokeObjectURLMock).toHaveBeenCalledExactlyOnceWith('blob:svg-raster');
    expect(createObjectURLMock).toHaveBeenCalledTimes(2);
    expect(createObjectURLMock.mock.results[1].value).toBe('blob:svg-raster-v2');
  });

  it('shows a load error when the raster image fails', () => {
    const { container } = render(<SvgPreview content={buildLargeSvg()} />);
    const img = container.querySelector('img');

    expect(img).not.toBeNull();
    fireEvent.error(img as Element);

    expect(screen.getByText('inlinePreview.loadError')).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
  });
});
