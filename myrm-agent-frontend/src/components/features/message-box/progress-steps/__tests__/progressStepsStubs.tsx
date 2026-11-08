/**
 * Stand-ins for the components a step module renders as children, so each module's own suite
 * only sees what the module hands them. A `vi.mock` factory loads them lazily with `import()`.
 */
import type { ArchiveRestoreAction, ArchiveRestoreResultPayload, ProgressItem } from '@/store/chat/types';
import type { StepNodeContext } from '../ProgressStepNode';
import type { TreeNode } from '../treeUtils';

interface RendererProps {
  items?: { text?: string; url?: string }[] | string;
  messageId?: string;
  stepIndex?: number;
  toolName?: string;
  isCurrentStep?: boolean;
  handleLinkClick?: (target: string) => void;
}

/** Marks which renderer got which props; a link renderer also gets a button that clicks its first item. */
const rendererStub = (name: string) =>
  function RendererStub({ items, messageId, stepIndex, toolName, isCurrentStep, handleLinkClick }: RendererProps) {
    const first = Array.isArray(items) ? items[0] : undefined;
    const target = first?.text ?? first?.url;
    return (
      <div
        data-testid={name}
        data-message-id={messageId}
        data-step-index={stepIndex}
        data-tool-name={toolName}
        data-current={isCurrentStep === undefined ? undefined : String(isCurrentStep)}
      >
        {handleLinkClick && target !== undefined && (
          <button type="button" onClick={() => handleLinkClick(target)}>
            {`open ${name}`}
          </button>
        )}
      </div>
    );
  };

function LiveTerminalStub(props: Record<string, string | number | boolean | undefined>) {
  return <div data-testid="LiveTerminal" data-props={JSON.stringify(props)} />;
}

export const rendererModule = {
  CodeRenderer: rendererStub('CodeRenderer'),
  FilePathRenderer: rendererStub('FilePathRenderer'),
  LiveTerminal: LiveTerminalStub,
  QueryItemsRenderer: rendererStub('QueryItemsRenderer'),
  SearchToolCard: rendererStub('SearchToolCard'),
  SkillSelectRenderer: rendererStub('SkillSelectRenderer'),
  SourcesRenderer: rendererStub('SourcesRenderer'),
  TextItemsRenderer: rendererStub('TextItemsRenderer'),
  TextRenderer: ({ text }: { text: string }) => <div data-testid="TextRenderer" data-text={text} />,
  URLItemsRenderer: rendererStub('URLItemsRenderer'),
};

function StepItemsViewStub({
  step,
  messageId,
  index,
  isCurrent,
}: {
  step: ProgressItem;
  messageId: string;
  index: number;
  isCurrent: boolean;
}) {
  return (
    <div
      data-testid="items-view"
      data-step-key={step.step_key}
      data-message-id={messageId}
      data-index={index}
      data-current={String(isCurrent)}
    />
  );
}

function StepTerminalStub({ step }: { step: ProgressItem }) {
  return <div data-testid="terminal" data-step-key={step.step_key} />;
}

export const outputModule = { StepItemsView: StepItemsViewStub, StepTerminal: StepTerminalStub };

export const archiveActionModule = {
  ArchiveRestoreStepAction: ({ actions }: { actions: ArchiveRestoreAction[] }) => (
    <div data-testid="archive-restore-action" data-count={actions.length} />
  ),
};

export const archiveResultModule = {
  ArchiveRestoreResultChip: ({ result }: { result: ArchiveRestoreResultPayload }) => (
    <div data-testid="archive-restore-result" data-restore-arg={result.restore_arg} />
  ),
};

export const rollbackModule = {
  SkillManageBatchRollbackAction: ({ batchId }: { batchId: string }) => (
    <div data-testid="skill-rollback" data-batch-id={batchId} />
  ),
};

export const nodesModule = {
  StepNodes: ({ nodes, depth, ctx }: { nodes: TreeNode[]; depth: number; ctx: StepNodeContext }) => (
    <ul data-testid="nodes" data-depth={depth} data-message-id={ctx.messageId}>
      {nodes.map((node) => (
        <li key={node.originalIndex}>{node.step.step_key}</li>
      ))}
    </ul>
  ),
};
