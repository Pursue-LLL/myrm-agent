export type FormFieldType = 'text' | 'number' | 'select' | 'boolean';

export type FormFieldValue = string | number | boolean;

export interface SelectOption {
  label: string;
  value: string;
}

export interface FormFieldSpec {
  fieldId: string;
  label: string;
  type: FormFieldType;
  defaultValue: FormFieldValue;
  description?: string;
  options?: SelectOption[];
  required?: boolean;
}

export interface DynamicFormSpec {
  specId: string;
  version: number;
  title: string;
  description: string;
  fields: FormFieldSpec[];
  pushedAt: string;
}

export type AnswersState = Record<string, FormFieldValue>;

export type FieldDirtyMap = Record<string, boolean>;

export interface ReconciliationOutcome {
  mergedAnswers: AnswersState;
  preservedUserFieldsCount: number;
  initializedNewFieldsCount: number;
  reconciledAt: string;
}

export interface GenUIReconciliationState {
  currentSpec: DynamicFormSpec;
  answers: AnswersState;
  dirtyFields: FieldDirtyMap;
  lastReconciliation: ReconciliationOutcome | null;
  isSubmitted: boolean;

  updateFieldValue: (fieldId: string, value: FormFieldValue) => void;
  receiveNewSpec: (newSpec: DynamicFormSpec) => ReconciliationOutcome;
  simulateAgentSpecRefresh: () => ReconciliationOutcome;
  submitForm: () => AnswersState;
  resetForm: () => void;
}
