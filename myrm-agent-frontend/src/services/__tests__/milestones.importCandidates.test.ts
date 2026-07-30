import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listAssessmentImportArtifactCandidates,
  normalizeAssessmentImportArtifactCandidates,
} from '../milestones';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

describe('milestones import artifact candidates', () => {
  let apiRequestMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    const api = await import('@/lib/api');
    apiRequestMock = api.apiRequest as unknown as ReturnType<typeof vi.fn>;
    apiRequestMock.mockReset();
  });

  it('normalizes candidates and sorts by updated time', () => {
    const normalized = normalizeAssessmentImportArtifactCandidates(
      [
        {
          id: 'artifact-older',
          name: 'Older',
          updated_at: '2026-07-28T10:00:00Z',
          latest_version_id: 'v1',
        },
        {
          id: 'artifact-latest',
          name: 'Latest',
          updated_at: '2026-07-29T10:00:00Z',
          latest_version_id: 'v2',
        },
      ],
      8,
    );

    expect(normalized.map((item) => item.id)).toEqual(['artifact-latest', 'artifact-older']);
  });

  it('drops invalid ids and falls back empty name to id', () => {
    const normalized = normalizeAssessmentImportArtifactCandidates(
      [
        {
          id: '   ',
          name: 'Invalid',
          updated_at: '2026-07-28T10:00:00Z',
        },
        {
          id: 'artifact-valid',
          name: '  ',
          updated_at: '2026-07-28T10:00:00Z',
        },
      ],
      8,
    );

    expect(normalized).toEqual([
      {
        id: 'artifact-valid',
        name: 'artifact-valid',
        updated_at: '2026-07-28T10:00:00Z',
        latest_version_id: null,
      },
    ]);
  });

  it('loads candidates from files artifacts endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({
      artifacts: [
        {
          id: 'artifact-a',
          name: 'Artifact A',
          updated_at: '2026-07-28T10:00:00Z',
          latest_version_id: 'version-a',
        },
      ],
    });

    const candidates = await listAssessmentImportArtifactCandidates(8);

    expect(apiRequestMock).toHaveBeenCalledWith('/files/artifacts?limit=8');
    expect(candidates).toEqual([
      {
        id: 'artifact-a',
        name: 'Artifact A',
        updated_at: '2026-07-28T10:00:00Z',
        latest_version_id: 'version-a',
      },
    ]);
  });

  it('caps list query limit to backend guardrail', async () => {
    apiRequestMock.mockResolvedValueOnce({ artifacts: [] });

    await listAssessmentImportArtifactCandidates(9999);

    expect(apiRequestMock).toHaveBeenCalledWith('/files/artifacts?limit=500');
  });
});
