/**
 * Semantic Tool Group Card Component Unit Tests
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { SemanticToolGroupCard } from '../SemanticToolGroupCard';
import { useSemanticToolGroupStore } from '../useSemanticToolGroupStore';

describe('SemanticToolGroupCard', () => {
  beforeEach(() => {
    useSemanticToolGroupStore.getState().resetToDefault();
  });

  it('should render main suite with header, score and preset options', () => {
    render(<SemanticToolGroupCard />);

    expect(screen.getByTestId('semantic-tool-group-suite')).toBeInTheDocument();
    expect(screen.getByTestId('security-score')).toBeInTheDocument();

    expect(screen.getByTestId('preset-btn-strict_safe')).toBeInTheDocument();
    expect(screen.getByTestId('preset-btn-standard_assistant')).toBeInTheDocument();
    expect(screen.getByTestId('preset-btn-dev_expert')).toBeInTheDocument();
    expect(screen.getByTestId('preset-btn-custom')).toBeInTheDocument();
  });

  it('should switch preset when clicking preset buttons', () => {
    render(<SemanticToolGroupCard />);

    const strictBtn = screen.getByTestId('preset-btn-strict_safe');
    fireEvent.click(strictBtn);

    expect(useSemanticToolGroupStore.getState().preset).toBe('strict_safe');
  });

  it('should toggle group enabled status via switch checkbox', () => {
    render(<SemanticToolGroupCard />);

    const runtimeToggle = screen.getByTestId('toggle-group-runtime');
    expect(runtimeToggle).toBeChecked();

    fireEvent.click(runtimeToggle);
    expect(useSemanticToolGroupStore.getState().groups.runtime.enabled).toBe(false);
  });

  it('should expand granular tool list and toggle specific tool', () => {
    render(<SemanticToolGroupCard />);

    const expandBtn = screen.getByTestId('expand-group-runtime');
    fireEvent.click(expandBtn);

    expect(screen.getByTestId('expanded-tools-runtime')).toBeInTheDocument();

    const bashCheckbox = screen.getByTestId('tool-checkbox-runtime_bash_session');
    // Initially disabled in standard_assistant preset
    expect(bashCheckbox).not.toBeChecked();

    fireEvent.click(bashCheckbox);
    expect(bashCheckbox).toBeChecked();
    expect(
      useSemanticToolGroupStore.getState().groups.runtime.disabledToolIds
    ).not.toContain('runtime_bash_session');
  });

  it('should toggle JSON preview drawer and display valid config', () => {
    render(<SemanticToolGroupCard />);

    const previewToggleBtn = screen.getByTestId('toggle-json-preview');
    fireEvent.click(previewToggleBtn);

    const jsonSection = screen.getByTestId('json-preview-section');
    expect(jsonSection).toBeInTheDocument();
    expect(jsonSection).toHaveTextContent(/"version": "2.0.0"/);
  });
});
