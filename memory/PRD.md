# StaffHub / FleetWash — Migration & Production-Prep PRD

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
- **2026-05-28** — HR Envelope enhancements complete:
  - **Bulk send** (`user_ids: []`) to one shared template / one issuance per staff
  - **Resend** endpoint (`POST /hr/issuances/{iid}/resend`) — re-attaches original PDF, blocks signed/cancelled/expired
  - **Silent cancel** (no email side-effect, audit only)
  - **Envelopes summary** rollup (`GET /hr/envelopes/summary`) — outstanding / pending / read / signed / overdue / stagnant
  - **3-day stagnant reminder** APScheduler job (07:00 UTC daily, gated by `reminder_3d_stagnant` audit marker)
  - **Admin UI**: rollup badges on Envelopes tab, multi-select picker + Select-all + filter in upload modal,
    Resend/Cancel buttons on HR Profile drawer
- **2026-05-28** — Holiday Calendar Legend: per-staff colour key chips + pending fallback chip on Holidays tab
- **2026-05-28** — Paul's account password reset to documented `Staff123!`
- **2026-05-29** — **Delete Roster** button on admin Shifts tab: lists all published roster PDFs (newest first, LATEST badge on top), each with a destructive delete confirmation; refreshes after publish/delete

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

## P1 — Next up
- [ ] Manual lat/lng fallback field in Customer Site modal (Nominatim ~5–10% Eircode misses)
- [ ] EAS account login + `eas build:configure` → fill `extra.eas.projectId`
- [ ] Real app icons / splash images
- [ ] Investigate React error #418 hydration warning on /admin first paint (cosmetic)

## P2 — Backlog
- [ ] Split `admin.tsx` (4856 lines) and `routers/hr.py` (878 lines) into per-tab/per-feature modules
- [ ] FCM/APNs server keys for push notifications (scaffold already in `src/push.ts`)
- [ ] Apple Developer + Google Play enrollment for store submission
- [ ] Resend API key to un-mock the *weekly digest* (transactional already on SMTP)
- [ ] Audit-trail filtering UI on HR Profile drawer (filter by event kind / date range)

## Currently MOCKED
- Weekly digest emails fall back to log line when `RESEND_API_KEY` is unset
  (does not affect transactional envelope/reminder mail which uses SMTP)
