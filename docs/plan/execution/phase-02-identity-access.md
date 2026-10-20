# Phase 2: Identity & access, and the console shell

## Goal

**Authentication.** People sign in with a password: Admins add a TOTP code, and repeated failures lock the account. Sessions are server-side and can be revoked.

**Authorization.**
- Each of the six roles has exactly its permissions.
- Admins manage users, roles, access groups and sessions.
- The React console exists with sign-in, a role-based menu, the account page and the admin pages.

This phase reaches **Milestone M1: sign-in works**.

## Before you start

- Phase 1 is done. The `users` table exists.

## Tasks

### Backend: authentication (`accounts`)
- [ ] Endpoints:
  - `auth/csrf/`, `auth/login/`, `auth/logout/`, `auth/me/`;
  - `auth/sessions/`, `auth/sessions/revoke-all/`;
  - `auth/password/`.
- [ ] Sign-in:
  - use Django's `login()`, which rotates the session key;
  - give the same error for an unknown user and a wrong password;
  - throttle at 5 attempts per minute per IP.
- [ ] Session cookies:
  - session: `HttpOnly`, `Secure`, `SameSite=Lax`;
  - CSRF cookie: readable by JavaScript;
  - `CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]` in the local settings.
- [ ] `user_sessions` rows:
  - created on sign-in (the `user_logged_in` signal), with the SHA-256 of the session key, IP and user agent;
  - `SessionGuardMiddleware` rejects revoked sessions and enforces the 30-minute idle and 8-hour absolute timeouts;
  - it updates `last_seen_at` at most once a minute.
- [ ] Lockout with django-axes: 5 failures lock the username for 15 minutes.
  - A signal handler updates `users.failed_login_count` and `locked_until`.
  - A locked account returns `423`.
- [ ] MFA with django-otp (TOTP):
  - `auth/mfa/setup/` returns a QR code (`qrcode`);
  - `auth/mfa/confirm/` and `auth/mfa/verify/`;
  - required for the Admin role; admin endpoints also check `is_verified()`.
- [ ] `python manage.py bootstrap_admin --username …` creates the first Admin: it asks for the password and prints the MFA enrolment QR code.
- [ ] Optional, only if needed: LDAP / Active Directory sign-in with `django-auth-ldap` (`auth_source = LDAP`).

### Backend: authorization (`accounts`)
- [ ] Models (`db_table` names as in the schema):
  - `Role`, `Permission`, `RolePermission`, `UserRole`;
  - `AccessGroup`, `UserAccessGroup`, `UserSession`.
- [ ] `RoleBackend` (in `AUTHENTICATION_BACKENDS`) answers `has_perm("rag.ask")` from the user's roles, cached once per request.
- [ ] A DRF permission class: `HasPerm("…")`.
- [ ] `accounts.selectors.access_scope(user)` returns the user's group names.
- [ ] Data migration `accounts 0003`: the 6 roles, the 19 permissions, the role–permission pairs and the `general` group (see [03-database.md §8](../03-database.md#8-seed-data)).
- [ ] Admin endpoints:
  - `admin/users/` (with roles, access groups, unlock, reset-mfa);
  - `admin/roles/`, `admin/access-groups/`;
  - `admin/sessions/` (with revoke).
- [ ] Safety rules:
  - the last active Admin cannot be removed or deactivated;
  - deactivating a user revokes all of their sessions.
- [ ] Audit events: sign-in, failed sign-in, lockout, sign-out, session revoked, user created or changed, role and group changes, MFA enrolled or reset.
- [ ] `access-groups/mine/`: any signed-in user can list the groups they belong to (used by the upload page).

### Console (`console/`)
- [ ] `npm create vite@latest` with the React + TypeScript template. Install the packages in [dependency.txt](../../../dependency.txt), section 7.
- [ ] `vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`.
- [ ] `api/client.ts`:
  - `credentials: "same-origin"`;
  - `X-CSRFToken` on writes;
  - 401 → `/login?next=…`; 403 → the no-permission view.
- [ ] `SessionProvider`, `RequireAuth`, `RequirePermission`, `useCan`.
- [ ] Pages:
  - Login, MFA, Account (my sessions, sign out everywhere, MFA setup);
  - Admin: users, access groups, sessions.
- [ ] Layout with a menu built from the user's permissions ([02-frontend.md §3](../02-frontend.md#3-pages)), and a light and dark theme.

### Tests
- [ ] Sign-in:
  - success; wrong password; unknown user (same message);
  - locked after 5 failures, then unlocked by an Admin;
  - an Admin without MFA cannot reach admin endpoints.
- [ ] Sessions:
  - a revoked session gets `401` on its next request;
  - the idle timeout and the absolute timeout work;
  - a write without `X-CSRFToken` gets `403 csrf_failed`.
- [ ] Each role's permission set exactly matches the role table.
- [ ] Every admin endpoint returns 403 for a non-Admin.
- [ ] Console:
  - `RequirePermission` shows the right menu for each of the six roles;
  - a 401 redirects to the login page.

## Done when

- [ ] One test account per role can sign in, and each sees only its menu.
- [ ] Calling a forbidden endpoint directly (with `curl` and a valid session) returns `403`.
- [ ] Revoking a session in the admin page signs that browser out on its next request.
- [ ] The audit log has rows for every sign-in and admin change made during testing.

## Risks and tips

- **Never trust the menu.** Hiding a button is only for convenience. The API test for every endpoint is what protects data.
- Browsers accept `Secure` cookies on `http://localhost`. If you open the console through a different host name, the cookie will not be sent; use `localhost`.
