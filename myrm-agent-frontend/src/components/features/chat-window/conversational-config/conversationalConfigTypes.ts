export type ConfigIntentCategory =
  | 'model_switch'
  | 'api_key_entry'
  | 'search_engine'
  | 'channel_binding';

export interface ConfigParamItem {
  key: string;
  label: string;
  type: 'text' | 'password' | 'select';
  value: string;
  defaultValue?: string;
  placeholder?: string;
  options?: string[];
  isSecret?: boolean;
}

export interface ConversationalConfigIntent {
  id: string;
  category: ConfigIntentCategory;
  title: string;
  description: string;
  matchedUtterance: string;
  params: ConfigParamItem[];
  isApplied: boolean;
  createdAt: number;
}

export interface NonDevWizardStep {
  stepNumber: number;
  title: string;
  subtitle: string;
  options: Array<{
    id: string;
    label: string;
    desc: string;
    icon: string;
  }>;
}
