import type { SingleModelSelection } from '@/store/config/providerTypes';

/** Store mock: the cards read the enabled provider models, which these tests do not need. */
export const providerStoreMock = () => ({
  default: (selector: (state: { providers: never[] }) => unknown) => selector({ providers: [] }),
  selectEnabledModels: () => [],
});

interface ModelSelectProps {
  value: SingleModelSelection | null;
  onChange: (selection: SingleModelSelection | null) => void;
  placeholder?: string;
}

/** Two buttons stand in for the model picker: one routes a model, one goes back to inheriting. */
export const enabledModelSelectMock = () => ({
  default: ({ onChange, value }: ModelSelectProps) => (
    <div data-model={value ? `${value.providerId}/${value.model}` : ''}>
      <button type="button" onClick={() => onChange({ providerId: 'openai_like', model: 'deepseek-chat' })}>
        use-model
      </button>
      <button type="button" onClick={() => onChange(null)}>
        inherit-model
      </button>
    </div>
  ),
});
