import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RiskRuleEditor from '../RiskRuleEditor';
import RiskRuleRow from '../RiskRuleRow';
import type { RiskRule } from '../risk-rules-types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const rule = (overrides: Partial<RiskRule> = {}): RiskRule => ({
  rule_id: 'my_rule',
  display_name: 'Project Falcon',
  description: null,
  pattern: 'falcon',
  severity: 'high',
  category: 'custom',
  is_enabled: true,
  is_builtin: false,
  sort_order: 0,
  created_at: null,
  updated_at: null,
  ...overrides,
});

function renderRow(row: RiskRule, name = row.display_name, description: string | null = null) {
  const handlers = { onToggle: vi.fn(), onEdit: vi.fn(), onDuplicate: vi.fn(), onDelete: vi.fn() };
  render(<RiskRuleRow rule={row} name={name} description={description} {...handlers} />);
  return handlers;
}

describe('RiskRuleRow', () => {
  it('shows the name it is given and reports each action with the rule it concerns', () => {
    const row = rule();
    const handlers = renderRow(row, 'Falcon (shown)');

    expect(screen.getByText('Falcon (shown)')).toBeTruthy();
    fireEvent.click(screen.getByRole('switch', { name: 'Falcon (shown)' }));
    fireEvent.click(screen.getByRole('button', { name: 'editRule' }));
    fireEvent.click(screen.getByRole('button', { name: 'duplicateRule' }));
    fireEvent.click(screen.getByRole('button', { name: 'deleteRule' }));

    expect(handlers.onToggle).toHaveBeenCalledWith('my_rule', false);
    expect(handlers.onEdit).toHaveBeenCalledWith(row);
    expect(handlers.onDuplicate).toHaveBeenCalledWith(row);
    expect(handlers.onDelete).toHaveBeenCalledWith('my_rule');
  });

  it('offers no delete for a built-in rule and marks it as built in', () => {
    renderRow(rule({ rule_id: 'api_key_like', is_builtin: true }));

    expect(screen.queryByRole('button', { name: 'deleteRule' })).toBeNull();
    expect(screen.getByText('builtin')).toBeTruthy();
  });

  it('prints a severity it does not know as it is stored', () => {
    renderRow(rule({ severity: 'critical' }));

    expect(screen.getByText('critical')).toBeTruthy();
  });
});

describe('RiskRuleEditor', () => {
  function renderEditor(editing: Partial<RiskRule>, isCreating: boolean) {
    const handlers = { onChange: vi.fn(), onSave: vi.fn(), onCancel: vi.fn() };
    render(<RiskRuleEditor rule={editing} isCreating={isCreating} {...handlers} />);
    return handlers;
  }

  it('fixes the id of an existing rule and the pattern of a built-in one', () => {
    renderEditor(rule({ rule_id: 'api_key_like', is_builtin: true }), false);

    expect((screen.getByPlaceholderText('ruleId') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByPlaceholderText('pattern') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText('builtinCannotEditPattern')).toBeTruthy();
  });

  it('lets a new rule set its id and pattern, and reports the edit merged into the rule', () => {
    const handlers = renderEditor({ rule_id: '', pattern: '', severity: 'medium', category: 'custom' }, true);

    expect((screen.getByPlaceholderText('ruleId') as HTMLInputElement).disabled).toBe(false);
    fireEvent.change(screen.getByPlaceholderText('pattern'), { target: { value: 'falcon' } });

    expect(handlers.onChange).toHaveBeenCalledWith({
      rule_id: '',
      pattern: 'falcon',
      severity: 'medium',
      category: 'custom',
    });
  });

  it('saves and cancels through the callbacks it is given', () => {
    const handlers = renderEditor(rule(), false);

    fireEvent.click(screen.getByRole('button', { name: 'saveRule' }));
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(handlers.onSave).toHaveBeenCalledTimes(1);
    expect(handlers.onCancel).toHaveBeenCalledTimes(1);
  });
});
