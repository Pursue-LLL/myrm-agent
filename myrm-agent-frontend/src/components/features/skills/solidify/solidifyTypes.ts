/**
 * Types and contracts for SolidifyToSkillWizardModal.
 * Adheres to parameter minimization principles and 4-in-1 standard bundle.
 */

export interface ParameterExtractionRule {
  name: string;
  description: string;
  defaultValue?: string;
  placeholderPattern: string;
  required: boolean;
}

export interface SolidifySkillRequestPayload {
  name: string;
  displayTitle: string;
  description: string;
  category: string;
  sourceArtifactContent: string;
  sourceArtifactType?: string;
  customParameters?: ParameterExtractionRule[];
  includePlanBeforeExecuteHint?: boolean;
}

export interface SolidifySkillResponseData {
  skillId: string;
  name: string;
  displayTitle: string;
  description: string;
  parameters: ParameterExtractionRule[];
  bundleFiles: string[];
  previewUrl?: string;
  createdAt: string;
}

export type SolidifyWizardStep = 'params' | 'bundle' | 'success';
