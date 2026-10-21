import type { OrganizePlanDto, OrganizePlanItemDto } from '@/services/organizeTypes';

export function isOrganizePlanArtifact(filename: string): boolean {
  return filename.endsWith('.organize-plan.json');
}

export function parseOrganizePlan(content: string): OrganizePlanDto | null {
  try {
    const raw = JSON.parse(content) as OrganizePlanDto;
    if (raw.version !== 1 || !Array.isArray(raw.items) || !raw.scope_root) {
      return null;
    }
    return raw;
  } catch {
    return null;
  }
}

export function updateOrganizePlanItem(
  plan: OrganizePlanDto,
  index: number,
  patch: Partial<OrganizePlanItemDto>,
): OrganizePlanDto {
  const items = plan.items.map((item, i) => (i === index ? { ...item, ...patch } : item));
  return { ...plan, items };
}

export function removeOrganizePlanItem(plan: OrganizePlanDto, index: number): OrganizePlanDto {
  return { ...plan, items: plan.items.filter((_, i) => i !== index) };
}

export function serializeOrganizePlan(plan: OrganizePlanDto): string {
  return JSON.stringify(plan, null, 2);
}
