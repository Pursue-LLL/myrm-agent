import { describe, expect, it } from 'vitest';

import { canManageOrgMcp } from '../orgMcpAccess';
import type { OrgMember } from '@/services/enterprise-org';

describe('canManageOrgMcp', () => {
  const members: OrgMember[] = [
    { user_id: 'owner-1', role: 'owner', idp_groups: null, joined_at: 1 },
    { user_id: 'admin-1', role: 'admin', idp_groups: null, joined_at: 2 },
    { user_id: 'member-1', role: 'member', idp_groups: null, joined_at: 3 },
  ];

  it('allows owner and admin', () => {
    expect(canManageOrgMcp(members, 'owner-1')).toBe(true);
    expect(canManageOrgMcp(members, 'admin-1')).toBe(true);
  });

  it('denies member and unknown users', () => {
    expect(canManageOrgMcp(members, 'member-1')).toBe(false);
    expect(canManageOrgMcp(members, 'unknown')).toBe(false);
    expect(canManageOrgMcp(members, undefined)).toBe(false);
  });

  it('denies when members list is empty', () => {
    expect(canManageOrgMcp([], 'owner-1')).toBe(false);
  });
});
