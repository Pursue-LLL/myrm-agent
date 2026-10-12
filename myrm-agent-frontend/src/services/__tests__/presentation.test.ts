import { describe, it, expect, vi, beforeEach } from 'vitest';
import { API_BASE_URL } from '@/lib/api';
import { apiClient } from '../api';
import {
  generatePresentation,
  getPresentation,
  getPresentationDownloadUrl,
  type PresentationGenerateRequest,
  type PresentationArtifactResponse,
} from '../presentation';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('presentation service client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('generatePresentation sends POST payload to /presentation/generate', async () => {
    const payload: PresentationGenerateRequest = {
      topic: '企业级云原生微服务',
      template_style: 'enterprise_blue',
      slides_count: 5,
      enable_illustrations: true,
    };

    const mockResponse: PresentationArtifactResponse = {
      id: 'pres_123456',
      topic: '企业级云原生微服务',
      template_style: 'enterprise_blue',
      total_slides: 5,
      slides: [
        {
          slide_number: 1,
          title: '企业级云原生微服务',
          layout: 'title_hero',
          elements: [],
        },
      ],
      file_name: 'presentation_123.pptx',
      file_size_bytes: 4096,
      download_url: '/api/v1/presentation/pres_123456/download',
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await generatePresentation(payload);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/presentation/generate',
      payload,
    );
    expect(result).toEqual(mockResponse);
  });

  it('getPresentation sends GET request to /presentation/{id}', async () => {
    const mockResponse: PresentationArtifactResponse = {
      id: 'pres_123456',
      topic: '企业级云原生微服务',
      template_style: 'enterprise_blue',
      total_slides: 1,
      slides: [],
      file_name: 'presentation_123.pptx',
      file_size_bytes: 4096,
      download_url: '/api/v1/presentation/pres_123456/download',
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockResponse);

    const result = await getPresentation('pres_123456');

    expect(apiClient.get).toHaveBeenCalledWith('/presentation/pres_123456');
    expect(result).toEqual(mockResponse);
  });

  it('getPresentationDownloadUrl constructs correct download url', () => {
    const url = getPresentationDownloadUrl('pres_999');
    expect(url).toBe(`${API_BASE_URL}/presentation/pres_999/download`);
  });
});
