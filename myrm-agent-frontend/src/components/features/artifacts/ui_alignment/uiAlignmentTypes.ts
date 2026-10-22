/**
 * [INPUT]
 * - None (domain contract types)
 *
 * [OUTPUT]
 * - UiVariantStyle, UiVariantItem, VisualAnnotationItem, VisualContractItem, UiAlignmentState
 *
 * [POS]
 * Types for Multi-Turn UI Design Visual Alignment Workflow (Item 39 P0).
 * Zero `any`.
 */

export type UiVariantStyle =
  | "modern_bento"
  | "minimal_dark"
  | "glassmorphism"
  | "neo_brutalism"
  | "custom";

export interface UiVariantItem {
  variant_id: string;
  title: string;
  style_theme: UiVariantStyle;
  html_content: string;
  css_tokens: Record<string, string>;
  description: string;
  created_at_ms: number;
}

export interface VisualAnnotationItem {
  annotation_id: string;
  variant_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  comment: string;
  label: string;
  created_at_ms: number;
}

export interface VisualContractItem {
  contract_id: string;
  session_id: string;
  approved_variant_id: string;
  style_theme: UiVariantStyle;
  dom_outline: string;
  design_tokens: Record<string, string>;
  annotations_count: number;
  enforcement_prompt: string;
  finalized_at_ms: number;
}

export interface UiAlignmentState {
  variants: UiVariantItem[];
  selectedVariantId: string | null;
  annotations: Record<string, VisualAnnotationItem[]>; // variant_id -> annotations
  activeContract: VisualContractItem | null;
  isAnnotating: boolean;
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  setOpen: (open: boolean) => void;
  setAnnotating: (annotating: boolean) => void;
  selectVariant: (variantId: string) => void;
  fetchVariants: (chatId: string) => Promise<void>;
  registerVariant: (
    chatId: string,
    variant: {
      title: string;
      style_theme: UiVariantStyle;
      html_content: string;
      css_tokens?: Record<string, string>;
      description?: string;
    }
  ) => Promise<UiVariantItem | null>;
  fetchAnnotations: (chatId: string, variantId: string) => Promise<void>;
  addAnnotation: (
    chatId: string,
    variantId: string,
    annotation: {
      x: number;
      y: number;
      width: number;
      height: number;
      comment: string;
      label?: string;
    }
  ) => Promise<VisualAnnotationItem | null>;
  finalizeContract: (chatId: string, variantId: string) => Promise<VisualContractItem | null>;
  fetchContract: (chatId: string) => Promise<void>;
  reset: () => void;
}
