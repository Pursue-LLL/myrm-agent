/** @vitest-environment jsdom */
import type { MouseEvent, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>();
  return {
    ...actual,
    ReactFlow: ({
      nodes,
      onNodeClick,
      children,
    }: {
      nodes: Array<{ id: string }>;
      onNodeClick: (event: MouseEvent, node: { id: string }) => void;
      children?: ReactNode;
    }) => (
      <div>
        {nodes.map((node) => (
          <button key={node.id} type="button" data-testid={`node-${node.id}`} onClick={(e) => onNodeClick(e, node)}>
            {node.id}
          </button>
        ))}
        {children}
      </div>
    ),
    Controls: () => null,
    Background: () => null,
    MiniMap: () => null,
  };
});
vi.mock('@xyflow/react/dist/style.css', () => ({}));
vi.mock('html2canvas', () => ({ default: vi.fn() }));
vi.mock('../../MermaidPreview', () => ({ default: () => <div>mermaid-fallback</div> }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

import ArchitecturePreview from '../ArchitecturePreview';
import type { ArtifactVersion } from '@/store/chat/types';

const CURRENT = JSON.stringify({
  title: 'Order Platform',
  nodes: [
    { id: 'gateway', label: 'API Gateway' },
    { id: 'order', label: 'Order Service' },
    { id: 'billing', label: 'Billing Service' },
    { id: 'orphan', label: 'Orphan Service' },
  ],
  edges: [
    { id: 'e1', source: 'gateway', target: 'order' },
    { id: 'e2', source: 'order', target: 'billing' },
  ],
});

const PREVIOUS = JSON.stringify({
  title: 'Order Platform',
  nodes: [
    { id: 'gateway', label: 'API Gateway' },
    { id: 'legacy', label: 'Legacy Service' },
  ],
  edges: [{ id: 'e0', source: 'gateway', target: 'legacy' }],
});

const versions = [{ content: CURRENT }, { content: PREVIOUS }] as unknown as ArtifactVersion[];

describe('ArchitecturePreview localized copy', () => {
  it('renders the toolbar placeholder and the translated schema error', () => {
    const { unmount } = render(<ArchitecturePreview content={CURRENT} />);
    expect(screen.getByPlaceholderText('searchNodes')).toBeInTheDocument();
    expect(screen.queryByText('liveView')).not.toBeInTheDocument();
    unmount();

    render(<ArchitecturePreview content="not a diagram" />);
    expect(screen.getByText('invalidSchema')).toBeInTheDocument();
  });

  it('falls back to the translated default title when the diagram has none', () => {
    render(<ArchitecturePreview content={JSON.stringify({ nodes: [{ id: 'a', label: 'A' }], edges: [] })} />);

    expect(screen.getByText('defaultTitle')).toBeInTheDocument();
  });

  it('labels the diff toggle and the diff summary badges', async () => {
    render(<ArchitecturePreview content={CURRENT} versions={versions} />);

    await userEvent.click(screen.getByText('diffView'));

    expect(screen.getByText('liveView')).toBeInTheDocument();
    expect(screen.getByText('evolutionDiffActive')).toBeInTheDocument();
    expect(screen.getByText('diffNodesAdded:3')).toBeInTheDocument();
    expect(screen.getByText('diffNodesDeleted:1')).toBeInTheDocument();
    expect(screen.getByText('diffEdgesAdded:2')).toBeInTheDocument();
    expect(screen.getByText('diffEdgesDeleted:1')).toBeInTheDocument();
  });

  it('shows the tracing hint for one selected node and the clear action', async () => {
    render(<ArchitecturePreview content={CURRENT} />);

    await userEvent.click(screen.getByTestId('node-gateway'));

    expect(screen.getByText(/tracingFor/)).toBeInTheDocument();
    expect(screen.getByText('clickToTrace')).toBeInTheDocument();

    await userEvent.click(screen.getByText('clear'));
    expect(screen.queryByText('clickToTrace')).not.toBeInTheDocument();
  });

  it('shows the shortest-path hop count for a reachable target', async () => {
    render(<ArchitecturePreview content={CURRENT} />);

    await userEvent.click(screen.getByTestId('node-gateway'));
    await userEvent.click(screen.getByTestId('node-billing'));

    expect(screen.getByText(/shortestPath/)).toBeInTheDocument();
    expect(screen.getByText('hops:2')).toBeInTheDocument();
    expect(screen.queryByText('noDirectedPath')).not.toBeInTheDocument();
  });

  it('shows the no-path label when the target is unreachable', async () => {
    render(<ArchitecturePreview content={CURRENT} />);

    await userEvent.click(screen.getByTestId('node-gateway'));
    await userEvent.click(screen.getByTestId('node-orphan'));

    expect(screen.getByText('noDirectedPath')).toBeInTheDocument();
    expect(screen.queryByText(/^hops:/)).not.toBeInTheDocument();
  });

  it('switches the copy button label after copying the JSON', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ArchitecturePreview content={CURRENT} />);

    await userEvent.click(screen.getByText('JSON'));

    expect(await screen.findByText('copied')).toBeInTheDocument();
  });
});
