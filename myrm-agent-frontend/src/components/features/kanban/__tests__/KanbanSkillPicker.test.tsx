import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { KanbanSkillPicker } from '../KanbanSkillPicker';

const marketSkills = [
  {
    id: 'web-search',
    name: 'Web Search',
    description: 'Search the web',
    type: 'prebuilt',
  },
  {
    id: 'content-writer',
    name: 'Content Writer',
    description: 'Write content',
    type: 'prebuilt',
  },
];

vi.mock('@/store/skill', () => ({
  useSkillStore: (selector: (state: object) => unknown) =>
    selector({
      marketSkills,
      localSkills: [],
      fetchMarketSkills: vi.fn(),
      fetchLocalSkills: vi.fn(),
    } as object),
}));

const PLACEHOLDER = 'Select skills (optional)';

function renderPicker(value = '', onChange = vi.fn()) {
  return render(<KanbanSkillPicker value={value} onChange={onChange} placeholder={PLACEHOLDER} />);
}

function openPicker() {
  fireEvent.click(screen.getByRole('button', { name: PLACEHOLDER }));
}

describe('KanbanSkillPicker', () => {
  it('shows placeholder when no skills selected', () => {
    renderPicker();
    expect(screen.getByText(PLACEHOLDER)).toBeTruthy();
  });

  it('renders known skill names as chips', () => {
    renderPicker('web-search, content-writer');
    expect(screen.getByText('Web Search')).toBeTruthy();
    expect(screen.getByText('Content Writer')).toBeTruthy();
  });

  it('marks persisted ids that no longer exist as unknown', () => {
    renderPicker('web-search, vanished-skill');
    expect(screen.getByText('skillsUnknown')).toBeTruthy();
  });

  it('opens the list and emits sorted ids when toggling a skill', () => {
    const onChange = vi.fn();
    renderPicker('content-writer', onChange);
    fireEvent.click(screen.getByRole('button', { name: /skillsCount/ }));
    fireEvent.click(screen.getByRole('option', { name: /Web Search/ }));
    expect(onChange).toHaveBeenCalledWith('content-writer, web-search');
  });

  it('removes a skill when its chip close button is clicked', () => {
    const onChange = vi.fn();
    renderPicker('web-search, content-writer', onChange);
    fireEvent.click(screen.getAllByLabelText('skillsRemove')[0]);
    expect(onChange).toHaveBeenCalledWith('content-writer');
  });

  it('filters the skill list by search query', () => {
    renderPicker();
    openPicker();
    const input = screen.getByPlaceholderText('skillsSearch');
    fireEvent.change(input, { target: { value: 'web' } });
    expect(screen.getByText('Web Search')).toBeTruthy();
    expect(screen.queryByText('Content Writer')).toBeNull();
  });
});
