# Self-service accounts on Render Free

The website supports username/password registration, sign-in, reading and updating
your own profile, changing your password, deleting your account, and signing out.
There is no public list of users or ability to edit somebody else's account.
Users do not need a `DEMO_USERS_JSON` entry in this mode.

Accounts and revocable sessions live in PostgreSQL. Uploads, SQL datasets, and AI
conversations remain temporary in Render memory. The browser connects directly to
the visitor's own Ollama only after they explicitly connect and select a model.
Groq continues using the server's existing `GROQ_API_KEY`.

## Set up the free external database

Use a new [Neon Free project](https://neon.com/docs/introduction/plans) for accounts.
Its Free plan is intended for prototypes and small teams and has usage limits;
check the current plan before selecting it. No paid resources are required by the
code or created automatically.

1. Sign up at [Neon](https://console.neon.tech/), select the **Free** plan, and
   create a project such as `business-insights-accounts`. Choose a region near your
   Render service. Use a dedicated database for this app's accounts.
2. In the project, click **Connect**. Select the intended branch, database and
   role. Keep **Connection pooling** enabled and copy the PostgreSQL connection
   string privately. Neon includes the password in that string. Do not paste it
   into chat, screenshots, GitHub, source files, or Vite variables.
3. The database role must be able to create tables and indexes in the selected
   database. The application creates `dashboard_users` and `dashboard_sessions`
   at startup using additive `CREATE ... IF NOT EXISTS` statements. Do not point
   it at somebody else's application database.

The app uses the PostgreSQL driver, not Neon's separate managed Auth product.
External database connections enforce `sslmode=verify-full` and
`sslrootcert=system`, even if the copied URL specifies a weaker SSL mode. Prepared
statements are disabled for transaction-pool compatibility, database operations
have a ten-second statement timeout, and each connection closes after its
transaction. Database errors returned to the browser omit credentials and SQL.

[Neon connection instructions](https://neon.com/docs/connect/connect-from-any-app),
[PostgreSQL certificate verification](https://www.postgresql.org/docs/current/libpq-ssl.html).

Render Free's web-service filesystem is ephemeral, so it is not used for account
storage. Free **Render Postgres** expires after 30 days; it is not the suggested
long-term account database for this setup. See
[Render Free limitations](https://render.com/docs/free).

## Configure the existing Render service

Keep the Docker service, current service URL, `/health` check, one Gunicorn
worker, `PORT`, `PUBLIC_ORIGIN`, and `GROQ_API_KEY`. On that service's Environment
page, configure:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `accounts` |
| `DATABASE_URL` | The complete private Neon PostgreSQL connection string |
| `ALLOW_REGISTRATION` | `true` to allow sign-ups, `false` to close sign-ups |
| `PUBLIC_ORIGIN` | `https://ai-business-insights-generator.onrender.com`, or the exact service origin you actually use |
| `GROQ_API_KEY` | Keep the existing server-side value |

`DEMO_USERS_JSON` is ignored in account mode. Existing demo credentials are not
automatically imported: create a new account through **Create account** after
deployment. Do not remove legacy configuration until you have tested the new flow
and decided whether you need a rollback.

The `render.yaml` template now selects account mode and asks for `DATABASE_URL`.
Editing the template alone does not update an existing manually configured
service. At the code level, the default remains `AUTH_MODE=demo` to avoid silently
changing authentication on existing deployments. Selecting `accounts` without a
valid database fails startup; it never falls back to demo authentication.

1. Review and commit `feature/self-service-accounts`, push it, and open a PR
   targeting the branch your Render service builds (currently
   `feature/render-free-deployment`, unless you changed it).
2. After the required review, merge the PR and configure the variables above on
   the existing Render service. Keep Auto-Deploy off during this transition.
3. Save the variables, then use **Manual Deploy → Deploy latest commit** so the
   new account code and configuration become active together. A **Save only**
   environment change does not take effect until deployment. Do not deploy
   `AUTH_MODE=accounts` against an old build that lacks this implementation.
4. Wait for **Live**, open the website, and click **Create account**. Choose a
   username of 3–32 letters/numbers/dots/underscores/hyphens, and a unique password
   of 16–256 characters. Usernames are normalized to lowercase.
5. Create a second account in another browser profile and complete the acceptance
   checks below before inviting others.

[Render environment settings](https://render.com/docs/configure-environment-variables),
[manual deploys](https://render.com/docs/deploys#manual-deploys).

## Use and manage an account

Open the account icon or choose **Account** in the hamburger menu beside it.
Account settings use a full page at `/#account`, with the same header and panel
design as the dashboards. You can switch pages or use browser Back without
discarding the current dataset or conversation. Saving account changes still
clears temporary data as described below.

- **Create account** registers and signs in. Display name is optional; username
  and password are required. No demo password or shared application token is used.
- **Account → Profile** shows your username/display name. Changing them requires
  your current password.
- **Account → Change password** requires the current password and confirmation
  of the new password in the UI.
- Saving either form revokes all existing sessions, signs this browser in with a
  fresh session, and reloads the dashboard. Other devices must sign in again.
  Your temporary datasets/conversations are cleared. Keep the original file.
- **Account → Sign out** revokes this browser's session, clears its temporary
  server data and reloads the sign-in screen. Other devices remain signed in.
- **Account → Delete account** requires the current password and a deliberate UI
  confirmation. It deletes the account and all its sessions and clears its
  temporary datasets, conversations and pending local-model runs.
- Account edits, deletion and logout wait until an active server upload/analysis
  finishes instead of racing against it. If the service reports busy, retry when
  that operation finishes.
- Set `ALLOW_REGISTRATION=false` to close new registrations while retaining
  existing users' sign-in and account management. Deploy the configuration change.

Sessions expire after one hour. Account records and unexpired sessions survive
app restarts because they are in PostgreSQL. Uploaded business data does not.
If an AI dataset expires, rebuild it from the original file. Dataset ownership
includes both the immutable account ID and the authenticated browser session;
another browser cannot reuse a dataset ID, even when it belongs to the same user.

## Verification

Run the complete existing suite and frontend build:

```sh
.venv/bin/python -m pip install -r requirements.txt
npm test
npm run build
```

`tests/test_accounts.py` runs with a temporary file-backed SQLite fixture by
default. To repeat the same suite against a **disposable** PostgreSQL database,
set `ACCOUNT_TEST_DATABASE_URL` privately and run:

```sh
.venv/bin/python -m unittest tests.test_accounts
```

Never use a live customer database for tests. Account test names are randomized,
and tests remove only their own synthetic users. SQLite account storage is
accepted only for loopback HTTPS development/test origins; it is rejected for
hosted sites. The original `python app.py` workflow remains local and does not
require a database or account.

Optional macOS Chrome browser checks (test-only Playwright required):

```sh
.venv/bin/python -m scripts.check_accounts_ui
.venv/bin/python -m scripts.check_dashboard_ui
```

The account check exercises registration, validation, sign-in, profile editing,
password changes, logout, deletion, a real sample dashboard, and desktop/mobile
layouts over temporary local HTTPS. It uses fictional credentials and no real
model inference. Existing dashboard/Ollama transport tests remain applicable.

Production image check with real Gunicorn under the Free service's resource
limits (the test uses loopback-only SQLite fixtures and no external network):

```sh
docker build --platform linux/amd64 -t ai-business-insights:accounts .
docker run --rm --platform linux/amd64 --network none --memory=512m --cpus=0.1 -i ai-business-insights:accounts python - < tests/accounts_container_smoke.py
```

This verifies application startup, authenticated uploads, browser-local SQL
authorization, session persistence across an actual process restart, logout and
deletion. It is a small smoke test, not a concurrency/capacity certification.

Before sharing the deployed account flow, verify:

1. Anonymous visitors see the sign-in screen; unauthenticated dashboard APIs return
   `401` without a Basic-auth browser prompt.
2. Register two accounts and upload different fictional files in separate browser
   profiles. Reusing the first account's dataset/run identifiers from the second
   browser must fail. This check must also fail between two sessions for one user.
3. Profile/password changes revoke the other session; the old password fails after
   a password change. Logout and deletion revoke their respective sessions.
4. Restart Render. Existing accounts can sign in, but old in-memory AI datasets
   require reupload. Confirm the actual Neon connection uses verified TLS.
5. Test Groq with the actual server key and explicitly connect local Ollama from
   a visitor's computer. Automated provider mocks do not verify those live
   credentials, quotas, permissions or hardware.

## Security scope and remaining limitations

Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Session cookies are
opaque, `Secure`, `HttpOnly`, host-only and `SameSite=Strict`; only their SHA-256
hashes are stored as session identifiers in the database. CSRF tokens are
session-bound and rotate at sign-in and account changes. Every unsafe request
checks the exact origin and CSRF token, including registration and login.
Credentials/tokens never enter browser localStorage/sessionStorage.

Authentication and account CRUD have process-local limits before expensive work:
3 registration attempts/minute globally, 12 sign-in attempts/minute globally,
5 sign-in attempts/minute per submitted username, and 5 account changes/minute
per user. Existing per-user upload/question limits, serialized analysis, bounded
memory caches, SQL authorizer and browser-local Ollama protections are retained.
No client-supplied user ID/role is accepted. Account SQL is parameterized, and the
business SQL analyst cannot connect to or query the account database.

This is a small-project account foundation, not a certification for unrestricted
public traffic. It has no email verification, self-service forgotten-password
recovery, MFA, CAPTCHA, admin user-management web UI, or distributed abuse
protection. Login errors are generic; registration still discloses username
availability. Process-local rate limits reset on restart and do not replace edge
protection. Provider outages, cold starts, free-plan quotas, parser/memory limits
and temporary business-data storage still apply. Review provider backup/restore
and account-recovery procedures before relying on persistent identities. Do not
open the service broadly until the deployed authentication/isolation checks and
an independent security review are complete.
