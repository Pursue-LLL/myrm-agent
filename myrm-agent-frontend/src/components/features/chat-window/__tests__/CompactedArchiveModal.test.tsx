/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CompactedArchiveModal } from '../CompactedArchiveModal';

function renderArchive(...contents: string[]): HTMLElement {
  return render(
    <CompactedArchiveModal
      isOpen
      isLoading={false}
      messages={contents.map((content, index) => ({ id: `m${index}`, role: 'assistant', content, created_at: null }))}
      title="Archive"
      emptyLabel="Empty"
      roleUserLabel="User"
      roleAssistantLabel="Assistant"
      onClose={() => undefined}
    />,
  ).container;
}

describe('CompactedArchiveModal math', () => {
  it('renders formulas in any notation and leaves prices as text', () => {
    const container = renderArchive('It costs $5 and $10.', 'Area \\(\\pi r^2\\) and $$e^{i\\pi}=-1$$');

    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(container.textContent).toContain('It costs $5 and $10.');
  });

  it('does not turn commands that link or load a resource into links or images', () => {
    const container = renderArchive('$\\href{https://example.com}{x}$ $\\includegraphics{https://example.com/a.png}$');

    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(container.querySelectorAll('a, img')).toHaveLength(0);
  });
});
