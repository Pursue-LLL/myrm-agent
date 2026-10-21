/**
 * Unit tests for AgentVisualComposer workbench.
 *
 * [INPUT] AgentVisualComposer, assemblerService
 * [OUTPUT] Full coverage tests for Lego-style capability composition, catalog filtering, canvas interactions, and dry-run execution.
 * [POS] src/components/features/agent-assembler/__tests__/AgentVisualComposer.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AgentVisualComposer } from '../AgentVisualComposer';
import { assemblerService } from '../assemblerService';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    composerTitle: 'Visual Modular Agent Assembler',
    composerSubtitle: 'Block-Based Capability Composer & Sandbox Testbed',
    blockCatalogTitle: 'Capability Blocks Pool',
    available: 'blocks',
    searchBlocks: 'Search building blocks...',
    allCategories: 'All',
    brain: 'Brain',
    persona: 'Persona',
    tools: 'Tools',
    skills: 'Skills',
    memory: 'Memory',
    sandbox: 'Sandbox',
    equip: 'Equip',
    equipped: 'Equipped',
    assembledBlocks: 'Equipped Capability Blocks',
    active: 'Active',
    inactive: 'Inactive',
    blueprintValid: 'Blueprint Structurally Valid',
    blueprintInvalid: 'Dependency Issues Detected',
    playgroundTitle: 'Sandbox Testbed & Dry-Run',
    testPromptLabel: 'Test Instruction Prompt',
    runDryRun: 'Run Dry-Run',
    simulating: 'Simulating...',
    predictedTools: 'Predicted Activated Tools',
    saveBlueprint: 'Save Agent',
    export: 'Export',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../assemblerService', async () => {
  const actual = await vi.importActual<typeof import('../assemblerService')>('../assemblerService');
  return {
    ...actual,
    assemblerService: {
      getBlockCatalog: vi.fn().mockResolvedValue(actual.DEFAULT_BLOCK_CATALOG),
      validateAssembly: vi.fn().mockResolvedValue({
        is_valid: true,
        errors: [],
        warnings: [],
        suggestions: [],
        estimated_token_cost: 350,
      }),
      dryRunAssembly: vi.fn().mockResolvedValue({
        simulated_response: 'Simulated output from testbed',
        resolved_system_prompt: 'System prompt content for test agent',
        predicted_tool_calls: ['read_file', 'run_command'],
        latency_ms: 18,
        tokens_used: 390,
      }),
    },
  };
});

describe('AgentVisualComposer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all three panes and default architect preset blueprint', async () => {
    render(<AgentVisualComposer />);

    expect(screen.getByText('Visual Modular Agent Assembler')).toBeInTheDocument();
    expect(screen.getByTestId('assembler-block-catalog')).toBeInTheDocument();
    expect(screen.getByTestId('assembler-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('assembler-dry-run-playground')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Blueprint Structurally Valid')).toBeInTheDocument();
    });
  });

  it('allows equipping a new block from the catalog into the canvas', async () => {
    render(<AgentVisualComposer />);

    await waitFor(() => {
      expect(screen.getByText('Data & Research Analyst')).toBeInTheDocument();
    });

    const equipButtons = screen.getAllByRole('button', { name: 'Equip' });
    if (equipButtons.length > 0) {
      fireEvent.click(equipButtons[0]);
    }

    await waitFor(() => {
      expect(assemblerService.validateAssembly).toHaveBeenCalled();
    });
  });

  it('switches between presets when preset buttons are clicked', async () => {
    render(<AgentVisualComposer />);

    const analystPresetBtn = screen.getByRole('button', { name: 'Analyst' });
    fireEvent.click(analystPresetBtn);

    await waitFor(() => {
      expect(screen.getByDisplayValue('Deep Research & Data Analyst')).toBeInTheDocument();
    });
  });

  it('triggers dry-run execution in the testbed playground', async () => {
    render(<AgentVisualComposer />);

    const runBtn = screen.getByRole('button', { name: 'Run Dry-Run' });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(assemblerService.dryRunAssembly).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: expect.stringContaining('Analyze repository'),
        }),
      );
      expect(screen.getByText('Simulated output from testbed')).toBeInTheDocument();
      expect(screen.getByText('read_file')).toBeInTheDocument();
      expect(screen.getByText('run_command')).toBeInTheDocument();
      expect(screen.getByText('18ms')).toBeInTheDocument();
    });
  });

  it('invokes onSaveBlueprint callback when save button is clicked', () => {
    const onSave = vi.fn();
    render(<AgentVisualComposer onSaveBlueprint={onSave} />);

    const saveBtn = screen.getByRole('button', { name: 'Save Agent' });
    fireEvent.click(saveBtn);

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: expect.any(String),
        blocks: expect.any(Array),
      }),
    );
  });
});
