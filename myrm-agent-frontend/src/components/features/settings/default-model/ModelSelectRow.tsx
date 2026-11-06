'use client';

import { createContext, memo, useContext } from 'react';
import { useTranslations } from 'next-intl';
import { IconSliders } from '@/components/features/icons/PremiumIcons';
import type { ProviderConfig } from '@/store/config/providerTypes';
import EnabledModelSelect, { type EnabledModel } from './EnabledModelSelect';
import { useModelSlot, type ModelSlotId } from './modelSlots';

/** What every model select on the page needs besides its own slot: the choices and the shared model dialog. */
export interface ModelSelectEnv {
  enabledModels: EnabledModel[];
  providers: ProviderConfig[];
  isModelRestricted: (modelName: string) => boolean;
  openModelConfig: (providerId: string, model: string) => void;
}

const ModelSelectEnvContext = createContext<ModelSelectEnv | null>(null);

export const ModelSelectEnvProvider = ModelSelectEnvContext.Provider;

export function useModelSelectEnv(): ModelSelectEnv {
  const env = useContext(ModelSelectEnvContext);
  if (!env) {
    throw new Error('Model selects must be rendered inside ModelSelectEnvProvider');
  }
  return env;
}

interface ModelSelectRowProps {
  slot: ModelSlotId;
  label: string;
  /** Show the shortcut that opens the selected model's settings; nested fallback selects go without it. */
  withConfigure?: boolean;
}

/** A model select bound to one slot, with the shortcut to the selected model's settings. */
const ModelSelectRow = memo<ModelSelectRowProps>(({ slot, label, withConfigure = true }) => {
  const t = useTranslations('settings.defaultModel');
  const { enabledModels, providers, isModelRestricted, openModelConfig } = useModelSelectEnv();
  const [selection, select] = useModelSlot(slot);

  const picker = (
    <EnabledModelSelect
      label={label}
      value={selection}
      onChange={select}
      enabledModels={enabledModels}
      providers={providers}
      isModelRestricted={isModelRestricted}
    />
  );
  if (!withConfigure) {
    return picker;
  }

  return (
    <div className="flex items-end gap-2">
      <div className="flex-1">{picker}</div>
      {selection && (
        <button
          type="button"
          onClick={() => openModelConfig(selection.providerId, selection.model)}
          className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
          title={t('configureModel')}
        >
          <IconSliders className="w-4 h-4 text-muted-foreground" />
        </button>
      )}
    </div>
  );
});

ModelSelectRow.displayName = 'ModelSelectRow';

export default ModelSelectRow;
