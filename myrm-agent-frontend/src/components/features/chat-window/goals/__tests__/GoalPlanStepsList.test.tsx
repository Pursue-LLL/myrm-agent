import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GoalPlanStepsList } from '../GoalPlanStepsList';

describe('GoalPlanStepsList', () => {
  it('renders goal title and step descriptions', () => {
    render(
      <GoalPlanStepsList
        goal="Ship planning UX"
        steps={[
          { step_id: 'a', description: 'Enable planning', status: 'completed', expected_output: '', dependencies: [] },
          { step_id: 'b', description: 'Verify todos', status: 'in_progress', expected_output: '', dependencies: [] },
        ]}
        compact
      />,
    );

    expect(screen.getByText('Ship planning UX')).toBeTruthy();
    expect(screen.getByText(/Enable planning/)).toBeTruthy();
    expect(screen.getByText(/Verify todos/)).toBeTruthy();
  });
});
