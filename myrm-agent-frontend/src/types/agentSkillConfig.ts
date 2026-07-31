/** Per-skill configuration stored on Agent profile (server SSOT). */
export type AgentSkillConfig = {
  is_core?: boolean;
  instance_name?: string | null;
};

export type AgentSkillConfigMap = Record<string, AgentSkillConfig>;
