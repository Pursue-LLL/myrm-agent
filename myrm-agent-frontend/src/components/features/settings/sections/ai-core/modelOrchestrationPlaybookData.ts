export interface OrchestrationStrategy {
  id: string;
  badgeKey: string;
  titleKey: string;
  descriptionKey: string;
  idealForKeys: string[];
  slots: {
    brainRoleKey: string;
    brainDescKey: string;
    handsRoleKey: string;
    handsDescKey: string;
    fallbackRoleKey?: string;
    fallbackDescKey?: string;
  };
  tokenEconomicsKey: string;
  recommendedSlotLink: 'base' | 'lite' | 'routing' | 'moa';
}

export const ORCHESTRATION_STRATEGIES: OrchestrationStrategy[] = [
  {
    id: 'brain_and_hands',
    badgeKey: 'strategies.brainAndHands.badge',
    titleKey: 'strategies.brainAndHands.title',
    descriptionKey: 'strategies.brainAndHands.description',
    idealForKeys: [
      'strategies.brainAndHands.ideal1',
      'strategies.brainAndHands.ideal2',
      'strategies.brainAndHands.ideal3',
    ],
    slots: {
      brainRoleKey: 'strategies.brainAndHands.brainRole',
      brainDescKey: 'strategies.brainAndHands.brainDesc',
      handsRoleKey: 'strategies.brainAndHands.handsRole',
      handsDescKey: 'strategies.brainAndHands.handsDesc',
      fallbackRoleKey: 'strategies.brainAndHands.fallbackRole',
      fallbackDescKey: 'strategies.brainAndHands.fallbackDesc',
    },
    tokenEconomicsKey: 'strategies.brainAndHands.tokenEconomics',
    recommendedSlotLink: 'routing',
  },
  {
    id: 'moa_consensus',
    badgeKey: 'strategies.moaConsensus.badge',
    titleKey: 'strategies.moaConsensus.title',
    descriptionKey: 'strategies.moaConsensus.description',
    idealForKeys: [
      'strategies.moaConsensus.ideal1',
      'strategies.moaConsensus.ideal2',
      'strategies.moaConsensus.ideal3',
    ],
    slots: {
      brainRoleKey: 'strategies.moaConsensus.brainRole',
      brainDescKey: 'strategies.moaConsensus.brainDesc',
      handsRoleKey: 'strategies.moaConsensus.handsRole',
      handsDescKey: 'strategies.moaConsensus.handsDesc',
    },
    tokenEconomicsKey: 'strategies.moaConsensus.tokenEconomics',
    recommendedSlotLink: 'moa',
  },
  {
    id: 'split_stack_local',
    badgeKey: 'strategies.splitStackLocal.badge',
    titleKey: 'strategies.splitStackLocal.title',
    descriptionKey: 'strategies.splitStackLocal.description',
    idealForKeys: [
      'strategies.splitStackLocal.ideal1',
      'strategies.splitStackLocal.ideal2',
      'strategies.splitStackLocal.ideal3',
    ],
    slots: {
      brainRoleKey: 'strategies.splitStackLocal.brainRole',
      brainDescKey: 'strategies.splitStackLocal.brainDesc',
      handsRoleKey: 'strategies.splitStackLocal.handsRole',
      handsDescKey: 'strategies.splitStackLocal.handsDesc',
    },
    tokenEconomicsKey: 'strategies.splitStackLocal.tokenEconomics',
    recommendedSlotLink: 'base',
  },
];
