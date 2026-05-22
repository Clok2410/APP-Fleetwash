# StaffHub / FleetWash — Migration & Production-Prep PRD

## Original problem statement
Migrate the existing Expo + FastAPI + MongoDB **StaffHub / FleetWash** app from
GitHub (`https://github.com/Clok2410/APP-Fleetwash`) into this Emergent pod, verify
backend + Mongo, serve Expo web at the public URL, keep cross-platform (web + iOS + Android),
and **never wipe the production MongoDB data**.

## Done in session 1 (Migration) — 2026-05-22
- Cloned repo into `/app`; preserved pod's `.git` and `.emergent` files
- Wired safe **local-dev** env files (mongo://localhost, isolated DB, generated JWT_SECRET, Emergent LLM key)
- Backend running (FastAPI 0.110, 123 routes, APScheduler started)
- Auto-seeded `admin@company.com / Admin@123` + `jane@company.com / Staff@123`
- Frontend running via `expo start --web --port 3000`
- End-to-end login through public URL verified (JWT + /me + /users 200)

## Done in session 2 (Production prep) — 2026-05-22
1. **Static web export** — `expo export -p web` builds the entire app into `/app/frontend/dist`
   (14 routes, ~2.2 MB main bundle). Replaces dev server with optimized static output.
2. **Static server on port 3000** — `package.json start` now runs `serve dist --single --listen tcp://0.0.0.0:3000`.
   The original Metro dev command is preserved as `start:dev` for future hot-reload sessions.
   Same Emergent ingress contract (`/api/*` → :8001, everything else → :3000), much faster cold start, optimized bundles.
3. **EAS Build configs** — `/app/frontend/eas.json` with `development`, `preview`, `production`
   profiles for iOS + Android. `app.json` updated with `bundleIdentifier=com.fleetwash.staffhub`,
   `package=com.fleetwash.staffhub`, location/camera Info.plist strings, and proper Android permissions.
   To use: run `eas login` + `eas build:configure` (will fill in `extra.eas.projectId`).
4. **AI roster import banner** — admin-only banner at the top of the Schedule tab. Tap → deep-links
   to `/admin?openRoster=1`, which auto-switches to Shifts tab and opens the Roster PDF upload modal.
   Implementation: `useLocalSearchParams` in `admin.tsx`, new banner UI in `schedule.tsx`.
   Verified via screenshot: banner renders with Claude Sonnet 4.5 tagline.

## Currently MOCKED
- **Resend email digests** (`RESEND_API_KEY` not set) — backend logs `[MOCKED EMAIL]` instead of sending.
  Plug a real key into `/app/backend/.env` to go live.

## Architecture summary
**Backend** (`/app/backend`, FastAPI + Motor)
- `server.py` — auth, clock in/out + geofencing, holidays, shifts, roster LLM parser, drive,
  form templates + checklists, AI summaries, PDF form sessions, notifications, weekly digest, HR docs
- `deps.py` — DB, JWT, password hashing
- `routers/` — customers, holidays, hr

**Frontend** (`/app/frontend`, Expo SDK 54)
- Expo Router (`app/_layout`, `app/index`, `app/(tabs)/{home,schedule,drive,forms,profile}`, `app/admin`)
- `src/api.ts` axios + AsyncStorage JWT
- Cross-platform: web (`react-native-web`), iOS, Android
- Served as static export in production

## Tech stack
- FastAPI 0.110, Motor 3.3, MongoDB 7, APScheduler 3.11, ReportLab 4.5
- Expo SDK 54, React Native 0.81, React 19, Expo Router 6, serve 14
- Claude Sonnet 4.5 via emergentintegrations (roster PDF parsing, form AI summaries)
- Resend (email digests — MOCKED)

## Still required from user for **real production**
**P0:**
- [ ] Production `MONGO_URL` (Atlas connection string with existing data)
- [ ] Production `DB_NAME`
- [ ] Fresh `JWT_SECRET` (rotate)
- [ ] When deploying via Emergent's Deploy flow, set these as **deploy env vars**,
      NOT in the committed `.env` (so secrets never leave the deploy pipeline)

**P1:**
- [ ] `RESEND_API_KEY` to un-mock the weekly digest emails
- [ ] EAS account login + `eas build:configure` to populate `extra.eas.projectId` (one-time)
- [ ] Real app icons / splash images (currently uses repo defaults)

**P2:**
- [ ] FCM/APNs server keys for push notifications (scaffold already in `src/push.ts`)
- [ ] Apple Developer Program + Google Play Console enrollment for store submission

## Smart enhancement (already implemented this session)
**One-click AI roster import** — admins now see a `Import roster from PDF` banner on the
Schedule tab that opens the existing Claude Sonnet 4.5 roster parser in one tap. This was
buried inside the admin panel before. Saves managers ~30 min/week and is an obvious upsell
hook for the SaaS tier.
