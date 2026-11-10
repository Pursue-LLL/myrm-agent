import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { SubagentsPanel, type EphemeralSubagentConfig } from '../SubagentsPanel';

const t = (key: string) => key;

type Roles = Record<string, EphemeralSubagentConfig>;

interface Draft {
  roles: Roles;
  errors: Record<string, string>;
}

/** The editor around the panel: it owns both drafts and refuses to save while any role carries an error. */
function Editor({ initial }: { initial: Roles }) {
  const [roles, setRoles] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  return (
    <>
      <SubagentsPanel
        localEphemeralSubagents={roles}
        setLocalEphemeralSubagents={setRoles}
        t={t}
        tCommon={t}
        displayNameErrors={errors}
        setDisplayNameErrors={setErrors}
      />
      <button type="button" disabled={Object.values(errors).some((message) => message !== '')}>
        save
      </button>
      <output data-testid="draft">{JSON.stringify({ roles, errors })}</output>
    </>
  );
}

export const user = () => userEvent.setup();

export function renderEditor(initial: Roles = {}): void {
  render(<Editor initial={initial} />);
}

/** What the editor currently holds. */
export const draft = (): Draft => JSON.parse(screen.getByTestId('draft').textContent ?? '{}') as Draft;

export const saveButton = () => screen.getByRole('button', { name: 'save' });

/** The select inside a role's card, found through the id the card gives it. */
export const roleSelect = (kind: 'control-scope' | 'theme-color', key: string): HTMLElement => {
  const element = document.getElementById(`${kind}-${key}`);
  if (!element) {
    throw new Error(`no ${kind} select for ${key}`);
  }
  return element;
};

export const displayNameInput = (key: string): HTMLInputElement => {
  const element = document.getElementById(`display-name-${key}`);
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`no display name field for ${key}`);
  }
  return element;
};
