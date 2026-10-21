import { beforeEach, describe, expect, it } from 'vitest';
import useChatStore from '@/store/useChatStore';

describe('useChatStore - environment alerts', () => {
  beforeEach(() => {
    useChatStore.getState().clearEnvironmentAlerts();
  });

  it('collects each alert category once in the Set held by the immer store', () => {
    const { addEnvironmentAlert } = useChatStore.getState();

    addEnvironmentAlert('network');
    addEnvironmentAlert('network');
    addEnvironmentAlert('auth');

    expect([...useChatStore.getState().environmentAlerts].sort()).toEqual(['auth', 'network']);
  });

  it('clears every collected category', () => {
    useChatStore.getState().addEnvironmentAlert('network');

    useChatStore.getState().clearEnvironmentAlerts();

    expect(useChatStore.getState().environmentAlerts.size).toBe(0);
  });
});
