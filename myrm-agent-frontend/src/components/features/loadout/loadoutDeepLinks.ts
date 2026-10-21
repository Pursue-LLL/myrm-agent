/** [OUTPUT] loadoutDeepLinks: Settings URL helpers for agent loadout and team assets navigation. [POS] Deep-link SSOT for loadout module routes. */

export function agentSettingsHref(agentId: string): string {
  return `/settings/agents?agentId=${encodeURIComponent(agentId)}#loadout`;
}

export function agentWikiHref(agentId: string): string {
  return `/settings/wiki?agentId=${encodeURIComponent(agentId)}`;
}

export function teamAssetsHubHref(): string {
  return '/settings/memory?sub=team-hub';
}

/** In-page anchor on Agent Capabilities tab — scrolls to Shared Context binding section. */
export function agentSharedContextBindingAnchor(): string {
  return '#shared-context-binding';
}

export function skillsSettingsHref(): string {
  return '/settings/skills';
}

export function memoryExplorerHref(): string {
  return '/settings/memory';
}
