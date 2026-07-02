import type { OrgMember } from '@/services/enterprise-org';

const ORG_MCP_ADMIN_ROLES = new Set(['owner', 'admin']);

/** Whether the signed-in user may manage org-level MCP servers (matches CP require_admin). */
export function canManageOrgMcp(members: OrgMember[], userId: string | undefined): boolean {
  if (!userId) return false;
  const member = members.find((m) => m.user_id === userId);
  return member !== undefined && ORG_MCP_ADMIN_ROLES.has(member.role);
}
