// Friendly text for each permission (mirrors backend apps/accounts/rbac.py).
export const PERMISSION_TEXT: Record<string, string> = {
  'rag.ask': 'Ask questions',
  'documents.view': 'See and open documents in your access groups',
  'feedback.create': 'Rate answers',
  'documents.upload': 'Upload documents',
  'documents.manage': 'Upload new versions of documents and delete them',
  'documents.manage_access': 'Choose which access groups may read a document',
  'jobs.view': 'See processing jobs',
  'jobs.retry': 'Retry or cancel processing jobs',
  'pipelines.view': 'See pipelines, models and settings',
  'pipelines.edit': 'Edit draft pipeline versions and settings',
  'indexes.view': 'See index generations',
  'indexes.build': 'Build and validate index generations',
  'evaluation.view': 'See evaluation runs and results',
  'evaluation.manage_datasets': 'Create and edit evaluation datasets',
  'evaluation.run': 'Start evaluation runs',
  'failures.review': 'Review failure cases',
  'releases.approve': 'Approve and publish releases; roll back index generations',
  'accounts.manage': 'Manage users, roles, access groups and sessions',
  'audit.read': 'Read the audit log',
}

// Which roles grant which permissions (mirrors backend apps/accounts/rbac.py; every account is also a User).
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  User: ['rag.ask', 'documents.view', 'feedback.create'],
  'Knowledge manager': ['documents.upload', 'documents.manage', 'documents.manage_access', 'jobs.view', 'jobs.retry'],
  'Pipeline engineer': ['pipelines.view', 'pipelines.edit', 'indexes.view', 'indexes.build', 'jobs.view', 'jobs.retry'],
  Evaluator: ['evaluation.view', 'evaluation.manage_datasets', 'evaluation.run', 'failures.review', 'pipelines.view'],
  'Release approver': ['releases.approve', 'evaluation.view', 'pipelines.view', 'indexes.view'],
  Admin: ['accounts.manage', 'audit.read'],
}

export function rolesGranting(permission: string): string[] {
  return Object.entries(ROLE_PERMISSIONS)
    .filter(([, perms]) => perms.includes(permission))
    .map(([role]) => role)
}
