export type PipelineStage = 'specifier' | 'coder' | 'cleaner' | 'hardener' | 'qa';

export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked';

export type ViolationType = 'inverted_dependency' | 'layer_bypass' | 'circular_dependency';

export interface ArchitectureViolationItem {
  sourceModule: string;
  targetModule: string;
  violationType: ViolationType;
  ruleDescription: string;
  remediationSuggestion: string;
}

export interface StageArtifactItem {
  stage: PipelineStage;
  title: string;
  content: string;
  metadata?: Record<string, string>;
}

export interface CleanCodeTaskItem {
  taskId: string;
  sessionId: string;
  title: string;
  specPrompt: string;
  currentStage: PipelineStage;
  status: StageStatus;
  artifacts: Record<string, StageArtifactItem>;
  stageHistory: string[];
  violations: ArchitectureViolationItem[];
}

export interface CleanCodeAssemblyPipelineCardProps {
  taskId?: string;
  sessionId?: string;
  initialTask?: CleanCodeTaskItem;
  onDismiss?: () => void;
  onAdvanceComplete?: (task: CleanCodeTaskItem) => void;
}

export const PIPELINE_STAGES: { stage: PipelineStage; label: string; roleDescription: string }[] = [
  {
    stage: 'specifier',
    label: '1. Specifier',
    roleDescription: 'Defines formal interface contracts and DIP abstractions',
  },
  {
    stage: 'coder',
    label: '2. Coder',
    roleDescription: 'Implements business logic strictly against spec',
  },
  {
    stage: 'cleaner',
    label: '3. Cleaner',
    roleDescription: 'Refactors and eliminates code smells without changing logic',
  },
  {
    stage: 'hardener',
    label: '4. Hardener',
    roleDescription: 'Enforces type annotations, error guards, and docstrings',
  },
  {
    stage: 'qa',
    label: '5. QA Signoff',
    roleDescription: 'Verifies unit tests and regression boundaries',
  },
];

export const MOCK_INITIAL_TASK: CleanCodeTaskItem = {
  taskId: 'clean-task-101',
  sessionId: 'sess-default',
  title: 'Hexagonal Domain Model Assembly',
  specPrompt: 'Implement decoupled payment processing with strict DIP architecture boundaries.',
  currentStage: 'coder',
  status: 'running',
  artifacts: {
    specifier: {
      stage: 'specifier',
      title: 'Formal Interface Contracts',
      content: 'Defined PaymentProcessorProtocol and PaymentGatewayPort in Domain layer.',
      metadata: { author: 'SpecifierSubAgent' },
    },
  },
  stageHistory: ['specifier', 'coder'],
  violations: [],
};
