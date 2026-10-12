import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as domainService from '@/services/memory/domainIsolation';
import { useDomainIsolation } from '../useDomainIsolation';

vi.mock('@/services/memory/domainIsolation', () => ({
  listConnectorBindings: vi.fn(),
  setConnectorBinding: vi.fn(),
  getConnectorBinding: vi.fn(),
  deleteConnectorBinding: vi.fn(),
  listDomainGrants: vi.fn(),
  getDomainGrant: vi.fn(),
  updateDomainGrant: vi.fn(),
  validateDomainRecall: vi.fn(),
  validateDomainWrite: vi.fn(),
  evaluateChannelEgress: vi.fn(),
}));

describe('useDomainIsolation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockBinding: domainService.ConnectorDomainBindingDTO = {
    connector_id: 'feishu_01',
    channel: 'feishu',
    account_id: 'user_feishu',
    domain: 'work',
    created_at: '2026-10-10T00:00:00Z',
    updated_at: '2026-10-10T00:00:00Z',
  };

  const mockGrants: domainService.DomainGrantConfigDTO[] = [
    {
      domain: 'work',
      allow_write: true,
      allow_recall: true,
      allow_proactive: true,
      allow_egress: true,
    },
    {
      domain: 'personal',
      allow_write: true,
      allow_recall: true,
      allow_proactive: false,
      allow_egress: false,
    },
  ];

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useDomainIsolation());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isEvaluating).toBe(false);
    expect(result.current.bindings).toEqual([]);
    expect(result.current.grants).toEqual([]);
    expect(result.current.activeDomain).toBe('work');
    expect(result.current.lastEgressDecision).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches, binds, and unbinds connectors successfully', async () => {
    vi.mocked(domainService.listConnectorBindings).mockResolvedValueOnce([mockBinding]);

    const { result } = renderHook(() => useDomainIsolation());

    let fetched: domainService.ConnectorDomainBindingDTO[] = [];
    await act(async () => {
      fetched = await result.current.fetchBindings('work');
    });

    expect(fetched).toEqual([mockBinding]);
    expect(result.current.bindings).toEqual([mockBinding]);

    // Bind new connector
    const newBinding: domainService.ConnectorDomainBindingDTO = {
      connector_id: 'wechat_02',
      channel: 'wechat',
      account_id: 'wx_user',
      domain: 'personal',
      created_at: '2026-10-10T01:00:00Z',
      updated_at: '2026-10-10T01:00:00Z',
    };
    vi.mocked(domainService.setConnectorBinding).mockResolvedValueOnce(newBinding);

    let bound: domainService.ConnectorDomainBindingDTO | null = null;
    await act(async () => {
      bound = await result.current.bindConnector({
        connector_id: 'wechat_02',
        domain: 'personal',
        channel: 'wechat',
      });
    });

    expect(bound).toEqual(newBinding);
    expect(result.current.bindings).toContainEqual(newBinding);

    // Unbind connector
    vi.mocked(domainService.deleteConnectorBinding).mockResolvedValueOnce(undefined);

    let unbindSuccess = false;
    await act(async () => {
      unbindSuccess = await result.current.unbindConnector('feishu_01');
    });

    expect(unbindSuccess).toBe(true);
    expect(result.current.bindings.map((b) => b.connector_id)).toEqual(['wechat_02']);
  });

  it('fetches and modifies domain grants independently', async () => {
    vi.mocked(domainService.listDomainGrants).mockResolvedValueOnce(mockGrants);

    const { result } = renderHook(() => useDomainIsolation());

    let fetchedGrants: domainService.DomainGrantConfigDTO[] = [];
    await act(async () => {
      fetchedGrants = await result.current.fetchGrants();
    });

    expect(fetchedGrants).toEqual(mockGrants);
    expect(result.current.grants).toEqual(mockGrants);

    // Modify personal grant
    const updatedPersonalGrant: domainService.DomainGrantConfigDTO = {
      domain: 'personal',
      allow_write: false,
      allow_recall: false,
      allow_proactive: false,
      allow_egress: false,
    };
    vi.mocked(domainService.updateDomainGrant).mockResolvedValueOnce(updatedPersonalGrant);

    let updated: domainService.DomainGrantConfigDTO | null = null;
    await act(async () => {
      updated = await result.current.modifyGrant('personal', {
        allow_write: false,
        allow_recall: false,
      });
    });

    expect(updated).toEqual(updatedPersonalGrant);
    expect(
      result.current.grants.find((g) => g.domain === 'personal')?.allow_write
    ).toBe(false);
    expect(
      result.current.grants.find((g) => g.domain === 'work')?.allow_write
    ).toBe(true);
  });

  it('validates recall and write permissions correctly', async () => {
    const mockRecallResp: domainService.ValidateRecallResponse = {
      allowed: false,
      reason: '跨域隔离拦截',
      is_cross_domain: true,
    };
    vi.mocked(domainService.validateDomainRecall).mockResolvedValueOnce(mockRecallResp);

    const { result } = renderHook(() => useDomainIsolation());

    let recallCheck: domainService.ValidateRecallResponse | null = null;
    await act(async () => {
      recallCheck = await result.current.checkRecall('personal', false);
    });

    expect(recallCheck).toEqual(mockRecallResp);

    // Validate write
    const mockWriteResp: domainService.ValidateWriteResponse = {
      allowed: true,
      reason: '允许写入',
    };
    vi.mocked(domainService.validateDomainWrite).mockResolvedValueOnce(mockWriteResp);

    let writeCheck: domainService.ValidateWriteResponse | null = null;
    await act(async () => {
      writeCheck = await result.current.checkWrite('work');
    });

    expect(writeCheck).toEqual(mockWriteResp);
  });

  it('evaluates channel egress privacy redlines', async () => {
    const mockEgressDecision: domainService.EgressDecisionDTO = {
      allowed: false,
      requires_user_confirmation: true,
      reason: '隐私红线触发：严禁静默外发',
      source_domain: 'personal',
      target_channel: 'slack_public',
      is_cross_domain: true,
    };
    vi.mocked(domainService.evaluateChannelEgress).mockResolvedValueOnce(mockEgressDecision);

    const { result } = renderHook(() => useDomainIsolation());

    let decision: domainService.EgressDecisionDTO | null = null;
    await act(async () => {
      decision = await result.current.checkEgress('personal', 'slack_public', false);
    });

    expect(decision).toEqual(mockEgressDecision);
    expect(result.current.lastEgressDecision).toEqual(mockEgressDecision);
  });
});
