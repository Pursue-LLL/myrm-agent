/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - SlideLayoutType, SlideElementType
 * - SlideElement, SlideData
 * - PresentationGenerateRequest, PresentationArtifactResponse
 * - generatePresentation: Async function to create structured slides & binary pptx
 * - getPresentation: Async function to query generated presentation by ID
 * - getPresentationDownloadUrl: Helper function to get binary pptx download endpoint
 *
 * [POS]
 * Client service layer for EnterprisePresentationSlideGeneratorAndVisualConceptIllustrator (Item 16).
 * Single file < 120 lines. Zero `any` types.
 */

import { apiClient } from './api';

export type SlideLayoutType =
  | 'title_hero'
  | 'two_column_comparison'
  | 'three_card_flow'
  | 'concept_illustration_focus'
  | 'summary_action';

export type SlideElementType =
  | 'text'
  | 'card'
  | 'vector_metrics'
  | 'concept_illustration'
  | 'comparison_column';

export interface SlideElement {
  element_type: SlideElementType;
  title?: string | null;
  body?: string | null;
  bullet_points?: string[];
  illustration_prompt?: string | null;
  illustration_url?: string | null;
  metric_value?: string | null;
  metric_label?: string | null;
}

export interface SlideData {
  slide_number: number;
  title: string;
  subtitle?: string | null;
  layout: SlideLayoutType;
  elements: SlideElement[];
  speaker_notes?: string | null;
}

export interface PresentationGenerateRequest {
  topic: string;
  template_style?:
    | 'enterprise_blue'
    | 'minimal_dark'
    | 'creative_gradient'
    | 'tech_emerald';
  slides_count?: number;
  enable_illustrations?: boolean;
}

export interface PresentationArtifactResponse {
  id: string;
  topic: string;
  template_style: string;
  total_slides: number;
  slides: SlideData[];
  file_name: string;
  file_size_bytes: number;
  download_url: string;
  created_at: string;
}

const PRESENTATION_BASE = '/api/v1/presentation';

export async function generatePresentation(
  payload: PresentationGenerateRequest,
): Promise<PresentationArtifactResponse> {
  return apiClient.post<PresentationArtifactResponse>(
    `${PRESENTATION_BASE}/generate`,
    payload,
  );
}

export async function getPresentation(
  id: string,
): Promise<PresentationArtifactResponse> {
  return apiClient.get<PresentationArtifactResponse>(`${PRESENTATION_BASE}/${id}`);
}

export function getPresentationDownloadUrl(id: string): string {
  return `${PRESENTATION_BASE}/${id}/download`;
}
