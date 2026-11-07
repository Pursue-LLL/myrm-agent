import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SecurityChipListEditor } from '../SecurityChipListEditor';
import type { ListEditorBinding } from '../useSecurityListEditors';

function renderEditor(
  overrides: Partial<React.ComponentProps<typeof SecurityChipListEditor>> = {},
  binding: Partial<ListEditorBinding> = {},
) {
  const handlers = {
    onValueChange: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
  };
  const view = render(
    <SecurityChipListEditor
      icon={<span data-testid="card-icon" />}
      title="Allowed paths"
      description="Where the agent may read"
      tone="primary"
      placeholder="/data"
      addLabel="Add path"
      emptyText="Nothing yet"
      items={[]}
      value=""
      {...handlers}
      {...binding}
      {...overrides}
    />,
  );
  return { ...view, ...handlers };
}

const chipOf = (text: string) => screen.getByText(text).closest('div') as HTMLElement;

describe('SecurityChipListEditor', () => {
  it('renders the heading, description and empty hint', () => {
    renderEditor();
    expect(screen.getByRole('heading', { name: 'Allowed paths' })).toBeInTheDocument();
    expect(screen.getByTestId('card-icon')).toBeInTheDocument();
    expect(screen.getByText('Where the agent may read')).toBeInTheDocument();
    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
  });

  it('keeps the add button disabled until the input has text', () => {
    const { rerender, onAdd } = renderEditor({}, { value: '   ' });
    expect(screen.getByRole('button', { name: 'Add path' })).toBeDisabled();

    rerender(
      <SecurityChipListEditor
        icon={null}
        title="Allowed paths"
        description="d"
        tone="primary"
        placeholder="/data"
        addLabel="Add path"
        emptyText="Nothing yet"
        items={[]}
        value="/data"
        onValueChange={vi.fn()}
        onAdd={onAdd}
        onRemove={vi.fn()}
      />,
    );
    const addButton = screen.getByRole('button', { name: 'Add path' });
    expect(addButton).toBeEnabled();
    fireEvent.click(addButton);
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('reports typing and adds on Enter without submitting a form', () => {
    const { onValueChange, onAdd } = renderEditor({}, { value: '/data' });
    const input = screen.getByPlaceholderText('/data');
    fireEvent.change(input, { target: { value: '/data/x' } });
    expect(onValueChange).toHaveBeenCalledWith('/data/x');

    const notPrevented = fireEvent.keyDown(input, { key: 'Enter' });
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);

    fireEvent.keyDown(input, { key: 'a' });
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('renders one chip per item and removes by index, including repeated labels', () => {
    const { onRemove } = renderEditor({}, { items: ['/a', '/b', '/a'] });
    expect(screen.queryByText('Nothing yet')).toBeNull();
    expect(screen.getAllByText('/a')).toHaveLength(2);

    const removers = [...document.querySelectorAll('div.rounded-full > button')];
    expect(removers).toHaveLength(3);
    fireEvent.click(removers[2]);
    expect(onRemove).toHaveBeenCalledWith(2);
  });

  it('shows the error instead of the empty hint', () => {
    renderEditor({}, { error: 'Invalid domain' });
    const error = screen.getByText('Invalid domain');
    expect(error).toHaveClass('text-destructive-text');
    expect(screen.queryByText('Nothing yet')).toBeNull();
  });

  it('keeps showing the error next to existing chips', () => {
    renderEditor({}, { items: ['x.com'], error: 'Duplicate' });
    expect(screen.getByText('Duplicate')).toBeInTheDocument();
    expect(screen.getByText('x.com')).toBeInTheDocument();
  });

  it('colors danger chips with the readable destructive text token', () => {
    renderEditor({ tone: 'danger' }, { items: ['evil.com'] });
    const chip = chipOf('evil.com');
    expect(chip).toHaveClass('bg-destructive/10', 'border-destructive/30');
    expect(screen.getByText('evil.com')).toHaveClass('text-destructive-text');
    const remove = chip.querySelector('button') as HTMLElement;
    expect(remove).toHaveClass('text-destructive-text/60', 'hover:text-destructive-text');
    expect(document.querySelector('.text-destructive')).toBeNull();
  });

  it('colors primary and success chips with their own tones', () => {
    const { rerender } = renderEditor({ tone: 'primary' }, { items: ['/a'] });
    expect(screen.getByText('/a')).toHaveClass('text-primary');
    expect(chipOf('/a')).toHaveClass('bg-primary/10', 'border-primary/30');

    rerender(
      <SecurityChipListEditor
        icon={null}
        title="t"
        description="d"
        tone="success"
        placeholder="p"
        addLabel="a"
        emptyText="e"
        items={['ok.com']}
        value=""
        onValueChange={vi.fn()}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(chipOf('ok.com')).toHaveClass('bg-emerald-500/10', 'border-emerald-500/30');
    expect(screen.getByText('ok.com')).toHaveClass('text-emerald-700');
  });

  it('marks the card as a scroll target only when an id is given', () => {
    const { container, rerender } = renderEditor({ scrollTargetId: 'allowed-roots-section' });
    const card = container.firstElementChild as HTMLElement;
    expect(card).toHaveAttribute('id', 'allowed-roots-section');
    expect(card).toHaveClass('transition-all');

    rerender(
      <SecurityChipListEditor
        icon={null}
        title="t"
        description="d"
        tone="primary"
        placeholder="p"
        addLabel="a"
        emptyText="e"
        items={[]}
        value=""
        onValueChange={vi.fn()}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    const plain = container.firstElementChild as HTMLElement;
    expect(plain).not.toHaveAttribute('id');
    expect(plain).not.toHaveClass('transition-all');
  });

  it('applies the optional input and layout modifiers', () => {
    const { container } = renderEditor({ monospaceInput: true, stackOnMobile: true });
    expect(screen.getByPlaceholderText('/data')).toHaveClass('font-mono');
    expect(container.querySelector('.sm\\:flex-row')).not.toBeNull();
  });

  it('renders the leading chip icon and extra children', () => {
    renderEditor({ chipIcon: <i data-testid="chip-icon" />, children: <p>extra block</p> }, { items: ['a', 'b'] });
    expect(screen.getAllByTestId('chip-icon')).toHaveLength(2);
    expect(screen.getByText('extra block')).toBeInTheDocument();
  });
});
