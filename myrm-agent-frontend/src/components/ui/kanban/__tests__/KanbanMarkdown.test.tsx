import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import KanbanMarkdown from '../KanbanMarkdown';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/ui/markdown-render-tools/CodeBlock', () => ({
  default: ({ language, value }: { language: string; value: string }) => (
    <pre data-testid="code-block" data-language={language}>
      {value}
    </pre>
  ),
}));

vi.mock('@/lib/utils/reactUtils', () => ({
  getChildrenAsText: (children: any) => {
    if (typeof children === 'string') return children;
    if (Array.isArray(children)) return children.join('');
    return String(children ?? '');
  },
}));

describe('KanbanMarkdown', () => {
  it('renders plain text as paragraph', () => {
    render(<KanbanMarkdown>Hello world</KanbanMarkdown>);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('renders bold text', () => {
    render(<KanbanMarkdown>**bold text**</KanbanMarkdown>);
    expect(screen.getByText('bold text').tagName).toBe('STRONG');
  });

  it('renders links with target=_blank and rel=noopener', () => {
    render(<KanbanMarkdown>[click](https://example.com)</KanbanMarkdown>);
    const link = screen.getByText('click');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('href', 'https://example.com');
  });

  it('rejects javascript: protocol links', () => {
    render(<KanbanMarkdown>[evil](javascript:alert(1))</KanbanMarkdown>);
    const el = screen.getByText('evil');
    expect(el.tagName).toBe('SPAN');
    expect(el).not.toHaveAttribute('href');
  });

  it('renders code blocks with CodeBlock component', () => {
    render(<KanbanMarkdown>{'```python\nprint("hi")\n```'}</KanbanMarkdown>);
    const codeBlock = screen.getByTestId('code-block');
    expect(codeBlock).toHaveAttribute('data-language', 'python');
    expect(codeBlock).toHaveTextContent('print("hi")');
  });

  it('renders inline code', () => {
    render(<KanbanMarkdown>use `npm install`</KanbanMarkdown>);
    const code = screen.getByText('npm install');
    expect(code.tagName).toBe('CODE');
  });

  it('renders GFM tables', () => {
    const md = '| A | B |\n|---|---|\n| 1 | 2 |';
    const { container } = render(<KanbanMarkdown>{md}</KanbanMarkdown>);
    expect(container.querySelector('table')).toBeInTheDocument();
    expect(container.querySelector('td')).toHaveTextContent('1');
  });

  it('renders GFM task lists', () => {
    const md = '- [ ] todo\n- [x] done';
    const { container } = render(<KanbanMarkdown>{md}</KanbanMarkdown>);
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBe(2);
  });

  it('does not parse $ as math (no remarkMath)', () => {
    render(<KanbanMarkdown>Price is $100</KanbanMarkdown>);
    expect(screen.getByText(/Price is \$100/)).toBeInTheDocument();
  });

  it('applies maxLines clamp class', () => {
    const { container } = render(<KanbanMarkdown maxLines={4}>Long content</KanbanMarkdown>);
    const wrapper = container.querySelector('.line-clamp-4');
    expect(wrapper).toBeInTheDocument();
  });

  it('shows "showMore" button when maxLines is set', () => {
    render(<KanbanMarkdown maxLines={2}>Content</KanbanMarkdown>);
    expect(screen.getByText('showMore')).toBeInTheDocument();
  });

  it('expands on showMore click and shows showLess', () => {
    render(<KanbanMarkdown maxLines={2}>Content</KanbanMarkdown>);
    fireEvent.click(screen.getByText('showMore'));
    expect(screen.queryByText('showMore')).not.toBeInTheDocument();
    expect(screen.getByText('showLess')).toBeInTheDocument();
  });

  it('collapses back on showLess click', () => {
    render(<KanbanMarkdown maxLines={2}>Content</KanbanMarkdown>);
    fireEvent.click(screen.getByText('showMore'));
    fireEvent.click(screen.getByText('showLess'));
    expect(screen.getByText('showMore')).toBeInTheDocument();
  });

  it('does not show expand buttons without maxLines', () => {
    render(<KanbanMarkdown>Content</KanbanMarkdown>);
    expect(screen.queryByText('showMore')).not.toBeInTheDocument();
    expect(screen.queryByText('showLess')).not.toBeInTheDocument();
  });

  it('strips disallowed HTML tags via unwrapDisallowed (XSS safe)', () => {
    const { container } = render(<KanbanMarkdown>{'<script>alert(1)</script>safe text'}</KanbanMarkdown>);
    expect(container.querySelector('script')).not.toBeInTheDocument();
    expect(container.textContent).toContain('safe text');
  });

  it('applies custom className', () => {
    const { container } = render(<KanbanMarkdown className="text-red-500">Hi</KanbanMarkdown>);
    expect(container.querySelector('.text-red-500')).toBeInTheDocument();
  });

  it('renders unordered lists', () => {
    const md = '- item 1\n- item 2\n- item 3';
    const { container } = render(<KanbanMarkdown>{md}</KanbanMarkdown>);
    expect(container.querySelector('ul')).toBeInTheDocument();
    expect(container.querySelectorAll('li').length).toBe(3);
  });
});
