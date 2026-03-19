# RFP Summarizer Frontend

React + Vite results viewer with MSAL authentication for the RFP Summarizer.

## Features

- **MSAL sign-in** via Azure AD (popup flow, `@azure/msal-react` v2)
- **Sidebar** with RFPs grouped by blob name, nested runs sorted by date
- **Tabs**: Results, Chunks (intermediate JSON), Context (`fed_context.txt`), Source PDF
- **Admin tab** (visible only to users with `RFP.Admin` role) for editing prompt templates and schemas
- **Role-based UI** -- `/api/me` provides user roles; Admin tab hidden for readers
- **Auth-aware fetch** -- all API calls include a Bearer token when deployed; no auth locally

## Run locally

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` so no auth is needed for local development. MSAL is disabled when `VITE_CLIENT_ID` is empty (see `.env.development`).

## Build for production

```bash
npm run build
```

Output goes to `dist/`. In production the static files are served by `server.js` (Express) inside an Azure Container App.

## Environment variables

Set at build time via Vite (`VITE_` prefix) or as Container App env vars:

| Variable | Purpose |
|---|---|
| `VITE_TENANT_ID` | Azure AD tenant ID |
| `VITE_CLIENT_ID` | Frontend app registration client ID |
| `VITE_API_CLIENT_ID` | Backend app registration client ID |
| `VITE_API_SCOPE` | Backend API scope (`api://<id>/access_as_user`) |
| `VITE_API_BASE_URL` | Backend URL (empty in dev, set in production) |

## Docker

The `Dockerfile` uses a multi-stage build -- `VITE_*` values are passed as `--build-arg` and baked into the static bundle at image build time.

```bash
# Built by deploy/deploy-apps.ps1 via az acr build (not locally)
az acr build --build-arg VITE_TENANT_ID=... --build-arg VITE_CLIENT_ID=... ...
```

## Deployment

All deployment scripts live in `deploy/` at the repo root. The frontend is built and deployed via `deploy/deploy-apps.ps1`, which:

1. Runs `az acr build` to build the Docker image in ACR (passing all `VITE_*` build args)
2. Updates the frontend Container App to use the new image
3. Configures CORS on the backend to accept requests from the frontend URL

## Project structure

```
├── src/
│   ├── auth/
│   │   ├── msalConfig.js     # MSAL configuration
│   │   ├── AuthGuard.jsx     # Sign-in/sign-out wrapper
│   │   └── authFetch.js      # Fetch wrapper with Bearer token
│   ├── components/
│   │   ├── AdminTab.jsx      # Prompt/schema editor (Admin only)
│   │   ├── Sidebar.jsx       # RFP/run navigation
│   │   ├── RunHeader.jsx     # Run metadata display
│   │   ├── ResultsTab.jsx    # Extracted fields cards
│   │   ├── ChunksTab.jsx     # Intermediate JSON viewer
│   │   ├── ContextTab.jsx    # Fed context text viewer
│   │   └── SourceTab.jsx     # PDF embed with auth
│   ├── hooks/
│   │   ├── useAuthFetch.js   # Generic fetch hook with auth + cancellation
│   │   ├── useRfps.js        # Fetch RFP list
│   │   ├── useRun.js         # Fetch single run details
│   │   └── useUser.js        # Fetch user roles from /api/me
│   ├── utils/
│   │   └── format.js         # Date formatting helpers
│   ├── App.jsx               # Main app shell
│   ├── main.jsx              # Entry point with MsalProvider
│   └── index.css             # Global styles
├── server.js                 # Production Express static server
├── Dockerfile                # Multi-stage build
├── .env.development          # Local dev overrides (auth disabled)
└── package.json
```
