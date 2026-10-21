import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import MarkdownImage from '../MarkdownImage';

describe('MarkdownImage 键盘可达性', () => {
  it('图片由原生按钮包裹，点击后打开预览', () => {
    render(<MarkdownImage src="https://example.com/architecture.png" alt="Architecture" />);

    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Architecture' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('alt 为空时按钮回退到本地化的预览名称', () => {
    render(<MarkdownImage src="https://example.com/architecture.png" />);

    expect(screen.getByRole('button', { name: 'preview' })).toBeInTheDocument();
  });
});
