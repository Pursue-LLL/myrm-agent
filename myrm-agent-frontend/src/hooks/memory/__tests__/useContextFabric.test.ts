import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as fabricService from '@/services/memory/contextFabric';
import { useContextFabric } from '../useContextFabric';

vi.mock('@/services/memory/contextFabric', () => ({
  registerProject: vi.fn(),
  listProjects: vi.fn(),
  extractContextEntities: vi.fn(),
  linkTextToProjects: vi.fn(),
  sinkProjectInsight: vi.fn(),
}));

describe('useContextFabric', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useContextFabric());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isExtracting).toBe(false);
    expect(result.current.isLinking).toBe(false);
    expect(result.current.isSinking).toBe(false);
    expect(result.current.projects).toEqual([]);
    expect(result.current.lastExtractedEntities).toEqual([]);
    expect(result.current.lastLinkResults).toEqual([]);
    expect(result.current.lastSinkResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches and registers projects successfully', async () => {
    const mockProject: fabricService.ProjectRegistryEntryDTO = {
      project_id: 'proj_bj',
      name: '北京站',
      aliases: ['BJ-Station'],
      keywords: ['闸机'],
      description: '北京站改造项目',
      status: 'active',
    };

    vi.mocked(fabricService.listProjects).mockResolvedValueOnce([mockProject]);

    const { result } = renderHook(() => useContextFabric());

    await act(async () => {
      await result.current.fetchProjects();
    });
    expect(result.current.projects).toEqual([mockProject]);

    const newProject: fabricService.ProjectRegistryEntryDTO = {
      project_id: 'proj_sh',
      name: '上海虹桥',
      aliases: [],
      keywords: [],
      description: '',
      status: 'active',
    };
    vi.mocked(fabricService.registerProject).mockResolvedValueOnce(newProject);

    await act(async () => {
      await result.current.addProject(newProject);
    });
    expect(result.current.projects.length).toBe(2);
  });

  it('extracts context entities successfully', async () => {
    const mockEntities: fabricService.WorkContextEntityDTO[] = [
      {
        entity_id: 'ent_1',
        entity_type: 'person',
        name: '张三',
        role_or_relation: 'stakeholder',
        temporal_anchor: null,
        status: 'active',
        confidence: 0.9,
        evidence_snippet: '@张三',
      },
    ];

    vi.mocked(fabricService.extractContextEntities).mockResolvedValueOnce({
      entities: mockEntities,
      total_count: 1,
    });

    const { result } = renderHook(() => useContextFabric());

    let extracted: fabricService.WorkContextEntityDTO[] = [];
    await act(async () => {
      extracted = await result.current.extract('由@张三 负责联调');
    });

    expect(extracted).toEqual(mockEntities);
    expect(result.current.lastExtractedEntities).toEqual(mockEntities);
    expect(result.current.isExtracting).toBe(false);
  });

  it('links text to projects successfully', async () => {
    const mockMatches: fabricService.EntityMatchResultDTO[] = [
      {
        project_id: 'proj_bj',
        project_name: '北京站',
        confidence_score: 0.85,
        matched_terms: ['北京站', '闸机'],
        evidence_snippet: '北京站闸机改造',
        is_definitive: true,
      },
    ];

    vi.mocked(fabricService.linkTextToProjects).mockResolvedValueOnce({
      matches: mockMatches,
      top_project_id: 'proj_bj',
    });

    const { result } = renderHook(() => useContextFabric());

    let links: fabricService.EntityMatchResultDTO[] = [];
    await act(async () => {
      links = await result.current.link('北京站闸机改造访谈');
    });

    expect(links).toEqual(mockMatches);
    expect(result.current.lastLinkResults).toEqual(mockMatches);
    expect(result.current.isLinking).toBe(false);
  });

  it('sinks project insight successfully', async () => {
    const mockSinkResp: fabricService.InsightSinkResponseDTO = {
      success: true,
      record_id: 'rec_101',
      project_id: 'proj_bj',
      sink_target: 'PROJECT_STATE.md',
      provenance_tag: 'prov:audio_md',
      rendered_bullet: '- [BLK-01] Insight content',
      message: 'Sunken',
    };

    vi.mocked(fabricService.sinkProjectInsight).mockResolvedValueOnce(mockSinkResp);

    const { result } = renderHook(() => useContextFabric());

    let res: fabricService.InsightSinkResponseDTO | null = null;
    await act(async () => {
      res = await result.current.sink({
        candidate: {
          insight_id: 'ins_1',
          title: '闸机网络优化',
          content: '离线凭证缓存',
        },
      });
    });

    expect(res).toEqual(mockSinkResp);
    expect(result.current.lastSinkResult).toEqual(mockSinkResp);
    expect(result.current.isSinking).toBe(false);
  });

  it('handles error gracefully on extraction failure', async () => {
    vi.mocked(fabricService.extractContextEntities).mockRejectedValueOnce(
      new Error('Extraction server error'),
    );

    const { result } = renderHook(() => useContextFabric());

    await act(async () => {
      await result.current.extract('text');
    });

    expect(result.current.error).toBe('Extraction server error');
    expect(result.current.lastExtractedEntities).toEqual([]);
    expect(result.current.isExtracting).toBe(false);
  });
});
