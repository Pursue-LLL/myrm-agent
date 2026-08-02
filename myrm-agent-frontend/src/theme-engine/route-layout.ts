const WORK_DENSE_PREFIXES = [
  '/kanban',
  '/settings',
  '/memory',
  '/approvals',
  '/eval-lab',
  '/projects',
] as const;

export function resolveLayoutFromPathname(
  pathname: string,
  profileLayoutId: import('./schema').ThemeLayoutId,
): import('./schema').ThemeLayoutId {
  const normalized = pathname.split('?')[0] ?? pathname;
  if (WORK_DENSE_PREFIXES.some((prefix) => normalized.startsWith(prefix))) {
    return 'work-dense';
  }
  return profileLayoutId;
}
