import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ShellToolCallApproval } from '../ShellToolCallApproval';
import { shellCall } from './approvalKit';
import { propsOf } from './approvalStubs';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock(
  '@/components/features/chat-window/approval/ShellCommandDisplay',
  async () => (await import('./approvalStubs')).shellCommandDisplayModule,
);
vi.mock(
  '@/components/approval/ApprovalScopeNoteLine',
  async () => (await import('./approvalStubs')).scopeNoteLineModule,
);

afterEach(cleanup);

const COMMAND = 'ls -la | wc';
const display = () => propsOf(screen.getByTestId('ShellCommandDisplay'));
const renderShell = (args: Record<string, unknown>, workspaceRoot?: string) =>
  render(<ShellToolCallApproval call={shellCall(args)} workspaceRoot={workspaceRoot} />);

describe('ShellToolCallApproval', () => {
  describe('the command', () => {
    it.each(['command', 'script', 'cmd', 'code'])('is read from the "%s" argument', (key) => {
      renderShell({ [key]: COMMAND });

      expect(display()).toMatchObject({ toolName: 'bash_code_execute_tool', command: COMMAND });
    });

    it('is empty when no argument carries one', () => {
      renderShell({ other: 1 });

      expect(display().command).toBe('');
    });

    it('is shown relative to the workspace root it is given', () => {
      renderShell({ command: COMMAND }, '/work/space');

      expect(display().workspaceRoot).toBe('/work/space');
    });

    it('is annotated with the scope note of the call', () => {
      renderShell({ command: COMMAND });

      expect(propsOf(screen.getByTestId('ApprovalScopeNoteLine'))).toEqual({
        toolName: 'bash_code_execute_tool',
        toolInput: { command: COMMAND },
      });
    });
  });

  describe('the span annotations', () => {
    const spans = [
      { startIndex: 0, endIndex: 2 },
      { startIndex: 9, endIndex: 11 },
    ];

    it('pass on the spans with their risks, reasons and the plain explanation', () => {
      renderShell({
        command: COMMAND,
        command_spans: spans,
        command_span_risks: ['safe', 'unknown'],
        command_span_reasons: ['safe', 'unknown_command'],
        plain_explanation: { en: 'list files', zh: '列出文件' },
      });

      expect(display()).toMatchObject({
        commandSpans: spans,
        commandSpanRisks: ['safe', 'unknown'],
        commandSpanReasons: ['safe', 'unknown_command'],
        plainExplanation: { en: 'list files', zh: '列出文件' },
      });
    });

    it('are also read from their camel-case names', () => {
      renderShell({
        command: COMMAND,
        commandSpans: spans,
        commandSpanRisks: ['safe', 'safe'],
        commandSpanReasons: ['safe', 'redirect'],
        plainExplanation: { en: 'a', zh: 'b' },
      });

      expect(display()).toMatchObject({
        commandSpans: spans,
        commandSpanRisks: ['safe', 'safe'],
        commandSpanReasons: ['safe', 'redirect'],
        plainExplanation: { en: 'a', zh: 'b' },
      });
    });

    it('prefer the snake-case name when both are given', () => {
      renderShell({ command: COMMAND, command_spans: [spans[0]], commandSpans: [spans[1]] });

      expect(display().commandSpans).toEqual([spans[0]]);
    });

    it('prefer the snake-case names of the risks, reasons and explanation as well', () => {
      renderShell({
        command: COMMAND,
        command_spans: spans,
        command_span_risks: ['safe', 'unknown'],
        commandSpanRisks: ['unknown', 'safe'],
        command_span_reasons: ['safe', 'unknown_command'],
        commandSpanReasons: ['unknown_command', 'safe'],
        plain_explanation: { en: 'snake', zh: '蛇' },
        plainExplanation: { en: 'camel', zh: '驼' },
      });

      expect(display()).toMatchObject({
        commandSpanRisks: ['safe', 'unknown'],
        commandSpanReasons: ['safe', 'unknown_command'],
        plainExplanation: { en: 'snake', zh: '蛇' },
      });
    });

    it('drop risks and reasons when no span is valid', () => {
      renderShell({
        command: COMMAND,
        command_spans: [{ startIndex: 5, endIndex: 99 }],
        command_span_risks: ['safe'],
        command_span_reasons: ['safe'],
      });

      const props = display();
      expect(props.commandSpans).toBeUndefined();
      expect(props.commandSpanRisks).toBeUndefined();
      expect(props.commandSpanReasons).toBeUndefined();
    });

    it('drop risks and reasons that do not match the spans one for one', () => {
      renderShell({
        command: COMMAND,
        command_spans: spans,
        command_span_risks: ['safe'],
        command_span_reasons: ['safe', 'not-a-reason'],
      });

      const props = display();
      expect(props.commandSpans).toEqual(spans);
      expect(props.commandSpanRisks).toBeUndefined();
      expect(props.commandSpanReasons).toBeUndefined();
    });

    it('drop a plain explanation that lacks a language', () => {
      renderShell({ command: COMMAND, plain_explanation: { en: 'only english' } });

      expect(display().plainExplanation).toBeUndefined();
    });
  });

  describe('the execution intent', () => {
    const intent = () => screen.queryByText('toolApproval.executionIntent:');

    it('is shown trimmed, from the stated intent first and the reason otherwise', () => {
      renderShell({ command: COMMAND, execution_intent: '  count files  ', reason: 'because' });
      expect(intent()?.parentElement?.textContent).toBe('toolApproval.executionIntent: count files');
      cleanup();

      renderShell({ command: COMMAND, reason: '  because  ' });
      expect(intent()?.parentElement?.textContent).toBe('toolApproval.executionIntent: because');
    });

    it('falls back to the reason when the stated intent is blank', () => {
      renderShell({ command: COMMAND, execution_intent: '   ', reason: 'because' });

      expect(intent()?.parentElement?.textContent).toBe('toolApproval.executionIntent: because');
    });

    it('is left out when neither is readable text', () => {
      renderShell({ command: COMMAND, execution_intent: 7, reason: '  ' });

      expect(intent()).toBeNull();
    });
  });

  describe('the escalated commands', () => {
    it.each([
      ['are absent', {}],
      ['are an empty list', { escalations: [] }],
      ['are not a list', { escalations: 'network' }],
    ])('show no notice when they %s', (_, extra) => {
      renderShell({ command: COMMAND, ...extra });

      expect(screen.queryByText('toolApproval.escalationTitle')).toBeNull();
    });

    it('list each command with the reason it needs approval', () => {
      renderShell({
        command: COMMAND,
        escalations: [
          { command: 'curl https://example.com', base_cmd: 'curl', reason: 'network' },
          { command: 'brand-new --flag', reason: 'brand_new_reason' },
          { base_cmd: 'rm', reason: '' },
          { command: 'who', base_cmd: 'who' },
        ],
      });

      expect(screen.getByText('toolApproval.escalationTitle')).toBeDefined();
      expect(screen.getByText('toolApproval.escalationReasons.network:')).toBeDefined();
      expect(screen.getByText('curl https://example.com')).toBeDefined();
      expect(screen.getByText('brand_new_reason:')).toBeDefined();
      expect(screen.getByText('brand-new --flag')).toBeDefined();
      expect(screen.getAllByText('toolApproval.escalationFallbackReason:')).toHaveLength(2);
      expect(screen.getByText('rm')).toBeDefined();
      expect(screen.getByText('who')).toBeDefined();
    });
  });
});
