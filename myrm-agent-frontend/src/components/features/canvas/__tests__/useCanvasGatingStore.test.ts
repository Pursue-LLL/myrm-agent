import { beforeEach, describe, expect, it } from 'vitest';
import { useCanvasGatingStore } from '../useCanvasGatingStore';

describe('useCanvasGatingStore', () => {
  beforeEach(() => {
    useCanvasGatingStore.getState().reset();
  });

  it('initializes with default empty security state', () => {
    const state = useCanvasGatingStore.getState();
    expect(state.allowedDomains).toEqual([]);
    expect(state.pendingRequests).toEqual([]);
    expect(state.auditLogs).toEqual([]);
    expect(state.isDomainAllowed('api.example.com')).toBe(false);
  });

  it('queues unverified egress requests and records audit log', () => {
    const store = useCanvasGatingStore.getState();
    const result = store.registerEgressRequest({
      url: 'https://api.external.org/data',
      domain: 'api.external.org',
      method: 'GET',
    });

    expect(result.allowed).toBe(false);
    expect(result.requestId).toMatch(/^req_/);

    const state = useCanvasGatingStore.getState();
    expect(state.pendingRequests).toHaveLength(1);
    expect(state.pendingRequests[0]).toMatchObject({
      domain: 'api.external.org',
      method: 'GET',
      status: 'pending',
    });

    expect(state.auditLogs).toHaveLength(1);
    expect(state.auditLogs[0].type).toBe('egress-requested');
  });

  it('auto-allows requests for domains already in the allowlist', () => {
    // Manually approve with persist domain
    const store = useCanvasGatingStore.getState();
    const firstReq = store.registerEgressRequest({
      url: 'https://trusted.cdn.com/lib.js',
      domain: 'trusted.cdn.com',
      method: 'GET',
    });

    store.approveRequest(firstReq.requestId, true);

    expect(useCanvasGatingStore.getState().isDomainAllowed('trusted.cdn.com')).toBe(true);

    // Second request to same domain should be automatically allowed
    const secondReq = useCanvasGatingStore.getState().registerEgressRequest({
      url: 'https://trusted.cdn.com/other.json',
      domain: 'trusted.cdn.com',
      method: 'GET',
    });

    expect(secondReq.allowed).toBe(true);
    expect(useCanvasGatingStore.getState().pendingRequests).toHaveLength(0);

    const latestLog = useCanvasGatingStore.getState().auditLogs[0];
    expect(latestLog.type).toBe('egress-allowed');
  });

  it('removes pending request upon user denial', () => {
    const store = useCanvasGatingStore.getState();
    const req = store.registerEgressRequest({
      url: 'https://malicious.tracker.net/ping',
      domain: 'malicious.tracker.net',
      method: 'POST',
    });

    expect(useCanvasGatingStore.getState().pendingRequests).toHaveLength(1);

    useCanvasGatingStore.getState().denyRequest(req.requestId);

    const state = useCanvasGatingStore.getState();
    expect(state.pendingRequests).toHaveLength(0);
    expect(state.isDomainAllowed('malicious.tracker.net')).toBe(false);

    const latestLog = state.auditLogs[0];
    expect(latestLog.type).toBe('egress-denied');
  });

  it('resets all security states', () => {
    const store = useCanvasGatingStore.getState();
    const req = store.registerEgressRequest({
      url: 'https://api.test.com/v1',
      domain: 'api.test.com',
      method: 'GET',
    });
    store.approveRequest(req.requestId, true);
    expect(useCanvasGatingStore.getState().allowedDomains).toHaveLength(1);

    useCanvasGatingStore.getState().reset();
    expect(useCanvasGatingStore.getState().allowedDomains).toEqual([]);
    expect(useCanvasGatingStore.getState().pendingRequests).toEqual([]);
    expect(useCanvasGatingStore.getState().auditLogs).toEqual([]);
  });
});
