export type PresentationToolName =
  | 'present_products'
  | 'present_itinerary'
  | 'present_suggestions'
  | 'present_comparison';

export interface SuggestionChipItem {
  id: string;
  label: string;
  actionQuery: string;
  position: number;
}

export interface ProductPresentationItem {
  id: string;
  title: string;
  subtitle?: string;
  highlight?: string;
  position: number;
}

export interface ItineraryStepItem {
  step: number;
  title: string;
  description: string;
  timeEstimate?: string;
  position: number;
}

export interface ComparisonRowItem {
  featureName: string;
  values: Record<string, string>;
  position: number;
}

export type PresentationItem =
  | SuggestionChipItem
  | ProductPresentationItem
  | ItineraryStepItem;

export interface PresentationPayload {
  id: string;
  toolName: PresentationToolName;
  title: string;
  description?: string;
  items: PresentationItem[];
  createdAt: number;
}

export interface PositionalResolutionResult {
  matchedItem: PresentationItem | null;
  position: number | null;
  confidence: number;
  rationale: string;
}
