# 9ja Jobs API

FastAPI service for authentication, job listings, applications, profiles, saved jobs, employer workflows, reviews, messages, notifications, and file uploads.

## Run locally

From the project root in PowerShell:

```powershell
py -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
uvicorn app.main:app --app-dir backend --reload
```

Set the frontend's `.env.local` to `VITE_API_URL=http://localhost:8000`, then run `npm run dev` in another terminal. API documentation is available at `/docs` while the server is running.

The local default uses SQLite. For a hosted PostgreSQL database, set `DATABASE_URL` to its connection URL. Set `JWT_SECRET` to a long random secret, `FRONTEND_ORIGINS` to the exact frontend origins separated by commas, and `COOKIE_SECURE=true` when the frontend and API use HTTPS. Persist the database and `UPLOAD_DIR` between deploys. Host this API on a Python service and point Vercel's `VITE_API_URL` at it.

Uploaded resumes are private: applicants and the employer who owns the relevant job can retrieve them. Profile images are served publicly. Passwords are hashed with Argon2; session tokens are kept in HttpOnly cookies.

## Google, Apple, and GitHub sign-in

The login page supports OAuth sign-in with all three providers. Each provider must be registered and configured before its button can complete sign-in. OAuth client secrets and Apple private keys belong only in `backend/.env` locally and in the API host's secret environment settings in production. Do not add them to Vercel's `VITE_*` variables or commit them to Git.

Set these backend variables:

```env
PUBLIC_API_URL=https://your-api-host.example
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
APPLE_CLIENT_ID=
APPLE_TEAM_ID=
APPLE_KEY_ID=
APPLE_PRIVATE_KEY=
```

Register these exact callback URLs with each provider (replace the host with your API URL):

```text
https://your-api-host.example/api/auth/oauth/google/callback
https://your-api-host.example/api/auth/oauth/github/callback
https://your-api-host.example/api/auth/oauth/apple/callback
```

Google uses a Web application OAuth client. GitHub uses an OAuth App and requests only `read:user` and `user:email`. Apple uses a Services ID as `APPLE_CLIENT_ID`, associated with your website and a Sign in with Apple private key. For `APPLE_PRIVATE_KEY`, paste the `.p8` contents into one environment variable with line breaks represented as `\n`. For local testing, add the matching `http://localhost:8000/.../callback` URLs to Google and GitHub; Apple requires a registered HTTPS website domain and return URL.

OAuth-created accounts are saved in the same `users` table and linked by provider identity. A verified matching email links the provider to an existing account. The first sign-in creates an account using the role selected on the login page.

## Existing data

The API starts with an empty database. Existing Firebase users, jobs, applications, messages, and files are not copied automatically. Keep the current Firebase project and data until you have exported and imported the records you need. Users will need accounts on the new service unless their accounts are migrated.

## Production settings

Use PostgreSQL, a high-entropy `JWT_SECRET`, HTTPS, persistent private file storage, and a restricted `FRONTEND_ORIGINS` list. Back up the database and uploaded files.
