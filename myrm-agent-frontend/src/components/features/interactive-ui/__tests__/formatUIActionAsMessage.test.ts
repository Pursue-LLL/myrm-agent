import { describe, expect, it } from 'vitest';
import { formatUIActionAsMessage, type UIActionMessageLabels } from '../utils';
import { stripUserMessageDisplayText } from '@/lib/utils/messageUtils';

const labels: UIActionMessageLabels = {
  header: 'Submitted',
  actionLabel: 'Action',
  dataLabel: 'Entries',
  emptyField: 'Not filled',
  actionTypes: {
    submit: 'Submit',
    cancel: 'Cancel',
    navigate: 'Navigate',
    custom: 'Confirm',
  },
};

describe('formatUIActionAsMessage', () => {
  it('appends ui_action_data for Agent while display text hides payload', () => {
    const raw = formatUIActionAsMessage(
      {
        surface_id: 'form_1',
        action_id: 'submit_btn',
        action_type: 'submit',
        data: { name: 'Alice' },
        payload: {},
      },
      labels,
    );

    expect(raw).toContain('<ui_action_data>');
    expect(raw).toContain('"surface_id":"form_1"');

    const display = stripUserMessageDisplayText(raw);
    expect(display).not.toContain('ui_action_data');
    expect(display).not.toContain('surface_id');
    expect(display).toContain('Submitted');
    expect(display).toContain('Action: Submit');
    expect(display).toContain('Alice');
  });
});
