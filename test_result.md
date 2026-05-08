#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Build a Connect Teams-style staff app with: clock in/out, holiday tracker & requests,
  job scheduler, shared drive (PDF fillable forms via Checklist builder), customer CRM
  (profiles, sites, contacts, notes), geofenced clock-ins, weekly digest emails (mocked),
  shift swap/availability, and admin dashboard.

backend:
  - task: "Holiday endpoints (balance, create, list, decision)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Endpoints exist; need verification of approve/reject flow + remaining balance math."
        - working: true
          agent: "testing"
          comment: "Verified via /app/backend_test.py against public proxy URL. GET /holidays/balance returns {entitlement, used, pending, remaining} for staff. POST /holidays/requests creates pending (3-day request increased pending by 3, two requests by 6). GET /holidays/requests returns own for staff and ?all=true returns all for admin (staff with all=true is correctly scoped to their own). POST /holidays/requests/{id}/decision?decision=approved by admin correctly reduces pending and increases used by 3 days; rejected request decrements pending without touching used. Staff hitting decision endpoint returns 403. Final math validated: used+=3, pending+=0, remaining-=3 over the run."
  - task: "Shifts with customer_id/site_id linking"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "POST /shifts now stores customer_id, customer_name, site_id, site_name. Verify response payload."
        - working: true
          agent: "testing"
          comment: "Created customer 'Riverside Council', added site 'Riverside Depot - East', then POST /api/shifts with {user_id, title, start, end, customer_id, site_id} returned customer_name and site_name auto-populated from the customer/site documents. GET /api/shifts as staff returned the same shift with customer_name and site_name persisted. Admin auth required for POST verified."
  - task: "Customer notes (pinned)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "GET /customers/{cid}/notes returns pinned-first order; verify auth and content."
        - working: true
          agent: "testing"
          comment: "POST /api/customers/{cid}/notes accepted both pinned=false (created first) and pinned=true (created later). GET /api/customers/{cid}/notes returned pinned note as first element confirming pinned-first ordering via Mongo sort([('pinned', -1), ('created_at', -1)]). Staff can read and create notes (endpoint requires auth only, not admin), as designed."
  - task: "PDF Fillable Forms (AcroForm parse + fill)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added pypdf-based extraction (_extract_pdf_fields) and fill (_fill_pdf). Endpoints: POST /pdf-forms/templates (admin upload base64 PDF, returns has_acroform + field_count), GET /pdf-forms/templates, GET /pdf-forms/templates/{id} (returns full PDF base64), DELETE /pdf-forms/templates/{id}, POST /pdf-forms/templates/{id}/fill (writes filled PDF, optional flatten), GET /pdf-forms/submissions (admin sees all, staff sees own), GET /pdf-forms/submissions/{id} (returns filled_pdf_base64). Stored in pdf_form_templates and pdf_form_submissions collections. Smoke-tested locally with reportlab-generated AcroForm PDF — text/checkbox/choice fields detected and filled, output PDF contains expected /V values."
        - working: false
          agent: "testing"
          comment: "Ran /app/pdf_forms_test.py against public proxy URL. 11/12 cases passed: (1) admin upload returns has_acroform=true, field_count=3, no pdf_base64 leak ✅; (2) listing has new template, no pdf_base64 ✅; (3) detail returns pdf_base64 + fields with types {text, checkbox, select} and options=['Engineering','Operations','HR','Finance'] ✅; (4) staff fill flatten=false succeeds and re-parsed PDF /V values match: full_name='John Doe', accept='/Yes', dept='Engineering' ✅; (6) staff submissions scoped to own, no filled_pdf_base64 in list ✅; (7) admin submissions list returns all 2 submissions ✅; (8) GET single submission returns filled_pdf_base64 decoding to %PDF ✅; (9) staff GET admin's submission → 403 ✅; (10) staff POST template → 403 ✅; (11) admin DELETE template returns 200, GET returns 404, submissions cascade-deleted ✅; (12) staff DELETE → 403 ✅. CRITICAL FAILURE on (5) POST fill flatten=true: backend returns 500 with detail \"Fill failed: Incorrect first char in NameObject, should start with '/': (1) is deprecated and was removed in pypdf 5.0.0.\" Root cause: in /app/backend/server.py _fill_pdf, the read-only flatten code does `obj.update({NameObject(\"/Ff\"): NameObject(str(1 << 0))})` which constructs NameObject(\"1\") — pypdf 6.x rejects NameObjects without a leading '/'. Fix: use NumberObject (from pypdf.generic) for the /Ff flag value, e.g. `obj.update({NameObject(\"/Ff\"): NumberObject(1)})`. The non-flatten path works correctly, so the bug only affects flatten=true requests."
        - working: true
          agent: "testing"
          comment: "Re-tested case 5 only via /app/pdf_forms_flatten_test.py against public proxy URL. Main agent's fix verified: server.py:1520 now uses `NumberObject(existing | 1)` instead of `NameObject(str(1 << 0))`. Flow: admin login → upload reportlab AcroForm PDF (text full_name + checkbox accept + choice dept[Engineering,Operations,HR,Finance]) returned has_acroform=true, field_count=3 ✅; staff login → POST /pdf-forms/templates/{id}/fill with values={full_name:'Riley Thompson', accept:True, dept:'Operations'} and flatten=true → 200 OK ✅; response contains filled_pdf_base64 (7715 bytes) decoding to %PDF magic ✅; re-parsing with pypdf shows /V values match exactly: full_name='Riley Thompson', accept='/Yes', dept='Operations' ✅; sanity: all 3/3 widget annots have /Ff bit-0 (ReadOnly) set after flatten=true ✅. Cleanup DELETE 200. flatten=true path now fully functional."

  - task: "Availability endpoints (set/list with role scoping)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "Verified via /app/recurring_shifts_test.py against public proxy URL. POST /api/availability as staff with {date:'2030-07-15', available:false, note:'test unavailable'} returns 200 with correct fields (user_id, user_name, date, available=false, note, updated_at). POST same date again with {available:true, note:'now available'} correctly upserts (only one record exists for that date when re-fetched, with the new values). GET /api/availability as staff returns own records only (others_count=0 even after admin posted their own). GET /api/availability as admin (no all flag) returns admin's own only. GET /api/availability?all=true as admin returns both admin and staff records. GET /api/availability?all=true as staff is correctly scoped to staff's own records (all=true is admin-only)."

frontend:
  - task: "Schedule shift card shows linked customer + pinned notes"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/schedule.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Wired customer_name, site_name, pinned notes preview, and View Customer CTA on each shift card. User to verify."
  - task: "PDF Fillable Forms UI (admin upload + staff fill + share)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin.tsx, /app/frontend/app/(tabs)/forms.tsx, /app/frontend/src/components/PdfFormFillModal.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Admin: new 'PDF' tab with DocumentPicker upload, base64 read via FileSystem (web fallback uses ArrayBuffer→btoa). Staff: forms tab now lists PDF templates, opens PdfFormFillModal that renders detected fields as text/switch/chip inputs, submits to /pdf-forms/templates/{id}/fill, shows download/share button using expo-sharing. Submissions list now merges checklists + PDFs."
  - task: "Recurring shifts (admin auto-generate series)"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/frontend/app/admin.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "ShiftIn now accepts repeat_count (1-60). When recurring=daily/weekly, backend inserts multiple shifts in series with shared series_id, occurrence_index 0..N-1, dates offset by 1d/7d. Admin shift modal exposes Repeat (none/daily/weekly) and number-of-occurrences input."
        - working: true
          agent: "testing"
          comment: "Verified backend portion via /app/recurring_shifts_test.py against public proxy URL. POST /api/shifts admin with recurring=daily, repeat_count=4 returned {created:4, series_id:<uuid>, first:{...}}; GET /api/shifts?all=true returned 4 shifts sharing the same series_id with start datetimes at +0d/+1d/+2d/+3d offsets and occurrence_index [0,1,2,3]. recurring=weekly, repeat_count=3 returned {created:3, series_id:<uuid>} and 3 shifts at +0d/+7d/+14d. recurring=none returned {created:1, series_id:null} (also verified omitting the field). Staff POST /api/shifts → 403 'Admin access required'. All 9 created shifts cleaned up via DELETE /api/shifts/{id} (200 each). Frontend admin.tsx not tested per instructions."
  - task: "Availability marking (staff calendar + admin team view)"
    implemented: true
    working: true
    file: "/app/frontend/app/(tabs)/schedule.tsx, /app/frontend/app/admin.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Backend /availability set/list already exists. Staff schedule has new 'Availability' tab with react-native-calendars Calendar — tap a date, mark unavailable/available with optional note."
        - working: true
          agent: "testing"
          comment: "Frontend smoke verified at mobile viewport 390x844: tabs Shifts/Swaps/Availability all visible; tab-availability opens react-native-calendars (testID availability-calendar). Tapped day 27 → note input + Mark Unavailable button rendered; submit succeeded and 'Your unavailable days' section appeared. Re-tapped same date → Mark Available button shown and toggling back worked. No regressions."
  - task: "Holiday Calendar polish (range picker + admin team calendar)"
    implemented: true
    working: true
    file: "/app/frontend/app/(tabs)/profile.tsx, /app/frontend/app/admin.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Replaced text date inputs with react-native-calendars period range picker on staff Holiday Request modal. Admin Holidays tab now shows multi-dot Team Holiday Calendar."
        - working: true
          agent: "testing"
          comment: "Verified: Profile +Request Holiday opens modal with holiday-calendar (testID). Tapped day 18 then 22, range highlight visible, filled reason 'Family event RT', submit-holiday returned successfully and request shows in list. Logged into admin → admin-tab-holidays default shows admin-holiday-calendar; Approve/Reject buttons visible for pending; Approve click cleared pending entry. Team holiday calendar dots present."
  - task: "Per-user availability filter on shift modal + tap-to-edit shift"
    implemented: true
    working: true
    file: "/app/frontend/app/admin.tsx, /app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Admin Assign-Shift modal now flags users as 'Unavailable' (amber row + warning icon) when they have a pending availability=false on the chosen start date. Shift cards in Admin Shifts list are tappable → opens Edit modal with same availability hint and updates via PATCH /api/shifts/{id}. Backend route added (require_admin)."
        - working: true
          agent: "testing"
          comment: "Backend portion (PATCH /api/shifts/{sid}) verified via /app/admin_features_test.py against the public proxy URL. (a) POST /shifts admin recurring=none returned created=1; (b) PATCH new title/start/end/location → response reflects all four updates and user_id/user_name remain Jane Doe (unchanged); (c) PATCH with a different user_id (admin's id) → user_name auto-resolved to 'Admin'; (d) PATCH with customer_id+site_id (Aer Lingus / Dublin Hangar from existing CRM) → customer_name and site_name auto-populated; (e) PATCH as staff → 403 'Admin access required'; (f) PATCH non-existent shift → 404 'Shift not found'; (g) DELETE cleanup 200. Frontend admin.tsx UI not tested per instructions."
  - task: "Holiday entitlement editor (admin)"
    implemented: true
    working: true
    file: "/app/frontend/app/admin.tsx, /app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Admin Users tab shows holiday_entitlement and a calendar-icon button per user. Tap → modal to edit days (0-365). Backend: PATCH /api/users/{user_id}/entitlement?value=N (admin only). After save, holiday balance recomputes against new entitlement on next /holidays/balance call."
        - working: true
          agent: "testing"
          comment: "Backend verified via /app/admin_features_test.py against the public proxy URL (jane@company.com). (a) PATCH /api/users/{staff_id}/entitlement?value=30 as admin → 200 {ok:true, holiday_entitlement:30}; (b) GET /api/holidays/balance as that staff returns entitlement=30 (used=6, pending=5, remaining=19) — value persisted to the user document and balance recomputes accordingly; (c) value=-5 → 400 'Entitlement must be 0–365 days'; (d) value=400 → 400 same detail; (e) PATCH as STAFF → 403 'Admin access required'; (f) PATCH /api/users/nonexistent/entitlement → 404 'User not found'; (g) restored to 25. All 7 sub-cases passed."
  - task: "Real Push notifications via Expo Push API"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/frontend/src/push.ts, /app/frontend/src/auth.tsx, /app/frontend/app.json"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Backend: added notify(user_id,...) helper that creates an in-app notification AND calls Expo Push API (https://exp.host/--/api/v2/push/send) when expo_push_token is set on the user. Wired into create_shift, update_shift, decide_holiday, decide_swap. New endpoint POST /api/users/me/push-token persists token. Frontend: src/push.ts uses expo-notifications + expo-device to register on login (silently ignores web). auth.tsx now calls registerForPushAsync after login/refresh and unregisters on logout. expo-notifications added to app.json plugins. Note: actual native push delivery only works on a physical device with Expo Go (cloud preview can't deliver native pushes), but the wiring is end-to-end."
  - task: "Collaborative PDF form sessions (multi-user fill, lock, download)"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/frontend/src/components/PdfFormFillModal.tsx, /app/frontend/app/(tabs)/forms.tsx, /app/frontend/app/admin.tsx, /app/frontend/src/components/WebDropZone.web.tsx, /app/frontend/src/components/WebDropZone.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "User reported drag-and-drop and upload button broken on admin PDF tab. Root cause: pickPdf could not extract base64 on web because expo-document-picker returns a data URL (and sometimes blob URL) rather than a file/file.uri readable by FileSystem. Rewrote with new helper readAssetAsBase64 that handles base64 prop, file ArrayBuffer, data: URL split, and blob: URL fetch fallback. Also added platform-split WebDropZone component (HTML5 drag-and-drop on web, no-op on native) wired into the upload modal. Added collaborative session model: pdf_form_sessions collection, endpoints POST /api/pdf-forms/templates/{tid}/sessions (anyone), GET /api/pdf-forms/sessions, GET /api/pdf-forms/sessions/{sid}, PATCH /api/pdf-forms/sessions/{sid} (open to all staff while draft, admin override after lock), POST /complete (admin only — locks + flattens PDF), POST /reopen (admin only), GET /api/pdf-forms/sessions/{sid}/pdf (download current state any time), DELETE (admin). Frontend: forms.tsx now lists in-progress sessions per template with progress percentage and last-editor name; New button creates a fresh session. PdfFormFillModal supports session mode with 700ms debounced auto-save (Saving… → Saved ✓ status), Mark Complete & Lock / Reopen / Download Current PDF actions. Web download opens in a new tab; native uses expo-sharing."
        - working: true
          agent: "testing"
          comment: "Backend regression PASSED 27/27 via /app/pdf_sessions_test.py against the public proxy URL (admin@company.com / jane@company.com). Built a tiny reportlab AcroForm PDF (text full_name + checkbox accept + choice dept[Engineering/Operations/HR/Finance]) and ran the full flow. (1) POST /pdf-forms/templates returns has_acroform=true, field_count=3, no pdf_base64 leak. (2a) POST /pdf-forms/templates/{tid}/sessions as staff with {name:'Crew Check #1'} → 200; response has id, status='draft', values={}, last_editor_name='Jane Doe'. (2b) Same call without body → 200 with auto-generated default name (e.g. 'Crew Check (Test) #20260508-0834'). (3) GET /pdf-forms/sessions includes both new sessions and contains NO filled_pdf_base64 in any entry; ?template_id={tid} and ?status=draft filters return only matching sessions. (4a) PATCH {values:{full_name:'John'}} as staff → 200 with saved_keys=1, total_filled=1; subsequent GET shows values.full_name='John' and last_editor_name='Jane Doe'. (4c) PATCH {values:{accept:true}} as ADMIN → 200 saved_keys=1, total_filled=2 (collab edit allowed during draft); GET shows merged values {full_name:'John', accept:true} and last_editor_name='Admin'. (5a) POST /complete as staff → 403 'Admin access required'. (5b) POST /complete as admin → 200; (5c) GET shows status='completed' and filled_pdf_base64 populated. (8) GET /pdf-forms/sessions/{sid}/pdf as staff in draft state → 200 with status='draft' and pdf_base64 decoding to bytes starting with b'%PDF'; same endpoint after complete → 200 with status='completed' and pdf_base64 decoding to b'%PDF…'. Admin can also fetch /pdf in draft state. (6a) PATCH after lock as staff → 403 with detail 'Session is locked. Ask admin to reopen.' (mentions 'lock'). (6b) PATCH after lock as admin → 200 (override accepted, dept set to 'Operations'). (7a) POST /reopen as staff → 403. (7b) POST /reopen as admin → 200; subsequent GET shows status='draft' and filled_pdf_base64 cleared (unset). (9a) DELETE /sessions/{sid} as staff → 403. (9b) DELETE as admin → 200. (9c) GET after delete → 404 'Session not found'. Cleanup: DELETE /pdf-forms/templates/{tid} as admin → 200. No regressions; all collaborative session endpoints behave per spec."

agent_communication_v4:
    - agent: "main"
      message: "Implemented collaborative PDF sessions + fixed upload/drag-drop. Please run a backend regression on the new /pdf-forms/sessions endpoints: 1) POST /pdf-forms/templates/{tid}/sessions as staff returns a draft with empty values; 2) GET /pdf-forms/sessions lists it (no filled_pdf_base64 in list); 3) PATCH /sessions/{sid} as staff with values updates last_editor_id and merges values dict; 4) PATCH still allowed as DIFFERENT staff (collab) and last_editor flips; 5) POST /complete as staff returns 403 (admin only); admin returns 200 and status flips to completed with filled_pdf_base64 saved; 6) PATCH after lock as staff returns 403; admin still 200 (override); 7) POST /reopen as admin clears completed status; 8) GET /sessions/{sid}/pdf returns valid base64 PDF (starts with %PDF after decode) for both draft and completed. Use creds in /app/memory/test_credentials.md. Build a tiny reportlab AcroForm PDF as before for the template upload."
        - working: true
          agent: "testing"
          comment: "Backend wiring verified via /app/admin_features_test.py against public proxy URL. (3a) POST /api/users/me/push-token as staff with {token:'ExponentPushToken[abc123]'} → 200 {ok:true}; immediately GET /api/auth/me returns expo_push_token='ExponentPushToken[abc123]'. (3b) {token:'garbage-token'} → 400 'Invalid Expo push token'. (3c) {token:''} → 200 {ok:true} and /auth/me shows expo_push_token=null. (3d) Admin valid-token flow → 200 ok. SMOKE (notify must not break flows when user has no expo_push_token): with both staff and admin tokens cleared, (4a) POST /api/shifts admin → 200 created:1 (notify(staff) ran without token); (4b) staff POST /api/holidays/requests → 200 pending, then admin POST /holidays/requests/{id}/decision?decision=rejected → 200 ok:true (notify(staff) safe); (4c) staff POST /api/shifts/{id}/swap → 200 pending, admin POST /shifts/swaps/{id}/decision?decision=rejected → 200 ok:true (notify both parties safe). All notify() calls wrapped in try/except so missing tokens never break the request; _send_expo_push also short-circuits when no valid Exponent tokens are present. End-to-end backend behaviour matches design."

agent_communication_v3:
    - agent: "main"
      message: "Implemented C+D+B(tap-to-edit)+A(real push). Please run a focused backend regression: 1) PATCH /api/users/{id}/entitlement (admin only, validates 0-365) and verify /api/holidays/balance reflects the change for that user; 2) PATCH /api/shifts/{sid} (admin only) updates user_id/title/start/end/location/customer_id/site_id and customer_name/site_name auto-resolve; 3) POST /api/users/me/push-token accepts ExponentPushToken[...] strings, rejects garbage with 400; empty token clears it (sets expo_push_token to null); 4) Smoke that decide_holiday/decide_swap/create_shift no longer crash (notify() must succeed even without a push token). Use creds in /app/memory/test_credentials.md."
  - task: "Frontend smoke flow — Auth, Schedule, Profile, Admin (PDF/Shifts/Swaps), Forms"
    implemented: true
    working: true
    file: "/app/frontend/app/index.tsx, /app/frontend/app/(tabs)/*, /app/frontend/app/admin.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "End-to-end smoke at 390x844: (1) Auth — both admin@company.com / Admin@123 and jane@company.com / Staff@123 login successfully and land on /home. (2) Schedule tabs OK; availability mark-off/on flow works. (3) Holiday request via calendar range picker works and admin sees it. (4) Admin Shifts: opened Assign New Shift modal, selected 'Jane Doe', filled Title/Start/End, picked weekly + count 3, tapped shift-assign-submit → POST /api/shifts returned 200 {created:3, series_id, first:{...recurring:weekly}} and DOM now shows 3 occurrences of '· weekly' suffix on the new RecTestRT2 shift. NOTE: Alert.alert on react-native-web renders as a custom modal (not a browser dialog), so the literal 'Series created… 3 shifts' string is shown in-app but cannot be captured by Playwright dialog handler — verified via the network response payload instead. (5) Admin Swap Requests: staff submitted swap on a shift via swap-{id} → swap-submit; admin Shifts tab shows 'Swap Requests' section with swap-approve-{id} / swap-reject-{id} testIDs (1 pending visible). (6) Admin PDF tab loads (open-pdf-upload visible, no errors). (7) Staff Forms tab loads templates list including PDF/Fillable section. All 7 flows working."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 2
  run_ui: false

test_plan:
  current_focus:
    - "PDF Fillable Forms (AcroForm parse + fill)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Finished schedule.tsx UI for linked customer + pinned notes on staff shift card. Please run backend regression on Holidays, Shifts (with customer/site fields), and Customer Notes."
    - agent: "testing"
      message: "Backend regression complete via /app/backend_test.py against the public proxy URL. 25/25 tests passed across smoke (login admin/staff, /auth/me, /clock/status, /notifications), Holidays (balance baseline + pending delta + approve/reject + final math + admin-only decision), Shifts with customer/site auto-populated names (POST + staff GET persists customer_name/site_name), and Customer Notes (pinned-first ordering with pinned note created after non-pinned still returned first). No critical issues found. All three high/medium priority tasks now marked working: true."
    - agent: "main"
      message: "Implemented True PDF Fillable Forms. Backend uses pypdf 6.x to extract AcroForm fields (text/checkbox/radio/select with options), fill values into fields and (optionally) lock them as read-only. Endpoints: /api/pdf-forms/templates (CRUD), /api/pdf-forms/templates/{id}/fill, /api/pdf-forms/submissions(/{id}). Please run focused tests: 1) admin uploads a base64 PDF (build a tiny one in the test using reportlab.pdfgen with form.textfield + form.checkbox + form.choice — or use an in-memory fixture), 2) GET listing returns has_acroform + field_count, 3) POST fill with values returns filled_pdf_base64 that decodes to a valid PDF whose fields contain the new values (verify by re-parsing with pypdf), 4) staff can list/get only own submissions, admin sees all, 5) DELETE removes template and its submissions. Use /app/memory/test_credentials.md."
    - agent: "testing"
      message: "PDF Fillable Forms: 11/12 tests passed via /app/pdf_forms_test.py. CRITICAL BUG in flatten=true path of _fill_pdf (server.py): line `obj.update({NameObject(\"/Ff\"): NameObject(str(1 << 0))})` produces a NameObject(\"1\") which pypdf 6.x rejects (NameObject must start with '/'). Returns 500 'Incorrect first char in NameObject'. Fix: replace with `NumberObject(1)` (import NumberObject from pypdf.generic) since /Ff is a numeric flag, not a name. flatten=false works perfectly — text='John Doe', checkbox /V='/Yes', select 'Engineering' all verified by re-parsing the returned PDF. All other endpoints (CRUD, role scoping, cascade delete) behave as expected; pdf_base64 is correctly omitted from list payloads and filled_pdf_base64 omitted from submission lists; admin sees all submissions, staff sees only own, cross-user GET returns 403, staff POST/DELETE on templates returns 403."
    - agent: "testing"
      message: "Re-test of case 5 (POST /pdf-forms/templates/{id}/fill with flatten=true) PASSED via /app/pdf_forms_flatten_test.py against public proxy URL. Main agent's fix at server.py:1520 (NumberObject(existing | 1) instead of NameObject(str(1 << 0))) is correct. Verified end-to-end: admin uploads reportlab AcroForm PDF (text+checkbox+choice) → staff posts fill with flatten=true → 200 OK with filled_pdf_base64 decoding to %PDF; pypdf re-parse confirms /V values match inputs (full_name='Riley Thompson', accept='/Yes', dept='Operations'); all 3/3 widget annots have /Ff bit-0 (ReadOnly) set. Task 'PDF Fillable Forms (AcroForm parse + fill)' is now fully working."
    - agent: "testing"
      message: "Frontend smoke (mobile 390x844) end-to-end PASSED for all 7 requested flows: (1) Auth admin+staff login OK; (2) Schedule three tabs visible; availability-calendar tap-date → mark-off saves and 'Your unavailable days' section appears; mark-on toggles back. (3) Profile +Request Holiday opens holiday-calendar; 2-date range select + reason + submit-holiday → request appears in list and admin-side. (4) /admin defaults to holidays tab; admin-holiday-calendar renders with dots; Approve clears pending request. (5) Admin Shifts → Assign New Shift → Jane Doe + title + start + end + weekly + count=3 + shift-assign-submit → POST /api/shifts 200 with {created:3, series_id, first.recurring=weekly}; DOM shows 3 shifts with '· weekly' suffix. NB: Alert.alert uses RN-Web custom modal (not browser dialog) so dialog handler can't capture text — verified via network response. (6) Admin Swap Requests section visible with swap-approve-{id}/swap-reject-{id} after staff submitted swap on a shift via swap-{id}/swap-submit. (7) Admin PDF tab loads (open-pdf-upload visible); Staff Forms tab loads templates including PDF/Fillable section. No critical issues."
    - agent: "testing"
      message: "Recurring shifts + Availability backend tests PASSED (29/29) via /app/recurring_shifts_test.py. POST /api/shifts admin: recurring=daily repeat_count=4 → {created:4, series_id, first}, GET ?all=true confirms 4 shifts share the series_id with starts at +0d/+1d/+2d/+3d and occurrence_index [0,1,2,3]; recurring=weekly repeat_count=3 → {created:3, series_id} with +0d/+7d/+14d offsets; recurring=none and omitted recurring → {created:1, series_id:null} (repeat_count ignored). Staff POST /api/shifts → 403. POST /api/availability upserts (POST same date with available:true overwrites earlier false; only one record persists). GET /api/availability scoped to caller; admin ?all=true returns both admin + staff records, while staff ?all=true is still limited to own. All 9 created shifts cleaned up via DELETE /api/shifts/{id}. Both 'Recurring shifts' and a new 'Availability endpoints' task marked working: true."
    - agent: "testing"
      message: "FRONTEND COLLAB PDF FLOW — BLOCKED BY UPLOAD BUG. Ran end-to-end UI test at 390x844 with admin@company.com / jane@company.com. Phase A failed at the very first step: built a real reportlab AcroForm PDF (3 fields: text+checkbox+choice) at /tmp/sample_form.pdf, opened admin → admin-tab-pdf-forms → open-pdf-upload → typed 'Aer Lingus Crew Check' into pdf-title-input (verified DOM input value is correct) → clicked pick-pdf-btn and used Playwright's expect_file_chooser to set_files(/tmp/sample_form.pdf). Modal then displayed 'sample_form.pdf' next to the upload button (so DocumentPicker → readAssetAsBase64 path completed without throwing). Tapping pdf-upload-submit triggered POST /api/pdf-forms/templates which returned **HTTP 400 {detail:'Invalid base64 PDF'}**. Backend logs show no traceback (the handler raised at base64.b64decode failure). This means the 'fixed' readAssetAsBase64 helper at /app/frontend/app/admin.tsx:1226 is producing an invalid (malformed/corrupted) base64 string from expo-document-picker's web asset, OR the asset's `.file`/`.uri` shape on this expo-document-picker version differs from what the helper expects (both `.file.arrayBuffer()` and the data:/blob: URL fallbacks may be returning empty or mis-encoded data — a fully empty base64 would have failed at the '%PDF' magic check rather than the b64decode catch, so it's likely partial / non-base64-alphabet bytes). Because no template was created, Phase B (start-session) had no start-session-{tid} button to click, and Phases C-D (admin lock/download/reopen, staff edit-after-lock guard) could not be exercised. Step 3 (drag-and-drop) was intentionally skipped per testing-agent rules. NOTE: the BACKEND collaborative-session endpoints were already verified PASSING in the previous run (27/27), and POST /api/pdf-forms/templates accepts a real reportlab base64 from python tests, so the regression is strictly in the frontend web upload path. Action items for main agent: (1) instrument readAssetAsBase64 to console.log file shape (file?.file ? typeof file.file : null, file.uri?.slice(0,30), file.size) and the resulting base64.length / first 16 chars, then re-check what expo-document-picker 55.0.13 actually returns on react-native-web — `assets[0].file` may not be a real Blob and `arrayBuffer()` may resolve with garbage, OR `assets[0].uri` is a regular http/blob URL that requires the fetch path. (2) Simplest robust fix: always prefer the `file.uri` data:/blob: path or call FileReader.readAsDataURL on file.file and split off the prefix, rather than building btoa from the iterated Uint8Array. (3) After fix, re-run only Phase A; if upload returns the new template, the rest of the collab session UI flow (autosave, lock, download, reopen, edit-after-lock guard) is independent of the upload bug and is expected to work since the backend endpoints already passed. Marked task working: false, stuck_count: 1, needs_retesting: true."
    - agent: "testing"
      message: "Collaborative PDF form sessions backend regression PASSED 27/27 via /app/pdf_sessions_test.py against the public proxy URL. Built reportlab AcroForm PDF (3 fields: text full_name, checkbox accept, choice dept[Engineering/Operations/HR/Finance]) and verified the entire spec end-to-end: (1) admin upload returns has_acroform=true, field_count=3; (2a) staff POST /pdf-forms/templates/{tid}/sessions {name:'Crew Check #1'} → 200 with id, status='draft', values={}, last_editor_name='Jane Doe'; (2b) same call without body → 200 with auto-generated default name. (3) GET /sessions lists both new sessions, no filled_pdf_base64 in any entry; ?template_id and ?status=draft filters work. (4a) staff PATCH {values:{full_name:'John'}} → 200 saved_keys=1; GET shows full_name='John' and last_editor_name=staff. (4c) admin PATCH {values:{accept:true}} during draft → 200 saved_keys=1, total_filled=2 (collab); GET shows merged values and last_editor_name='Admin'. (5a) staff /complete → 403; (5b) admin /complete → 200; (5c) GET shows status='completed' and filled_pdf_base64 populated. (8) GET /sessions/{sid}/pdf any-user returns 200 with pdf_base64 decoding to bytes starting with '%PDF' for both draft and completed states. (6a) staff PATCH after lock → 403 with detail 'Session is locked. Ask admin to reopen.' (matches 'lock'). (6b) admin PATCH after lock → 200 (override). (7a) staff /reopen → 403; (7b) admin /reopen → 200; GET shows status='draft' and filled_pdf_base64 cleared. (9a) staff DELETE /sessions/{sid} → 403; (9b) admin → 200; (9c) GET → 404. Cleanup: admin DELETE template → 200. No regressions; the 'Collaborative PDF form sessions' task is now marked working: true."
    - agent: "testing"
      message: "FRONTEND COLLAB PDF FLOW — RE-RUN PASSED at 390x844. First attempt against the running Expo bundle still returned 400 'Invalid base64 PDF' because Metro was serving the OLD pre-fix bundle of /app/frontend/app/admin.tsx (request body inspection showed pdf_base64 STILL prefixed with 'data:application/pdf;base64,'). After `supervisorctl restart expo` (no code changes), the new readAssetAsBase64 with FileReader.readAsDataURL took effect and the upload succeeded. Phase A: admin → admin-tab-pdf-forms → open-pdf-upload → typed 'Aer Lingus Crew Check' → pick-pdf-btn → set_files(/tmp/sample_form.pdf) → pdf-upload-submit → POST /api/pdf-forms/templates returned 200 with id, has_acroform=true, field_count=3, fields=[{full_name,text},{accept,checkbox},{dept,select}]; pdf_base64 sent as 10440 chars starting with 'JVBERi' (no data: prefix). Page rendered the 'Detected 3' alert text and the new template ('Aer Lingus Crew Check · 3 fields · 7.6 KB') appears in the admin pdf-forms list (testID pdf-tpl-{id}). Phase B: staff (jane@company.com) → forms → start-session-{tid} opened PdfFormFillModal → typed 'Riley Thompson' into the full_name TextInput → after 700ms debounce 'Saved ✓' indicator appeared and a single PATCH /api/pdf-forms/sessions/{sid} returned 200; closed modal. Admin (admin@company.com) → forms → session-{sid} opened the same session → session-download triggered PDF download (200 GET /sessions/{sid}/pdf) → session-complete locked the session and the modal redrew with header '🔒 Locked · Admin', the form fields became read-only, and a new 'Reopen for editing' button (testID session-reopen) appeared alongside Download/Share PDF; reopen clicked successfully and the modal flipped back to 'Draft · last edit by Jane Doe' with 'Mark Complete & Lock' visible again. Re-locked, then logged back in as staff and re-opened the same session — UI shows 'Locked by Admin' banner inline and the inputs are read-only (edit-after-lock guard ✓). Drag-and-drop intentionally skipped per testing-agent rules. All 4 screenshots captured (admin list with new template, admin locked modal, admin reopen back to draft, staff seeing lock banner). Task 'Collaborative PDF form sessions' is now marked working: true, stuck_count reset to 0, needs_retesting:false. NOTE TO MAIN AGENT: please make sure to restart the `expo` supervisor service after any change to admin.tsx — Metro's cache caused this run to fail twice before the restart, even though the source code already had the FileReader.readAsDataURL fix."
    - agent: "testing"
      message: "DRIVE UPLOAD FLOW (web, mobile viewport 390x844) — PASSED. Logged in as admin@company.com, navigated to /(tabs)/drive. (1) Header renders with 'SHARED DRIVE' label + 'Drive.' folder name; the dashed-border WebDropZone banner 'Drag & drop a file here, or use the upload button' is visible at the top of the list. (2) BUTTON UPLOAD: tapped upload-file-btn, used page.expect_file_chooser + chooser.set_files('/tmp/sample_form.pdf' — 7.6 KB AcroForm PDF). POST /api/drive/files returned 200 and the file 'sample_form.pdf · 7.6 KB · Admin' appeared in the list (testID file-{id}). (3) DRAG-AND-DROP: dispatched real DragEvent('drop') with a DataTransfer carrying a File built from base64-encoded sample_form.pdf bytes (renamed dropped.pdf) onto the dashed-border <div>. POST /api/drive/files returned 200 and 'dropped.pdf · 7.6 KB · Admin' appeared in the list. (4) PREVIEW: tapped sample_form.pdf row → GET /api/drive/files/{id} 200 → preview modal opened cleanly with name, MIME=application/pdf, Size=7.6 KB, and 'File ready. Stored securely in your shared drive.' (no crash, no red error). (5) >10MB GUARD: chose /tmp/big.pdf (11 MB) via upload-file-btn — NO POST /api/drive/files was sent (size check fired client-side); RN-Web Alert.alert is rendered via window.alert which Playwright auto-dismisses headlessly so the literal 'Too large' string isn't captured in DOM, but the absence of a network upload confirms the guard works as designed (same behaviour as Alert.alert in other tabs). Screenshots captured: drive_initial, drive_after_upload, drive_after_drop, drive_preview, drive_toolarge. The shared FileReader.readAsDataURL helper at src/utils/fileToBase64.ts works correctly for both DocumentPicker (asset.file path) and HTML5 drop (raw File path). No fixes applied; no code modified. Drive upload flow is fully functional."
    - agent: "testing"
      message: "Admin-features backend regression PASSED 26/26 via /app/admin_features_test.py against the public proxy URL. Tasks marked working: 'Holiday entitlement editor (admin)', 'Per-user availability filter on shift modal + tap-to-edit shift' (backend portion), 'Real Push notifications via Expo Push API' (backend wiring). Highlights: (1) PATCH /api/users/{id}/entitlement validates 0–365 (rejects -5 and 400 with 400), enforces admin (403 for staff), 404 for non-existent, and /api/holidays/balance reflects the new entitlement on next call (verified entitlement=30 then restored to 25). (2) PATCH /api/shifts/{sid} (admin only) updates title/start/end/location with user_id/user_name unchanged, auto-resolves user_name when user_id changes, auto-populates customer_name and site_name from customer_id+site_id (used existing CRM customer Aer Lingus / site Dublin Hangar), 403 for staff, 404 for non-existent shift. (3) POST /api/users/me/push-token accepts ExponentPushToken[...] (200 ok:true and /auth/me reflects the value), rejects garbage with 400 'Invalid Expo push token', empty string clears it (200 then /auth/me shows expo_push_token=null), works for both staff and admin. (4) Smoke with both users having no expo_push_token: create_shift, decide_holiday, and decide_swap all return 200 — notify() is wrapped in try/except and _send_expo_push short-circuits when no valid Exponent tokens are present, so missing/invalid tokens never break the request. No regressions."
