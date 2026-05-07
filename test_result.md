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
