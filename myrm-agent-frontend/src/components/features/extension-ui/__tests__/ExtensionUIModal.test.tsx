import { describe, it, expect, beforeEach, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExtensionUIModal } from '../ExtensionUIModal';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';
import type { UIRequestItem } from '../extensionUITypes';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (key === 'queuePending' && params?.count) {
      return `${params.count} more pending`;
    }
    const translations: Record<string, string> = {
      title: 'Interaction Prompt',
      confirmButton: 'Confirm',
      cancelButton: 'Cancel',
      submitButton: 'Submit',
      saveButton: 'Save & Submit',
      dismiss: 'Dismiss',
      inputPlaceholder: 'Enter value...',
    };
    return translations[key] ?? key;
  },
}));

describe('ExtensionUIModal component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExtensionUIStore.getState().reset();
  });

  it('renders nothing when there is no active request', () => {
    const { container } = render(<ExtensionUIModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders select mode with options and allows option picking', () => {
    const req: UIRequestItem = {
      request_id: 'req-sel-1',
      request_type: 'select',
      title: 'Choose Environment',
      options: [
        { label: 'Production Tier', value: 'prod', description: 'Real environment' },
        { label: 'Staging Tier', value: 'staging', description: 'Testing environment' },
      ],
      default_value: 'staging',
    };

    useExtensionUIStore.getState().enqueueRequest(req);
    render(<ExtensionUIModal />);

    expect(screen.getByText('Choose Environment')).toBeDefined();
    expect(screen.getByText('Production Tier')).toBeDefined();
    expect(screen.getByText('Staging Tier')).toBeDefined();

    // Pick option
    const prodOption = screen.getByText('Production Tier');
    fireEvent.click(prodOption);
    expect(useExtensionUIStore.getState().selectedValue).toBe('prod');
  });

  it('renders confirm mode with confirm and cancel buttons', () => {
    const req: UIRequestItem = {
      request_id: 'req-conf-1',
      request_type: 'confirm',
      title: 'Are you sure?',
      message: 'This will destroy temporary files.',
    };

    useExtensionUIStore.getState().enqueueRequest(req);
    render(<ExtensionUIModal />);

    expect(screen.getByText('Are you sure?')).toBeDefined();
    expect(screen.getByText('This will destroy temporary files.')).toBeDefined();
    expect(screen.getByText('Confirm')).toBeDefined();
    expect(screen.getByText('Cancel')).toBeDefined();
  });

  it('renders input mode and tracks typed value', () => {
    const req: UIRequestItem = {
      request_id: 'req-inp-1',
      request_type: 'input',
      title: 'Enter API Key',
      placeholder: 'sk-...',
    };

    useExtensionUIStore.getState().enqueueRequest(req);
    render(<ExtensionUIModal />);

    expect(screen.getByText('Enter API Key')).toBeDefined();
    const inputEl = screen.getByPlaceholderText('sk-...');
    fireEvent.change(inputEl, { target: { value: 'sk-123456' } });
    expect(useExtensionUIStore.getState().inputValue).toBe('sk-123456');
  });

  it('renders editor mode with content and language badge', () => {
    const req: UIRequestItem = {
      request_id: 'req-ed-1',
      request_type: 'editor',
      title: 'Review Schema',
      content: '{"type": "object"}',
      language: 'json',
    };

    useExtensionUIStore.getState().enqueueRequest(req);
    render(<ExtensionUIModal />);

    expect(screen.getByText('Review Schema')).toBeDefined();
    expect(screen.getByText(/json/i)).toBeDefined();
    const textarea = screen.getByDisplayValue('{"type": "object"}');
    fireEvent.change(textarea, { target: { value: '{"type": "string"}' } });
    expect(useExtensionUIStore.getState().editorValue).toBe('{"type": "string"}');
  });
});
