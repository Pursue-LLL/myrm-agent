/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - PrototypeViewport, PrototypeAnnotation, PrototypeSpec, PrototypeHandoffPayload, LivePrototypeCanvasProps
 *
 * [POS]
 * Domain types for Intent-to-Interactive-Prototype Canvas (Item 46 P0).
 * Strictly under 90 lines. Zero `any`.
 */

export type PrototypeViewport = 'desktop' | 'tablet' | 'mobile';

export interface PrototypeAnnotation {
  id: string;
  elementSelector: string;
  elementTag: string;
  comment: string;
  createdAt: number;
  resolved: boolean;
  position?: {
    x: number;
    y: number;
  };
}

export interface PrototypeSpec {
  title: string;
  intentSource: string;
  htmlContent: string;
  components: string[];
  mockData?: Record<string, unknown>;
  lastUpdated: number;
}

export interface PrototypeHandoffPayload {
  prototypeTitle: string;
  generatedSpecMarkdown: string;
  unresolvedAnnotations: PrototypeAnnotation[];
  timestamp: number;
}

export interface LivePrototypeCanvasProps {
  content: string; // HTML, JSON spec or Markdown intent
  title?: string;
  filename?: string;
  className?: string;
  onHandoffSpec?: (payload: PrototypeHandoffPayload) => void;
}
