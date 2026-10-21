import { describe, expect, it } from 'vitest'
import { visibleNav } from './nav'

// Permission sets of the six roles (backend apps/accounts/rbac.py); every account also has User.
const USER = ['rag.ask', 'documents.view', 'feedback.create']
const ROLES: Record<string, string[]> = {
  User: USER,
  'Knowledge manager': [...USER, 'documents.upload', 'documents.manage', 'documents.manage_access', 'jobs.view', 'jobs.retry'],
  'Pipeline engineer': [...USER, 'pipelines.view', 'pipelines.edit', 'indexes.view', 'indexes.build', 'jobs.view', 'jobs.retry'],
  Evaluator: [...USER, 'evaluation.view', 'evaluation.manage_datasets', 'evaluation.run', 'failures.review', 'pipelines.view'],
  'Release approver': [...USER, 'releases.approve', 'evaluation.view', 'pipelines.view', 'indexes.view'],
  Admin: [...USER, 'accounts.manage', 'audit.read'],
}

describe('visibleNav', () => {
  it.each(Object.entries(ROLES))('%s sees admin pages only when they may manage accounts', (role, perms) => {
    const labels = visibleNav(perms).map((item) => item.label)
    expect(labels).toContain('Home')
    if (role === 'Admin') expect(labels).toEqual(expect.arrayContaining(['Users', 'Access groups', 'Sessions']))
    else expect(labels).not.toContain('Users')
  })
})
