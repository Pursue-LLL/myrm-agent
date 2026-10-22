import type { ChatTurnItem, TurnProvenanceMeta } from '../turnLineageTypes';

/** The fields a lineage test cares about; the rest of a full turn is derived. */
export interface TurnFixture {
  id: string;
  turnNumber: number;
  author: string;
  content: string;
  provenance: Pick<TurnProvenanceMeta, 'originType' | 'timestamp' | 'causalityParentId'>;
}

export function asChatTurn(fixture: TurnFixture): ChatTurnItem {
  return {
    ...fixture,
    role: fixture.provenance.originType === 'user_direct' ? 'user' : 'assistant',
    tokensUsed: 0,
    durationMs: 0,
    provenance: {
      originRefId: fixture.id,
      triggerSourceTitle: fixture.author,
      executedByAgent: fixture.author,
      ...fixture.provenance,
    },
  };
}
