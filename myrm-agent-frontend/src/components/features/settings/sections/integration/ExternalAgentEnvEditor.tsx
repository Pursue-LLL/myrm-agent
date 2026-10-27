'use client';

import { memo, useId, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { IconEye, IconEyeOff, IconPlus, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import type { ExternalAgentAuthMode } from '@/services/config';
import { envRowProblems, newEnvRow, type EnvRow, type EnvRowProblem } from './externalAgentModel';

const PROBLEM_MESSAGE_KEYS: Record<EnvRowProblem, string> = {
  missing: 'envNameMissing',
  invalid: 'envNameInvalid',
  duplicate: 'envNameDuplicate',
};

interface ExternalAgentEnvEditorProps {
  rows: EnvRow[];
  authMode: ExternalAgentAuthMode;
  onChange: (rows: EnvRow[]) => void;
}

/** Name/value lines that become the agent's environment; values are secrets, so they stay masked until revealed. */
const ExternalAgentEnvEditor = memo(({ rows, authMode, onChange }: ExternalAgentEnvEditorProps) => {
  const t = useTranslations('settings.developer.externalAgents');
  const tKeyValue = useTranslations('common.keyValueEditor');
  const labelId = useId();
  const [revealed, setRevealed] = useState(false);
  const rowToFocus = useRef<string | null>(null);
  const problems = useMemo(() => envRowProblems(rows), [rows]);

  const update = (id: string, patch: Partial<Pick<EnvRow, 'name' | 'value'>>) =>
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));

  const add = () => {
    const row = newEnvRow();
    rowToFocus.current = row.id;
    onChange([...rows, row]);
  };

  // A line added by the user takes the cursor, once, as soon as its input exists.
  const focusIfNew = (input: HTMLInputElement | null, id: string) => {
    if (input && rowToFocus.current === id) {
      rowToFocus.current = null;
      input.focus();
    }
  };

  return (
    <fieldset aria-labelledby={labelId} className="m-0 min-w-0 space-y-2 border-0 p-0" data-testid="external-agent-env">
      <div className="flex items-center justify-between gap-2">
        <p id={labelId} className="text-xs font-medium text-muted-foreground">
          {t('env')}
        </p>
        {rows.length > 0 && (
          <button
            type="button"
            aria-pressed={revealed}
            onClick={() => setRevealed((shown) => !shown)}
            className="inline-flex items-center gap-1 rounded px-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {revealed ? <IconEyeOff className="w-3.5 h-3.5" /> : <IconEye className="w-3.5 h-3.5" />}
            {t('envShowValues')}
          </button>
        )}
      </div>

      {rows.map((row) => {
        const problem = problems.get(row.id);
        return (
          <div key={row.id} className="space-y-1">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <Input
                ref={(input) => focusIfNew(input, row.id)}
                value={row.name}
                onChange={(e) => update(row.id, { name: e.target.value })}
                placeholder={tKeyValue('keyPlaceholder')}
                aria-label={tKeyValue('keyPlaceholder')}
                aria-invalid={problem ? true : undefined}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                className="col-start-1 row-start-1 font-mono text-xs aria-invalid:border-destructive"
              />
              <Input
                type={revealed ? 'text' : 'password'}
                value={row.value}
                onChange={(e) => update(row.id, { value: e.target.value })}
                placeholder={tKeyValue('valuePlaceholder')}
                aria-label={tKeyValue('valuePlaceholder')}
                autoComplete="new-password"
                autoCapitalize="off"
                spellCheck={false}
                className="col-span-2 row-start-2 font-mono text-xs sm:col-span-1 sm:col-start-2 sm:row-start-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => onChange(rows.filter((other) => other.id !== row.id))}
                aria-label={t('envRemove')}
                className="col-start-2 row-start-1 h-8 w-8 shrink-0 sm:col-start-3"
              >
                <IconTrash className="w-3.5 h-3.5 text-muted-foreground" />
              </Button>
            </div>
            {problem && <p className="text-[11px] text-destructive">{t(PROBLEM_MESSAGE_KEYS[problem])}</p>}
          </div>
        );
      })}

      <Button type="button" variant="outline" size="sm" onClick={add}>
        <IconPlus className="w-3.5 h-3.5 mr-1.5" />
        {t('envAdd')}
      </Button>
      <p className="text-[11px] text-muted-foreground/60">
        {t(authMode === 'api_key' ? 'envHintApiKey' : 'envHintSubscription')}
      </p>
    </fieldset>
  );
});

ExternalAgentEnvEditor.displayName = 'ExternalAgentEnvEditor';

export default ExternalAgentEnvEditor;
