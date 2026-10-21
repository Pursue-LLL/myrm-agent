import { describe, it, expect } from 'vitest';
import {
  BUILT_IN_TEMPLATE_BOTS,
  BUILT_IN_TEAM_ROSTERS,
  filterTemplateBots,
  getTemplateBotById,
  getTeamRosterById,
} from '../templateBotCatalog';

describe('templateBotCatalog', () => {
  it('预置岗位智能体库结构完备且包含所有核心岗位', () => {
    expect(BUILT_IN_TEMPLATE_BOTS.length).toBeGreaterThanOrEqual(6);

    const botIds = BUILT_IN_TEMPLATE_BOTS.map((b) => b.id);
    expect(botIds).toContain('bot-chief-of-staff');
    expect(botIds).toContain('bot-senior-architect');
    expect(botIds).toContain('bot-fullstack-engineer');
    expect(botIds).toContain('bot-market-researcher');
    expect(botIds).toContain('bot-financial-analyst');
    expect(botIds).toContain('bot-qa-director');

    for (const bot of BUILT_IN_TEMPLATE_BOTS) {
      expect(bot.name).toBeDefined();
      expect(bot.category).toBeDefined();
      expect(bot.avatarBadge).toBeDefined();
      expect(bot.recommendedSkillIds.length).toBeGreaterThan(0);
      expect(bot.defaultTools.length).toBeGreaterThan(0);
      expect(bot.maxContextTokens).toBeGreaterThan(0);
    }
  });

  it('预置团队模板包含合理拓扑与角色配置', () => {
    expect(BUILT_IN_TEAM_ROSTERS).toHaveLength(3);

    const strikeSquad = BUILT_IN_TEAM_ROSTERS.find(
      (r) => r.teamId === 'team-tech-delivery'
    );
    expect(strikeSquad).toBeDefined();
    expect(strikeSquad?.collaborationTopology).toBe('hierarchical');
    expect(strikeSquad?.roles.length).toBe(4);

    const opsShield = BUILT_IN_TEAM_ROSTERS.find(
      (r) => r.teamId === 'team-ops-shield'
    );
    expect(opsShield?.collaborationTopology).toBe('peer_swarm');
  });

  it('根据分类与关键词准确过滤岗位智能体', () => {
    // 仅按分类
    const engineeringBots = filterTemplateBots('engineering');
    expect(engineeringBots.every((b) => b.category === 'engineering')).toBe(
      true
    );
    expect(engineeringBots.length).toBe(2);

    // 仅按关键词
    const searchArchitect = filterTemplateBots(undefined, '架构师');
    expect(searchArchitect).toHaveLength(1);
    expect(searchArchitect[0].id).toBe('bot-senior-architect');

    // 组合过滤
    const combined = filterTemplateBots('management', '幕僚长');
    expect(combined).toHaveLength(1);
    expect(combined[0].id).toBe('bot-chief-of-staff');

    // 不匹配关键词返回空
    const noMatch = filterTemplateBots(undefined, 'non_existent_role_xyz');
    expect(noMatch).toHaveLength(0);
  });

  it('根据 ID 正确获取岗位角色与团队模板', () => {
    expect(getTemplateBotById('bot-chief-of-staff')?.category).toBe(
      'management'
    );
    expect(getTemplateBotById('unknown-id')).toBeNull();

    expect(getTeamRosterById('team-market-intel')?.collaborationTopology).toBe(
      'pipeline'
    );
    expect(getTeamRosterById('unknown-team')).toBeNull();
  });
});
