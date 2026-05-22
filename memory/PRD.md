# StaffHub / FleetWash — Migration PRD

## Original problem statement
Migrate the existing Expo + FastAPI + MongoDB **StaffHub / FleetWash** app from
GitHub (`https://github.com/Clok2410/APP-Fleetwash`) into this Emergent pod:
1. Clone repo
2. Verify FastAPI backend boots and connects to MongoDB
3. Verify Expo frontend builds for web (`app.json` already has `web.output: "static"`)
4. Serve Expo web as the public preview URL
5. Use production env vars when deploying (vars NOT yet supplied by user)

Constraints: app must stay cross-platform (web + iOS + Android); **do NOT wipe the
production Mongo database**.

## Migration completed (this session — 2026-05-22)
- Cloned `Clok2410/APP-Fleetwash` → moved into `/app` (preserving pod `.git`/`.emergent`)
- Created safe **local-dev** envs:
  - `backend/.env`: `MONGO_URL=mongodb://localhost:27017`, `DB_NAME=staffhub`,
    auto-generated `JWT_SECRET`, `EMERGENT_LLM_KEY`, `CORS_ORIGINS="*"`
  - `frontend/.env`: `EXPO_PUBLIC_BACKEND_URL` + `REACT_APP_BACKEND_URL` both pointing
    at the preview URL (`api.ts` reads `EXPO_PUBLIC_BACKEND_URL`)
- Installed backend deps from `requirements.txt` (FastAPI, Motor, bcrypt, PyJWT,
  ReportLab, APScheduler, Resend, pypdf, emergentintegrations, etc.)
- Ran `yarn install` in `/app/frontend` → Expo SDK 54 + Expo Router + react-native-web
- Changed `frontend/package.json` `start` script from `expo start` to
  `expo start --web --port 3000 --host lan` so the pod supervisor's `yarn start`
  contract launches Metro web bundler on port 3000.
- `sudo supervisorctl restart backend frontend` → both services RUNNING
- APScheduler started (weekly digest Mon 09:00 UTC + HR expiry sweep daily 06:00 UTC)
- Auto-seeded demo accounts (idempotent — won't overwrite existing prod users):
  - `admin@company.com / Admin@123` (admin)
  - `jane@company.com / Staff@123` (staff)

## Verification done
- `GET /api/auth/me` without token → 401 (auth gate active)
- `POST /api/auth/login` admin via **public URL** → 200, JWT returned
- `GET /api/auth/me` with token → admin user payload
- `GET /api/users` → 2 seeded users listed
- Public URL renders Expo-Router StaffHub login page (screenshot verified)

## App architecture (from repo)
**Backend** (`/app/backend`, FastAPI + Motor)
- `server.py` (~1700 lines) — auth, clock in/out + geofencing, holidays, shifts,
  roster LLM parser, drive (base64 files), form templates + checklists + AI summary,
  PDF form sessions, notifications, weekly digest scheduler, HR docs (DocuSign-replacement)
- `deps.py` — DB, JWT, password hashing, helpers
- `routers/customers.py`, `routers/holidays.py`, `routers/hr.py` — modular routers

**Frontend** (`/app/frontend`, Expo SDK 54)
- Expo Router (`app/_layout.tsx`, `app/index.tsx`, `app/admin.tsx`, `app/(tabs)/…`)
- `src/api.ts` axios client with AsyncStorage JWT
- `src/auth.tsx` auth provider
- Components for scheduler, drag-and-drop roster, PDF form filler, signature canvas
- Cross-platform: works on web (`react-native-web`), iOS, Android

## Tech stack
- FastAPI 0.110, Motor 3.3, MongoDB 7
- Expo SDK 54, React Native 0.81, React 19, Expo Router 6
- emergentintegrations (Claude Sonnet 4.5 for roster parsing + form summaries)
- Resend (email digests — MOCKED until `RESEND_API_KEY` set)
- APScheduler (weekly digest + HR expiry sweeps)

## Outstanding for production deploy
**P0 (must do before going to real users):**
- [ ] Replace `MONGO_URL` with production Atlas string (user has not supplied)
- [ ] Replace `DB_NAME` with production DB name
- [ ] Rotate `JWT_SECRET` to a deploy-only secret
- [ ] Configure Emergent deploy with the above as production env vars (NOT in `.env`)

**P1:**
- [ ] Set `RESEND_API_KEY` to enable real email digests (currently MOCKED — logs
      `[MOCKED EMAIL]`)
- [ ] Run `cd /app/frontend && expo export -p web` to produce a static build at
      `/app/frontend/dist`, then either:
      - (a) serve via FastAPI static mount, or
      - (b) keep current `expo start --web` (dev server is fine for preview but a
        static build is recommended for production performance)
- [ ] EAS build configs for iOS/Android if you want native binaries

**P2:**
- [ ] Push notifications (FCM/APNs) wiring already scaffolded in `src/push.ts`

## Smart enhancement
The roster LLM parser (Claude Sonnet 4.5) already turns a messy Google-Sheets PDF roster
into structured rows for the admin to publish. Worth surfacing this as a one-click
"Import from PDF" CTA on the Scheduler dashboard — saves managers ~30 min/week and is
a great upsell hook for the SaaS tier.
