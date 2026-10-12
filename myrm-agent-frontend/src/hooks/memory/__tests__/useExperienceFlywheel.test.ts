import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as flywheelService from '@/services/memory/experienceFlywheel';
import { useExperienceFlywheel } from '../useExperienceFlywheel';

vi.mock('@/services/memory/experienceFlywheel', () => ({
  extractExperiences: vi.fn(),
  ingestExperience: vi.fn(),
  listExperiences: vi.fn(),
  sniffMinefield: vi.fn(),
}));

describe('useExperienceFlywheel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useExperienceFlywheel());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isExtracting).toBe(false);
    expect(result.current.isSniffing).toBe(false);
    expect(result.current.experiences).toEqual([]);
    expect(result.current.extractedExperiences).toEqual([]);
    expect(result.current.minefieldAlerts).toEqual([]);
    expect(result.current.advisoryPrompt).toBe('');
    expect(result.current.lastIngestResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches and ingests experiences successfully', async () => {
    const mockExp: flywheelService.EngineeringExperienceDTO = {
      experience_id: 'exp_1',
      kind: 'bug_experience',
      target_entity: 'sqlite_driver',
      trigger_condition: 'autocommit with manual tx',
      root_cause_or_rationale: 'state conflict',
      convention_or_remedy: 'use isolation_level=None',
      created_date: '2026-09-28',
    };
    const mockIngestRes: flywheelService.IngestExperienceResponseDTO = {
      experience_id: 'exp_1',
      kind: 'bug_experience',
      target_entity: 'sqlite_driver',
      bound_dongle_block_id: 'exp_1',
      persisted: true,
      message: 'Ingested',
    };

    vi.mocked(flywheelService.listExperiences).mockResolvedValueOnce([mockExp]);
    vi.mocked(flywheelService.ingestExperience).mockResolvedValueOnce(mockIngestRes);

    const { result } = renderHook(() => useExperienceFlywheel());

    await act(async () => {
      await result.current.fetchExperiences();
    });
    expect(result.current.experiences).toEqual([mockExp]);

    const newExp: flywheelService.EngineeringExperienceDTO = {
      experience_id: 'exp_2',
      kind: 'architectural_decision',
      target_entity: 'dongle_spec',
      trigger_condition: 'spec change',
      root_cause_or_rationale: 'pure markdown portability',
      convention_or_remedy: 'keep file under 400 lines',
      created_date: '2026-09-28',
    };
    vi.mocked(flywheelService.ingestExperience).mockResolvedValueOnce({
      experience_id: 'exp_2',
      kind: 'architectural_decision',
      target_entity: 'dongle_spec',
      bound_dongle_block_id: 'exp_2',
      persisted: true,
      message: 'Ingested',
    });

    await act(async () => {
      await result.current.ingest(newExp);
    });
    expect(result.current.experiences.length).toBe(2);
  });

  it('extracts experiences from narrative successfully', async () => {
    const mockExtracted: flywheelService.EngineeringExperienceDTO[] = [
      {
        experience_id: 'ext_1',
        kind: 'bug_experience',
        target_entity: 'auth_service',
        trigger_condition: 'concurrent login',
        root_cause_or_rationale: 'race condition',
        convention_or_remedy: 'use redis distributed lock',
        created_date: '2026-09-28',
      },
    ];

    vi.mocked(flywheelService.extractExperiences).mockResolvedValueOnce({
      experiences: mockExtracted,
      total_count: 1,
    });

    const { result } = renderHook(() => useExperienceFlywheel());

    let res: flywheelService.EngineeringExperienceDTO[] = [];
    await act(async () => {
      res = await result.current.extract('模块: auth_service 踩坑记录');
    });

    expect(res).toEqual(mockExtracted);
    expect(result.current.extractedExperiences).toEqual(mockExtracted);
    expect(result.current.isExtracting).toBe(false);
  });

  it('sniffs minefield and surfaces alerts successfully', async () => {
    const mockAlerts: flywheelService.MinefieldAlertDTO[] = [
      {
        entity_matched: 'payment_table',
        experience_id: 'exp_deadlock',
        kind: 'bug_experience',
        warning_message: '⚡️ 历史雷区提醒：曾发生死锁',
        convention_to_follow: '经由 PaymentSagaService 执行',
        severity: 'critical',
      },
    ];

    vi.mocked(flywheelService.sniffMinefield).mockResolvedValueOnce({
      alerts: mockAlerts,
      advisory_prompt: '### [HISTORICAL MINEFIELD ADVISORY]\n- payment_table warning',
      has_critical_alerts: true,
    });

    const { result } = renderHook(() => useExperienceFlywheel());

    let sniffRes: flywheelService.SniffMinefieldResponseDTO | null = null;
    await act(async () => {
      sniffRes = await result.current.sniff('准备直接修改 payment_table 扣减余额');
    });

    expect(sniffRes).not.toBeNull();
    const resolvedSniff = sniffRes as unknown as flywheelService.SniffMinefieldResponseDTO;
    expect(resolvedSniff.alerts).toEqual(mockAlerts);
    expect(result.current.minefieldAlerts).toEqual(mockAlerts);
    expect(result.current.advisoryPrompt).toContain('payment_table');
    expect(result.current.isSniffing).toBe(false);
  });

  it('handles error gracefully on extraction failure', async () => {
    vi.mocked(flywheelService.extractExperiences).mockRejectedValueOnce(
      new Error('Extraction failed'),
    );

    const { result } = renderHook(() => useExperienceFlywheel());

    await act(async () => {
      await result.current.extract('fail trace');
    });

    expect(result.current.error).toBe('Extraction failed');
    expect(result.current.extractedExperiences).toEqual([]);
    expect(result.current.isExtracting).toBe(false);
  });
});
