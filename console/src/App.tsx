import { Link, Route, Routes } from 'react-router'
import { RequireAuth } from './auth/RequireAuth'
import { RequirePermission } from './auth/RequirePermission'
import { Layout } from './components/Layout'
import AccessGroupsPage from './features/admin/AccessGroupsPage'
import AuditLogPage from './features/admin/AuditLogPage'
import RolesPage from './features/admin/RolesPage'
import SessionsPage from './features/admin/SessionsPage'
import UsersPage from './features/admin/UsersPage'
import AccountPage from './features/auth/AccountPage'
import ChatPage from './features/chat/ChatPage'
import LoginPage from './features/auth/LoginPage'
import MfaPage from './features/auth/MfaPage'
import DocumentDetailPage from './features/documents/DocumentDetailPage'
import DocumentsPage from './features/documents/DocumentsPage'
import UploadPage from './features/documents/UploadPage'
import DatasetsPage from './features/evaluation/DatasetsPage'
import EvaluationPage from './features/evaluation/EvaluationPage'
import FailuresPage from './features/evaluation/FailuresPage'
import RunDetailPage from './features/evaluation/RunDetailPage'
import HomePage from './features/home/HomePage'
import IndexesPage from './features/indexes/IndexesPage'
import PipelinesPage from './features/pipelines/PipelinesPage'
import VersionPage from './features/pipelines/VersionPage'

function NotFound() {
  return (
    <section className="panel">
      <h1>Not found</h1>
      <p className="muted">
        This page does not exist, or you cannot open it. <Link to="/">Go home</Link>
      </p>
    </section>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/mfa" element={<MfaPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="chat" element={<RequirePermission perm="rag.ask"><ChatPage /></RequirePermission>} />
        <Route path="documents" element={<RequirePermission perm="documents.view"><DocumentsPage /></RequirePermission>} />
        <Route path="documents/upload" element={<RequirePermission perm="documents.upload"><UploadPage /></RequirePermission>} />
        <Route path="documents/:documentId" element={<RequirePermission perm="documents.view"><DocumentDetailPage /></RequirePermission>} />
        <Route path="indexes" element={<RequirePermission perm="indexes.view"><IndexesPage /></RequirePermission>} />
        <Route path="evaluation" element={<RequirePermission perm="evaluation.view"><EvaluationPage /></RequirePermission>} />
        <Route path="evaluation/runs/:runId" element={<RequirePermission perm="evaluation.view"><RunDetailPage /></RequirePermission>} />
        <Route path="evaluation/datasets" element={<RequirePermission perm="evaluation.manage_datasets"><DatasetsPage /></RequirePermission>} />
        <Route path="evaluation/failures" element={<RequirePermission perm="failures.review"><FailuresPage /></RequirePermission>} />
        <Route path="admin/roles" element={<RequirePermission perm="accounts.manage"><RolesPage /></RequirePermission>} />
        <Route path="admin/audit" element={<RequirePermission perm="audit.read"><AuditLogPage /></RequirePermission>} />
        <Route path="pipelines" element={<RequirePermission perm="pipelines.view"><PipelinesPage /></RequirePermission>} />
        <Route path="pipelines/:pipelineId/versions/:versionId" element={<RequirePermission perm="pipelines.view"><VersionPage /></RequirePermission>} />
        <Route path="admin/users" element={<RequirePermission perm="accounts.manage"><UsersPage /></RequirePermission>} />
        <Route path="admin/access-groups" element={<RequirePermission perm="accounts.manage"><AccessGroupsPage /></RequirePermission>} />
        <Route path="admin/sessions" element={<RequirePermission perm="accounts.manage"><SessionsPage /></RequirePermission>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
