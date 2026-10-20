# 02 · Frontend — the React console

The frontend is one React single-page app in `console/`. People use it to:

- sign in;
- ask questions and read cited answers;
- upload and manage documents;
- configure pipelines;
- run evaluations;
- administer users.

It only **displays** what the server allows. Every permission is enforced again by the backend ([01-backend.md](01-backend.md#22-accounts)).

## 1. Stack

The versions are in [dependency.txt](../../dependency.txt), section 7. Use Node.js 24 LTS (`nvm install 24`).

| Package | Used for |
|---|---|
| React 19 + React DOM | UI |
| Vite 8 + `@vitejs/plugin-react` | dev server, proxy to the API, production build |
| TypeScript 7 | types for every API response |
| React Router 8 | pages and route guards |
| TanStack Query 5 | API calls, caching, loading and error states, polling |
| react-markdown + rehype-sanitize | showing answers safely (no raw HTML) |
| Vitest + jsdom + Testing Library | unit and component tests |
| ESLint | linting |

We use no UI component library and no chart library. A small set of shared components and plain CSS (CSS variables, light and dark themes) keeps the bundle small and the machine fast.

## 2. Folder structure

```
console/
├── package.json
├── vite.config.ts            # dev proxy: /api → http://127.0.0.1:8000
├── tsconfig.json
├── eslint.config.js
├── index.html
├── .env.example              # VITE_API_BASE=/api/v1
├── public/
└── src/
    ├── main.tsx              # React root, QueryClient, Router
    ├── App.tsx               # layout + route table
    ├── routes.tsx            # every route with its required permission
    ├── api/
    │   ├── client.ts         # apiFetch: same-origin cookies, X-CSRFToken, error mapping
    │   ├── types.ts          # response types (checked against /api/schema/)
    │   ├── auth.ts           # one file per backend app …
    │   ├── documents.ts
    │   ├── jobs.ts
    │   ├── pipelines.ts
    │   ├── indexes.ts
    │   ├── retrieval.ts      # ask() stream reader, runs, feedback, chunks
    │   ├── evaluation.ts
    │   └── admin.ts
    ├── auth/
    │   ├── SessionProvider.tsx   # loads /auth/me/, exposes user, roles, permissions
    │   ├── RequireAuth.tsx       # not signed in → /login?next=…
    │   ├── RequirePermission.tsx # hides a route or button (display only)
    │   └── useCan.ts             # can("documents.upload")
    ├── features/
    │   ├── auth/             # LoginPage, MfaPage, AccountPage (my sessions, MFA setup)
    │   ├── chat/             # ChatPage, AnswerView, CitationPanel, FeedbackForm, HistoryList
    │   ├── documents/        # DocumentsPage, UploadPage, DocumentDetailPage, AccessGroupPicker
    │   ├── jobs/             # JobTimeline, StepRunList, RetryButton
    │   ├── pipelines/        # PipelinesPage, VersionPage, StepEditor, SettingsEditor
    │   ├── indexes/          # IndexesPage, GenerationDetail, ValidationList
    │   ├── evaluation/       # DatasetsPage, CasesEditor, RunsPage, RunDetail, FailureCasesPage, ApprovalPanel
    │   └── admin/            # UsersPage, UserDetail, RolesPage, AccessGroupsPage, SessionsPage, AuditLogPage
    ├── components/           # Layout, Nav, DataTable, StatusBadge, EmptyState, ErrorView, ConfirmDialog, JsonEditor, Pagination, Toast
    ├── lib/                  # sse.ts (stream parser), format.ts (dates, sizes), csrf.ts
    └── styles/               # tokens.css (colours, light/dark), base.css, layout.css
```

Tests sit next to the code as `*.test.tsx`.

## 3. Pages

| Path | Page | Who sees it (permission) | Main API calls | Architecture module |
|---|---|---|---|---|
| `/login` | Sign in | everyone | `GET /auth/csrf/`, `POST /auth/login/` | Sign-in & Session |
| `/login/mfa` | Enter the 6-digit code | after a sign-in that needs MFA | `POST /auth/mfa/verify/` | Sign-in & Session |
| `/` → `/chat` | Ask a question; streamed answer; citations; abstentions; feedback; my history | `rag.ask` | `POST /ask/` (stream), `GET /runs/`, `GET /chunks/{id}/`, `POST /answers/{id}/feedback/` | RAG Chat & Citations |
| `/documents` | Document list: status, version, access groups, filters | `documents.view` | `GET /documents/` | Document Management |
| `/documents/upload` | Drag and drop, progress, choose access groups, duplicate message | `documents.upload` | `POST /documents/`, `GET /access-groups/mine/` | File Upload |
| `/documents/:id` | Versions, status timeline, job steps, retry, access groups, download, delete | `documents.view` (job steps need `jobs.view`; actions need `documents.manage`, `documents.manage_access`, `jobs.retry`) | `GET /documents/{id}/`, `GET /jobs/?document=`, `PUT /documents/{id}/access/` | Document Management |
| `/pipelines` | Pipelines and their versions | `pipelines.view` | `GET /pipelines/` | Pipeline Configuration |
| `/pipelines/:id/versions/:v` | Steps, models, retrieval and generation settings; edit a draft; clone | `pipelines.view` (edit needs `pipelines.edit`) | `GET/PATCH /pipeline-versions/{id}/`, `POST …/clone/` | Pipeline Configuration |
| `/indexes` | Index generations, counts, validations; build; roll back | `indexes.view` (build: `indexes.build`; roll back: `releases.approve`) | `GET/POST /index-generations/` | (indexes) |
| `/evaluation` | Runs compared with the baseline | `evaluation.view` | `GET /eval/runs/` | Evaluation Dashboard |
| `/evaluation/datasets` | Datasets and cases; import from CSV or JSON | `evaluation.manage_datasets` | `GET/POST /eval/datasets/` | Evaluation Dashboard |
| `/evaluation/runs/:id` | Metric table, failed cases, gate result, **Approve** | `evaluation.view` (approve: `releases.approve`) | `GET /eval/runs/{id}/`, `POST …/approve/` | Evaluation Dashboard |
| `/evaluation/failures` | Failure cases: open → in review → resolved | `failures.review` | `GET/PATCH /failure-cases/` | Evaluation Dashboard |
| `/admin/users` | Users: create, deactivate, unlock, roles, access groups | `accounts.manage` | `/admin/users/…` | Sign-in & Session |
| `/admin/access-groups` | Access groups and their members | `accounts.manage` | `/admin/access-groups/…` | Sign-in & Session |
| `/admin/sessions` | Active sessions; revoke | `accounts.manage` | `/admin/sessions/…` | Sign-in & Session |
| `/admin/audit` | Audit log with filters | `audit.read` | `GET /audit-events/` | — |
| `/account` | My profile, my sessions, set up MFA, sign out everywhere | signed in | `/auth/me/`, `/auth/sessions/` | Sign-in & Session |
| `*` | Not found / no permission | everyone | — | — |

**Menu by role:** the left menu is built from the user's permissions, so each role sees only its own pages. Every account has the User role, so **Chat** and **Documents** (a read-only list of documents in your access groups) appear for everyone. Each other role adds its own pages:

| Role | Adds to the menu |
|---|---|
| User | — (Chat · Documents) |
| Knowledge manager | Upload; edit, version and delete actions on documents |
| Pipeline engineer | Pipelines · Indexes |
| Evaluator | Evaluation · Datasets · Failures |
| Release approver | Evaluation · Pipelines · Indexes (approve and roll back) |
| Admin | Users · Access groups · Sessions · Audit log |

## 4. Signing in and staying safe

- **Cookies:**
  - **The session cookie is `HttpOnly`.** JavaScript never sees it, and no token is stored in `localStorage` or `sessionStorage`.
  - **CSRF:** on start the console calls `GET /api/v1/auth/csrf/`, which sets the `csrftoken` cookie. `apiFetch` reads it and sends `X-CSRFToken` on every POST, PUT, PATCH and DELETE.
- **Same origin:** every call uses `credentials: "same-origin"`, and the console and API share one origin. In development the browser talks only to Vite (`localhost:5173`), and Vite forwards `/api` to Django.
- **Errors:**

  | Response | What the console does |
  |---|---|
  | `401` | Clear the cached data and go to `/login?next=<current path>` |
  | `403` | Show "You don't have permission for this" |
  | `429` | Show "Too many requests — try again in a minute" |
  | `404` | Show "Not found" (also for documents outside your access groups) |

- **Permissions in the UI are hints only:**
  - `/auth/me/` returns the user, roles, permission codenames and access groups.
  - `RequirePermission` and `useCan()` hide pages and buttons the user cannot use.
  - The backend still checks every call.
- **Rendering:**
  - Answers are rendered with `react-markdown` + `rehype-sanitize`: no raw HTML, no images, and links only to the citation viewer.
  - `dangerouslySetInnerHTML` is never used.
- **Sign-out:** `POST /auth/logout/`, then clear the TanStack Query cache.
  - "Sign out everywhere" revokes all of the user's sessions.

## 5. How the chat page works

1. The user types a question (at most 2,000 characters) and presses **Ask**.
2. `api/retrieval.ts → ask()` sends `POST /api/v1/ask/` and reads the response body as a stream (`fetch` + `ReadableStream`, parsed by `lib/sse.ts`).
   - `EventSource` is not used, because it cannot send a POST body or the CSRF header.
3. Stream events and what the screen shows:

   | Event | Screen |
   |---|---|
   | `status` (`searching`, `reranking`, `writing`) | a progress line, because answers take 20–60 s on this CPU |
   | `token` | draft text, greyed, labelled "checking sources…" |
   | `done` | the validated final answer, with numbered citation chips |
   | `abstain` | "I could not find this in the documents you can access", and any clarifying question |
   | `error` | a short message and a **Try again** button |

4. **Citations:** clicking a chip opens `CitationPanel`, which calls `GET /chunks/{id}/` for the chunk text, document name, page and section, plus a download link when the user may open the file.
5. **Feedback:** 1–5 stars and an optional comment under each answer.
6. **History:** the user's own earlier questions (`GET /runs/?mine=1`).

## 6. How uploads work

- `UploadPage` uses `XMLHttpRequest` for the upload so it can show **progress** (`fetch` has no upload progress events).
- `AccessGroupPicker` lists only the groups the user may assign (`GET /access-groups/mine/`). At least one must be chosen.
- After upload, the page goes to `/documents/:id`. While the status is `QUEUED`, `PROCESSING`, `INDEXING` or `VALIDATING_INDEX`, the page polls every 3 seconds (TanStack Query `refetchInterval`) and stops polling at `PUBLISHED` or `FAILED`.
- A duplicate shows: "This file is already uploaded as *name* (status)", with a link to it.

## 7. Shared UI pieces

- **`StatusBadge`:** one colour per lifecycle status (the same names as [03-database.md](03-database.md#4-status-values)).
- **`DataTable`:** server-side pagination, sorting and filters through URL query parameters, so a filtered view can be bookmarked.
- **`JsonEditor`:** a text area with JSON syntax checking, used for pipeline step settings. The server's validation errors are shown next to the field.
- **`ConfirmDialog`:** for delete, revoke, publish and approve. It shows exactly what will happen.
- **Layout:** works from 390 px (phone) to 1440 px+ (desktop); light and dark themes follow the system setting.

## 8. Build and serve

| Mode | Command (from `console/`) | Where it runs |
|---|---|---|
| Develop | `npm run dev` | `http://localhost:5173`; `/api` is forwarded to `127.0.0.1:8000` |
| Test | `npm test` (Vitest) · `npm run lint` · `npx tsc --noEmit` | — |
| Daily use | `npm run build` → `console/dist/` | Django serves `dist/` at `/` and the API at `/api/`, on one origin, `127.0.0.1:8000` |

To serve `dist/` in daily use, Phase 9 adds `whitenoise` to [requirements.txt](../../requirements.txt), plus a catch-all view that returns `index.html` for client routes such as `/documents/123`.

## 9. What to test

- `apiFetch`:
  - adds `X-CSRFToken` to writes;
  - a 401 leads to `/login`;
  - a 403 shows the no-permission message.
- `RequirePermission` hides routes and buttons for each of the six roles.
- `lib/sse.ts` parses every event type, including events split across network chunks.
- `AnswerView`:
  - a draft is never shown as final;
  - an `abstain` event replaces the draft;
  - sanitized markdown drops `<script>`, images and outside links.
- `UploadPage`: progress, the duplicate message, and "choose at least one access group".
- Before each phase is marked done, check every page in a real browser (Playwright screenshots at 1440 px and 390 px wide).
