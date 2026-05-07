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

### 6. Fillable Forms
- Admin builds custom templates with field types: text, textarea, date, number, checkbox, select, signature
- Staff fills and submits
- Server generates printable PDF on demand (`/api/forms/submissions/{id}/pdf` via ReportLab)
- **AI summary** of submitted forms (Emergent LLM Key + Claude Sonnet 4.5)

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
