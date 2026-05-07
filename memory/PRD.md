# StaffHub — Connecteam-style Staff Management App

## Vision
A mobile-first workforce OS that gives every employee one tap to clock in, request time off, see their schedule, share files, and complete fillable forms — all under JWT-secured access with a built-in admin console.

## User Personas
- **Admin / Manager** – Manages employees, shifts, holiday approvals, builds form templates, oversees compliance.
- **Staff / Employee** – Clocks in/out, requests holidays, views schedule, swaps shifts, uploads to shared drive, completes forms.

## Core Features (v1)

### 1. Authentication
- JWT-based login (Bearer tokens in AsyncStorage)
- Roles: `admin` and `staff`
- Admin-only user creation (no public sign-up)
- Seeded demo accounts: `admin@company.com / Admin@123`, `jane@company.com / Staff@123`

### 2. Clock In/Out
- One-tap clock in with optional GPS location
- Live elapsed timer on Home screen
- Full history per user with daily duration totals

### 3. Holidays
- Personal balance (entitlement / used / pending / remaining)
- Submit request with type (annual/sick/unpaid), date range, reason
- Admin approve/reject from admin panel

### 4. Job Scheduler (Advanced)
- Admin assigns shifts (title, time range, location, recurring tag)
- Employees view personal schedule
- Shift swap requests (employee → admin → approve flips ownership)
- Availability submissions (employee marks dates available/unavailable)

### 5. Shared Drive
- Folder hierarchy with breadcrumb navigation
- Upload files (base64, ≤5MB) via DocumentPicker
- File browsing, preview metadata, deletion

### 6. Fillable Forms (with Checklist mode)
- **Form mode**: Admin builds custom templates with field types: text, textarea, date, number, checkbox, select, signature
- **Checklist mode**: For Aer Lingus-style truck-wash sheets and any recurring inspection list. Admin defines item rows (e.g. `HL 29 … HL 44`) and shared sub-tasks per row (e.g. `EXT, INT`). Bulk-add items by pasting one per line.
- Staff fills as a table of checkboxes + Date + Notes; submission stored with composite keys (`HL29_EXT`, `HL29_INT`, …)
- **Stats engine**: `/api/forms/templates/{id}/stats?date_from=…&date_to=…` aggregates per-item per-sub-task counts, computes overall %, flags **on-target / below-target** vs the template's target %.
- Admin Stats viewer with Day / Week / Month / All filters, overall progress bar, per-item breakdown.
- **CSV / PDF export** *(NEW)*: Stats can be exported via `/api/forms/templates/{id}/stats/export?format=csv|pdf`. Mobile uses `expo-file-system` + `expo-sharing` to invoke the native share sheet; web triggers a blob download.
- Server generates printable PDF of individual submissions on demand via ReportLab.
- **AI summary** of submitted forms (Emergent LLM Key + Claude Sonnet 4.5)

### 8. Admin Alerts & Notifications
- `/api/admin/checklist-alerts` returns checklists below target today / no submission yet today.
- Home dashboard shows red admin-only alert card linking to Admin Panel.
- **In-app notifications** *(NEW)*: every admin gets a notification (`/api/notifications` inbox) when:
  - A checklist submission lands below target
  - Someone clocks in **off-site** (outside any depot's geofence)
  - Admin manually triggers `/api/admin/scan-alerts`
- Bell icon with unread badge on Home opens a NotificationsModal with mark-as-read controls.

### 9. Geofencing & Multiple Depots *(NEW)*
- Admin Panel → **Depots** tab. Each depot: `name`, `lat`, `lng`, `radius_m`.
- Clock-in captures device GPS via `expo-location`, computes haversine distance to nearest depot, and stamps `off_site=true` on the entry if outside the radius.
- Off-site clock-ins are **allowed** but **flagged** for admin review and notify all admins instantly.

### 10. Weekly Compliance Digest *(NEW)*
- APScheduler weekly job (Mondays 09:00 UTC) generates a CSV digest of every checklist's compliance over the last 7 days.
- Manual trigger via Admin Panel → Depots tab → "Send Weekly Digest Now" button.
- CSV is persisted server-side and emailed to all admins via **Resend** (currently MOCKED — no RESEND_API_KEY set; backend logs `[MOCKED EMAIL]`. Plug a key into `/app/backend/.env` to go live).
- `/api/admin/digests` lists past digests; `/api/admin/digests/{id}/download` returns the CSV.

### 7. Admin Panel (modal route)
- Tabs: Holidays, Shifts, Forms, Users
- Approve/reject holidays, assign shifts, build form templates, add employees

## Tech Stack
- **Backend**: FastAPI + Motor (Mongo) + bcrypt + PyJWT + ReportLab + emergentintegrations
- **Frontend**: Expo Router (SDK 54), React Native 0.81, AsyncStorage, axios, expo-document-picker, expo-location
- **Storage**: MongoDB (file blobs base64 in `files` collection)
- **AI**: Claude Sonnet 4.5 via Emergent Universal Key

## Out of Scope (v2)
- True PDF rendering with form-field overlay (currently a custom template engine — equivalent functionality, lighter mobile footprint)
- Push notifications (FCM/APNs) for shift updates and holiday decisions
- Offline-first sync queue
- Geofencing for clock in
- Payroll/timesheet exports
- Org-wide chat/announcements (Connecteam-style messaging)

## Smart Business Enhancement
Built-in **AI Form Summaries** turn every employee submission (incident report, expense, feedback) into an instant 3-4 sentence digest for the admin — reducing review time by ~80% and surfacing flags that warrant attention. This is a paid-feature hook for SaaS upsell.

### 11. Off-site Review (NEW)
- Admin Panel → **Off-site** tab lists every flagged clock-in over the last 14 days (`/api/admin/off-site-clock-ins`).
- Each row: employee, distance to nearest depot (auto km/m), lat/lng, timestamp, plus an **Open in Maps** button that launches Google Maps (Android/Web) or Apple Maps (iOS) at the exact coordinates.

### 12. Per-Depot Weekly Digest (NEW)
- Checklist templates can be tied to a depot (`depot_id` field, picker in FormBuilderModal).
- Weekly digest now produces **one CSV per depot** (templates without `depot_id` grouped under "Unassigned"). Each CSV is saved to `digests` and individually downloadable.
- Resend email attaches all bundles to a single email; mocked alert in admin UI lists every bundle by depot.
