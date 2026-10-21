export type PlaybookCategory =
  | 'finance'
  | 'admin'
  | 'research'
  | 'legal'
  | 'content'
  | 'general';

export type ParameterFieldType = 'text' | 'file' | 'select' | 'textarea';

export interface PlaybookParameterField {
  id: string;
  label: string;
  type: ParameterFieldType;
  placeholder?: string;
  defaultValue?: string;
  options?: string[];
  required?: boolean;
}

export interface PlaybookScenario {
  id: string;
  title: string;
  category: PlaybookCategory;
  description: string;
  inputPlaceholder: string;
  toolsUsed: string[];
  expectedOutput: string;
  pipelineFlow: string[];
  parameters: PlaybookParameterField[];
  defaultPromptTemplate: string;
  starsCount?: number;
}

export interface ComparisonFeature {
  id: string;
  title: string;
  rawWebChat: string;
  myrmAgent: string;
  advantageDetail: string;
}
