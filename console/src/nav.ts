export type NavItem = { to: string; label: string; perm?: string; section: 'main' | 'admin' }

// Each phase adds its pages here (docs/plan/02-frontend.md §3).
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', section: 'main' },
  { to: '/chat', label: 'Chat', perm: 'rag.ask', section: 'main' },
  { to: '/documents', label: 'Documents', perm: 'documents.view', section: 'main' },
  { to: '/documents/upload', label: 'Upload', perm: 'documents.upload', section: 'main' },
  { to: '/pipelines', label: 'Pipelines', perm: 'pipelines.view', section: 'main' },
  { to: '/indexes', label: 'Indexes', perm: 'indexes.view', section: 'main' },
  { to: '/evaluation', label: 'Evaluation', perm: 'evaluation.view', section: 'main' },
  { to: '/evaluation/datasets', label: 'Datasets', perm: 'evaluation.manage_datasets', section: 'main' },
  { to: '/evaluation/failures', label: 'Failures', perm: 'failures.review', section: 'main' },
  { to: '/admin/users', label: 'Users', perm: 'accounts.manage', section: 'admin' },
  { to: '/admin/roles', label: 'Roles', perm: 'accounts.manage', section: 'admin' },
  { to: '/admin/access-groups', label: 'Access groups', perm: 'accounts.manage', section: 'admin' },
  { to: '/admin/sessions', label: 'Sessions', perm: 'accounts.manage', section: 'admin' },
  { to: '/admin/audit', label: 'Audit log', perm: 'audit.read', section: 'admin' },
]

/** The menu for a user: only the items their permissions allow. */
export function visibleNav(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.perm || permissions.includes(item.perm))
}
