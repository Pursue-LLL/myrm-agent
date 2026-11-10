/**
 * Shared stubs and fixtures of the edit dialog tests.
 *
 * The dialog's heavy children are replaced by probes: each one shows the part of the dialog's draft it receives and
 * hands the dialog's setters to the test. The dialog's own module is deliberately not imported here, because the
 * test files load this kit from inside their `vi.mock` factories.
 */
import { screen } from '@testing-library/react';
import type { ComponentProps, ReactElement } from 'react';
import { vi } from 'vitest';

import type { CuratorRunResponse } from '@/services/skill';
import type { MCPServiceConfig } from '@/store/config/types';
import type { Skill } from '@/store/skill/types';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';

import type { ActionSpaceAccuracyRadarProps } from '../ActionSpaceAccuracyRadar';
import type { ConfigCardType } from '../AgentConfigCards';
import type AgentConfigEditDialog from '../AgentConfigEditDialog';
import type { BuiltinToolsPanelProps } from '../BuiltinToolsPanel';
import type { InstructionPanelProps } from '../InstructionPanel';
import type { SkillsSectionPanelProps } from '../SkillsSectionPanel';
import type { SubagentsPanelProps } from '../SubagentsPanel';

export type DialogProps = ComponentProps<typeof AgentConfigEditDialog>;

interface McpToolSelectorProps {
  serverName: string;
  selectedTools: string[] | undefined;
  onSelectionChange: (serverName: string, tools: string[] | undefined) => void;
  isServerEnabled: boolean;
}

export const kit = {
  builtin: undefined as BuiltinToolsPanelProps | undefined,
  skills: undefined as SkillsSectionPanelProps | undefined,
  subagents: undefined as SubagentsPanelProps | undefined,
  instruction: undefined as InstructionPanelProps | undefined,
  radar: undefined as ActionSpaceAccuracyRadarProps | undefined,
  entitlements: { canUseCron: true, canUseVnc: true, isLoading: false },
  local: false,
  sandbox: false,
  toast: vi.fn<(options: { title?: string; description?: string; variant?: string }) => void>(),
  runCuratorSweep: vi.fn<() => Promise<CuratorRunResponse>>(),
  riskHeld: vi.fn<(response: Response) => Promise<Error | null>>(),
  onSave: vi.fn<(data: object) => void>(),
  onOpenChange: vi.fn<(open: boolean) => void>(),
};

/** Back to a clean slate; call after `vi.resetAllMocks()` in `beforeEach`. */
export function resetKit(): void {
  kit.builtin = undefined;
  kit.skills = undefined;
  kit.subagents = undefined;
  kit.instruction = undefined;
  kit.radar = undefined;
  kit.entitlements = { canUseCron: true, canUseVnc: true, isLoading: false };
  kit.local = false;
  kit.sandbox = false;
  kit.riskHeld.mockResolvedValue(null);
}

/* ─── module mock factories ─── */

export const nextDynamicMock = () => ({
  default: (loader: () => Promise<unknown>) => {
    const source = String(loader);
    if (source.includes('MCPToolSelector')) {
      return (props: McpToolSelectorProps) => (
        <div
          data-testid={`tools-${props.serverName}`}
          data-selected={JSON.stringify(props.selectedTools ?? null)}
          data-server-enabled={String(props.isServerEnabled)}
        >
          <button type="button" onClick={() => props.onSelectionChange(props.serverName, ['search'])}>
            {`choose-${props.serverName}`}
          </button>
          <button type="button" onClick={() => props.onSelectionChange(props.serverName, undefined)}>
            {`reset-${props.serverName}`}
          </button>
        </div>
      );
    }
    if (source.includes('SkillsSection')) {
      return () => <div data-testid="skills-settings" />;
    }
    if (source.includes('MCPSection')) {
      return () => <div data-testid="mcp-settings" />;
    }
    return () => null;
  },
});

export const entitlementsMock = () => ({ useFeatureEntitlements: () => kit.entitlements });

export const deployModeMock = (original: object) => ({
  ...original,
  isLocalMode: () => kit.local,
  isSandbox: () => kit.sandbox,
});

export const radarMock = () => ({
  ActionSpaceAccuracyRadar: (props: ActionSpaceAccuracyRadarProps): ReactElement => {
    kit.radar = props;
    return (
      <div
        data-testid="radar"
        data-evaluating={String(props.isEvaluating)}
        data-level={props.accuracyLevel}
        data-high={String(props.isNoiseHigh)}
        data-critical={String(props.isNoiseCritical)}
        data-stale={props.staleCoreSkillCount}
        data-pruning={String(props.isSmartPruning)}
        data-turn1-catalog={String(props.showTurn1Catalog)}
        data-preview={JSON.stringify(props.catalogPreview ?? null)}
      >
        <button type="button" onClick={props.onSmartPrune}>
          prune
        </button>
      </div>
    );
  },
});

export const skillsPanelMock = () => ({
  SkillsSectionPanel: (props: SkillsSectionPanelProps): ReactElement => {
    kit.skills = props;
    return (
      <div
        data-testid="skills-panel"
        data-ids={props.localSkillIds.join(',')}
        data-configs={JSON.stringify(props.localSkillConfigs)}
        data-agent={props.agentId ?? ''}
        data-noise={JSON.stringify(props.noiseData)}
        data-stale={props.staleCoreSkills.join(',')}
      />
    );
  },
});

export const builtinToolsPanelMock = () => ({
  BuiltinToolsPanel: (props: BuiltinToolsPanelProps): ReactElement => {
    kit.builtin = props;
    return (
      <div
        data-testid="builtin-panel"
        data-tools={props.localBuiltinTools.join(',')}
        data-domains={props.localAutoRestoreDomains.join(',')}
        data-source={props.localBrowserSource ?? ''}
        data-policy={props.localDialogPolicy ?? ''}
        data-recording={props.localSessionRecording ?? ''}
      />
    );
  },
});

export const subagentsPanelMock = () => ({
  SubagentsPanel: (props: SubagentsPanelProps): ReactElement => {
    kit.subagents = props;
    return (
      <div
        data-testid="subagents-panel"
        data-team={JSON.stringify(props.localEphemeralSubagents)}
        data-errors={JSON.stringify(props.displayNameErrors)}
      />
    );
  },
});

export const instructionPanelMock = () => ({
  InstructionPanel: (props: InstructionPanelProps): ReactElement => {
    kit.instruction = props;
    return (
      <div
        data-testid="instruction-panel"
        data-prompt={props.localPrompt}
        data-global={String(props.localUseGlobalInstruction)}
        data-generating={String(props.isGeneratingAi)}
        data-history={props.history.map((entry) => entry.version).join(',')}
      >
        <button type="button" onClick={() => props.setLocalPrompt('Answer in French')}>
          type-prompt
        </button>
        <button type="button" onClick={() => props.setLocalUseGlobalInstruction(false)}>
          drop-global
        </button>
      </div>
    );
  },
});

/* ─── fixtures ─── */

export function skill(id: string, overrides: Partial<Skill> = {}): Skill {
  return {
    id,
    type: 'prebuilt',
    name: id,
    description: '',
    storage_path: '',
    version: '1.0.0',
    category: null,
    icon_url: null,
    tags: [],
    requires: { bins: [], env: [], config: [] },
    available: true,
    unavailable_reason: null,
    trust: 'builtin',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: true,
    evolution_locked: false,
    has_upstream_update: false,
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mcp(name: string): MCPServiceConfig {
  return { name, type: 'sse', description: `${name} server`, enabled: true };
}

/** The props the panel gives the dialog, as a fresh set of objects on every call. */
export function dialogProps(type: ConfigCardType, overrides: Partial<DialogProps> = {}): DialogProps {
  return {
    open: true,
    onOpenChange: kit.onOpenChange,
    type,
    enabledSkills: [skill('s1'), skill('s2')],
    enabledMcps: [mcp('docs'), mcp('web')],
    selectedSkillIds: ['s1'],
    skillConfigs: {},
    selectedMcpNames: ['docs'],
    systemPrompt: 'Be brief',
    useGlobalInstruction: true,
    enabledBuiltinTools: ['web_search'],
    onSave: kit.onSave,
    ...overrides,
  };
}

/* ─── probes ─── */

export const builtin = (): BuiltinToolsPanelProps => {
  expectDefined(kit.builtin, 'built-in tools panel');
  return kit.builtin;
};
export const skillsPanel = (): SkillsSectionPanelProps => {
  expectDefined(kit.skills, 'skills panel');
  return kit.skills;
};
export const subagentsPanel = (): SubagentsPanelProps => {
  expectDefined(kit.subagents, 'subagents panel');
  return kit.subagents;
};
export const instructionPanel = (): InstructionPanelProps => {
  expectDefined(kit.instruction, 'instruction panel');
  return kit.instruction;
};

export const confirm = () => screen.getByRole('button', { name: 'confirm' });

export function settingsSheet(contentTestId: string): HTMLElement {
  const sheet = screen.getByTestId(contentTestId).closest<HTMLElement>('[role="dialog"]');
  expectNonNull(sheet, 'settings sheet');
  return sheet;
}
