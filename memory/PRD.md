# Fleetwash Hub (formerly StaffHub / FleetWash) — Migration & Production-Prep PRD

## Original problem statement
Migrate the existing Expo + FastAPI + MongoDB **StaffHub / FleetWash** app from
GitHub (`https://github.com/Clok2410/APP-Fleetwash`) into this Emergent pod, verify
backend + Mongo, serve Expo web at the public URL, keep cross-platform (web + iOS + Android),
and **never wipe the production MongoDB data**.

## Architecture summary
**Backend** (`/app/backend`, FastAPI + Motor)
- `server.py` — auth, clock in/out + geofencing, holidays, shifts, roster LLM parser, drive,
  form templates + checklists, AI summaries, PDF form sessions, notifications, weekly digest,
  HR sweeps + reminders
- `deps.py` — DB, JWT, password hashing
- `routers/` — customers, holidays, hr (DocuSign-style envelopes)

**Frontend** (`/app/frontend`, Expo SDK 54)
- Expo Router (`app/_layout`, `app/index`, `app/(tabs)/{home,schedule,drive,forms,profile}`, `app/admin`)
- Cross-platform: web (`react-native-web`), iOS, Android
- Served as static export (`expo export -p web`) from `dist/` by FastAPI in production
- SSR hydration is gated by a `hydrated` flag in `_layout.tsx` and `admin.tsx` — the static
  HTML shell renders empty, real UI mounts on the client after `useEffect`. This eliminates
  React minified error #418 (Build-time vs client-time `new Date()` mismatches).

## Implemented (chronological)
- **2026-05-22** — Repo clone, local-dev wiring, JWT, demo seed, /me/users verified
- **2026-05-22** — Expo static export → FastAPI serves `dist/`. EAS configs. AI roster import banner.
- **mid-session** — MongoDB Atlas migration, SMTP (Gmail App Password) replaces Resend for transactional mail
- **mid-session** — Roster Global PDF publish + inline preview, Hours Sheets with column sorting,
  unified Depots auto-geocoded via Nominatim
- **mid-session** — Holiday clash detection, date-range CSV report, on-leave-today panel,
  clickable status pills, dedicated Clashes filter
- **mid-session** — HR DocuSign-style Envelopes: PDF upload + email delivery + read receipt
  + signed PDF email back + signed copy to staff
- **2026-05-28** — HR Envelope enhancements (bulk send, resend, silent cancel, status rollup,
  3-day stagnant reminder via APScheduler)
- **2026-05-28** — Holiday Calendar Legend: per-staff colour key chips + pending fallback chip
- **2026-05-28** — Paul's account password reset to documented `Staff123!`
- **2026-05-29** — Delete Roster button + list view on admin Shifts tab
- **2026-06-02** — Manual lat/lng override field on Customer Site modal (Nominatim Eircode misses);
  site cards now display coords or a "geofencing disabled" warning if missing
- **2026-06-02** — React error #418 fix via SSR hydration shell in `_layout.tsx` and `admin.tsx`
- **2026-06-02** — Rebrand: app name **Fleetwash Hub**, slug `fleetwash-hub`,
  bundle `com.fleetwash.hub`. Real FleetWash logo wired as `icon.png` (1024×1024 on black),
  `adaptive-icon.png`, `splash-image.png` (1242×2436), `favicon.png`. Sidebar + login screen
  show new brand name.
- **2026-06-02** — `docs/EAS_SETUP.md` written — one-page guide for `eas init`, build profiles,
  store submission. User runs this from laptop when ready for iOS/Android binaries.

Backend `/app/backend/tests/test_hr_envelopes.py` covers 16 scenarios incl. RBAC, bulk dedupe,
silent cancel, resend state machine, summary shape. All passing.

## Tech stack
- FastAPI 0.110, Motor 3.3, MongoDB Atlas (cluster0.svzpkts), APScheduler 3.11, ReportLab 4.5, pypdf
- Expo SDK 54, React Native 0.81, React 19, Expo Router 6, serve 14
- Claude Sonnet 4.5 via emergentintegrations (roster PDF parsing, form AI summaries)
- SMTP Gmail (transactional). Resend kept as optional fallback for weekly digest.

## P0 — Done
- [x] Production MONGO_URL + DB_NAME wired (Atlas)
- [x] SMTP transactional email (Gmail App Password)
- [x] HR Envelope enhancements (bulk / resend / cancel / summary / 3-day reminder)
- [x] Holiday calendar legend
- [x] Delete Roster button
- [x] Manual lat/lng override on Customer Site modal
- [x] React #418 hydration warning fixed
- [x] App rebranded to "Fleetwash Hub" with real logo icon/splash/favicon

## P1 — Next up
- [ ] EAS account login + `eas init` from user's laptop → fills `extra.eas.projectId` in `app.json`
  (see `docs/EAS_SETUP.md` — user-runnable, 2 minutes)
- [ ] Apple Developer + Google Play enrollment + first store build via `eas build`

## P2 — Backlog
- [ ] Split `admin.tsx` (~5000 lines) and `routers/hr.py` (~880 lines) into per-tab/per-feature modules
- [ ] FCM/APNs server keys for push notifications (scaffold already in `src/push.ts`)
- [ ] Apple Developer + Google Play enrollment for store submission
- [ ] Resend API key to un-mock the *weekly digest* (transactional already on SMTP)
- [ ] Audit-trail filtering UI on HR Profile drawer (filter by event kind / date range)
- [ ] Roster history "trash" / undo (30-day soft delete)

## Currently MOCKED
- Weekly digest emails fall back to log line when `RESEND_API_KEY` is unset
  (does not affect transactional envelope/reminder mail which uses SMTP)
