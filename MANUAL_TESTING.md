# 🧪 CampusTriage — Manual Testing Script

> **Before you start:** Seed the database with `docker exec coen453-app-1 python seed.py`
> then open the app at **http://localhost:8000**
>
> All accounts use password: **`password123`**
> Sample dispensing token: **`ABC123`**

---

## ✅ Checklist Legend
- `[ ]` Not yet tested
- `[P]` Pass
- `[F]` Fail — note what went wrong

---

## 1. Pre-Flight

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1.1 | Navigate to `http://localhost:8000` | Redirected to `/login` (not logged in) | `[ ]` |
| 1.2 | Navigate to `http://localhost:8000/dashboard` without logging in | Redirected to `/login` | `[ ]` |
| 1.3 | Navigate to `http://localhost:8000/admin/flows` without logging in | Redirected to `/login` | `[ ]` |

---

## 2. Authentication

### 2A — Login Page
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2A.1 | Visit `/login` | Login form renders cleanly | `[ ]` |
| 2A.2 | Submit empty form | Error: "field required" or form validation fires | `[ ]` |
| 2A.3 | Enter wrong email `nobody@x.com` / any password | Error: **"Incorrect email or password."** (not a stack trace) | `[ ]` |
| 2A.4 | Enter correct email but wrong password | Error: **"Incorrect email or password."** | `[ ]` |

### 2B — Student Login
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2B.1 | Login as `student@campus.edu` / `password123` | Redirected to **Student Dashboard** | `[ ]` |
| 2B.2 | Check page title / header says Student view | Role-specific welcome message visible | `[ ]` |

### 2C — Clinician Login
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2C.1 | Logout, login as `clinician@campus.edu` | Redirected to **Clinician Dashboard** | `[ ]` |
| 2C.2 | Check page shows pending case queue | At least 1 flagged pending case visible | `[ ]` |

### 2D — Pharmacist Login
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2D.1 | Logout, login as `pharmacist@campus.edu` | Redirected to **Pharmacist Dashboard** | `[ ]` |
| 2D.2 | Pharmacist should NOT see admin nav items (Flows, Import, Audit) | Admin-only links not visible | `[ ]` |

### 2E — Admin Login
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2E.1 | Logout, login as `admin@campus.edu` | Redirected to **Admin Dashboard** | `[ ]` |
| 2E.2 | Admin dashboard shows high-level metrics | Stats / cards visible | `[ ]` |

### 2F — Logout
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2F.1 | Click Logout from any account | Redirected to `/login`, session cleared | `[ ]` |
| 2F.2 | After logout press browser back button | Redirected to `/login` (not served cached page) | `[ ]` |

### 2G — Registration
| # | Step | Expected | Result |
|---|------|----------|--------|
| 2G.1 | Visit `/register`, create new account `test@campus.edu` / `password123` | Account created, redirected to dashboard | `[ ]` |
| 2G.2 | Try to register with same email again | Error: **"User with this email already exists."** | `[ ]` |
| 2G.3 | New account role defaults to **Student** | Student dashboard shown | `[ ]` |

---

## 3. Student Dashboard & Triage

### 3A — Dashboard
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3A.1 | Login as student, check dashboard | Shows case history, "Start New Triage" button | `[ ]` |
| 3A.2 | 2 previous cases visible (1 PENDING/flagged, 1 TRIAGED/pharmacy) | Both cases appear in history list | `[ ]` |

### 3B — Triage Engine (Full Flow Walkthrough)
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3B.1 | Click "Start New Triage" | Triage page loads with first question: **"What is your primary complaint today?"** | `[ ]` |
| 3B.2 | Select **"Pain or Fever"** | Next question: **"Where is the pain located?"** | `[ ]` |
| 3B.3 | Select **"Head or face"** | Next question: **"How would you describe your headache?"** | `[ ]` |
| 3B.4 | Select **"Mild (1-3) — background ache"** | Next question: **"How long have you had this headache?"** | `[ ]` |
| 3B.5 | Select **"Less than 4 hours"** | Outcome shown: **PHARMACY** with prescription details | `[ ]` |
| 3B.6 | Outcome message mentions Ibuprofen and Paracetamol | Prescription drugs are listed clearly | `[ ]` |
| 3B.7 | A dispensing token is displayed | Token shown (6 chars alphanumeric) | `[ ]` |
| 3B.8 | Case record created and visible in dashboard history | New TRIAGED case appears | `[ ]` |

### 3C — Red Flag Path (Emergency)
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3C.1 | Start new triage → **"Pain or Fever"** → **"Head or face"** → **"Severe (7-10)"** | Next question: warning signs | `[ ]` |
| 3C.2 | Select **"Sudden thunderclap onset"** | Outcome: **EMERGENCY** with 999 / A&E instructions | `[ ]` |
| 3C.3 | No dispensing token issued for Emergency outcome | Token section not shown | `[ ]` |

### 3D — Mental Health Path
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3D.1 | Start triage → **"Mental health or Stress"** | Hint text "Your answers are confidential" appears | `[ ]` |
| 3D.2 | Select **"Exam stress or anxiety — manageable"** | Next: sleep/eating question | `[ ]` |
| 3D.3 | Select **"Yes — functioning OK"** | Outcome: **SELF_CARE** with counselling drop-in info | `[ ]` |
| 3D.4 | Start new triage → mental health → **"Thoughts of suicide with plan or intent"** | Outcome: **EMERGENCY** with Samaritans number | `[ ]` |

### 3E — GI Path
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3E.1 | Start triage → **"Stomach or Bowel issue"** → **"Nausea only"** | Outcome: **PHARMACY** with ORS, Domperidone, Loperamide | `[ ]` |
| 3E.2 | Start triage → GI → **"Blood in vomit or stools"** | Outcome: **EMERGENCY** immediately | `[ ]` |

### 3F — Respiratory Path
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3F.1 | Start triage → **"Cough or Breathing issue"** → **"Dry cough only, no fever"** | Outcome: **SELF_CARE** | `[ ]` |
| 3F.2 | Start triage → Respiratory → **"Breathlessness at rest or wheezing"** → **"No known asthma"** | Outcome: **EMERGENCY** | `[ ]` |

### 3G — Injury Path
| # | Step | Expected | Result |
|---|------|----------|--------|
| 3G.1 | Start triage → **"Injury or Wound"** → **"Minor cut or graze"** | Outcome: **PHARMACY** with wound care prescriptions | `[ ]` |
| 3G.2 | Start triage → Injury → **"Head injury with LOC"** | Outcome: **EMERGENCY** | `[ ]` |

---

## 4. Clinician Features

*Login as `clinician@campus.edu`*

### 4A — Case Queue
| # | Step | Expected | Result |
|---|------|----------|--------|
| 4A.1 | Navigate to dashboard / case queue | Pending/flagged cases listed | `[ ]` |
| 4A.2 | Flagged case shows a visual indicator (flag icon or badge) | Clearly marked as flagged | `[ ]` |

### 4B — Case Detail
| # | Step | Expected | Result |
|---|------|----------|--------|
| 4B.1 | Click on a case from the queue | Case detail page loads with patient info, score, answers | `[ ]` |
| 4B.2 | Case notes field is visible | Notes from triage / seed shown | `[ ]` |
| 4B.3 | The system-recommended outcome is displayed | e.g. "PHARMACY" badge | `[ ]` |

### 4C — Clinician Override
| # | Step | Expected | Result |
|---|------|----------|--------|
| 4C.1 | On a PENDING case detail, click **Override** | Override modal / section appears | `[ ]` |
| 4C.2 | Select a different outcome (e.g. CLINIC) and enter a reason | Form accepts it | `[ ]` |
| 4C.3 | Submit override | Case status changes to **OVERRIDDEN**, reason saved | `[ ]` |
| 4C.4 | Overridden outcome displayed in case detail | Shows clinician's chosen outcome | `[ ]` |

### 4D — Access Control for Clinicians
| # | Step | Expected | Result |
|---|------|----------|--------|
| 4D.1 | Visit `/admin/flows` as clinician | Flows list visible (read access) | `[ ]` |
| 4D.2 | Visit `/admin/import` as clinician | Should be **403 Forbidden** or redirect | `[ ]` |
| 4D.3 | Try to create a flow as clinician | Create button not visible or returns 403 | `[ ]` |

---

## 5. Pharmacist Features

*Login as `pharmacist@campus.edu`*

### 5A — Token Validation
| # | Step | Expected | Result |
|---|------|----------|--------|
| 5A.1 | Navigate to pharmacy scanner / validation page | Input field for token visible | `[ ]` |
| 5A.2 | Enter **`ABC123`** | Token validated, case info + prescription shown | `[ ]` |
| 5A.3 | Prescription items (drug name, dose, instructions) displayed | Clear medication details shown | `[ ]` |
| 5A.4 | Click "Mark as Dispensed" / confirm | Token marked as used, success message shown | `[ ]` |
| 5A.5 | Enter `ABC123` again (now used) | Error: token already used | `[ ]` |
| 5A.6 | Enter a completely fake token e.g. `ZZZZZ1` | Error: invalid or not found | `[ ]` |

### 5B — Access Control for Pharmacists
| # | Step | Expected | Result |
|---|------|----------|--------|
| 5B.1 | Try to visit `/admin/flows` as pharmacist | **403 Forbidden** or redirect | `[ ]` |
| 5B.2 | Try to visit the case queue as pharmacist | **403** or redirect | `[ ]` |

---

## 6. Admin Features

*Login as `admin@campus.edu`*

### 6A — Flow Management (List)
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6A.1 | Visit `/admin/flows` | Flow list renders, "Campus Health Triage Flow v1.0" visible | `[ ]` |
| 6A.2 | Flow shows status badge: **ACTIVE** | Status clearly displayed | `[ ]` |

### 6B — Create New Flow
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6B.1 | Click "New Flow" — modal opens | Upload/create modal appears | `[ ]` |
| 6B.2 | Submit with empty name | Validation error shown | `[ ]` |
| 6B.3 | Submit with invalid JSON in rule payload | Error: invalid format | `[ ]` |
| 6B.4 | Submit with valid name and valid JSON payload | Flow created as DRAFT, appears in list | `[ ]` |

### 6C — Edit Flow
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6C.1 | Click Edit on any DRAFT or ARCHIVED flow | Edit modal opens pre-filled with current data | `[ ]` |
| 6C.2 | Change the name and save | Flow name updated | `[ ]` |
| 6C.3 | Try to edit the currently ACTIVE flow | Edit allowed (check if restricted or not) | `[ ]` |

### 6D — Flow Lifecycle
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6D.1 | On a DRAFT flow, click **Submit for Approval** | Status changes to **PENDING_APPROVAL** | `[ ]` |
| 6D.2 | Login as clinician, approve the flow | Status changes to **ACTIVE** | `[ ]` |
| 6D.3 | When new flow becomes ACTIVE, previous ACTIVE flow becomes **ARCHIVED** | Only 1 active flow at a time | `[ ]` |
| 6D.4 | On ARCHIVED flow, click **Reactivate** | It becomes ACTIVE, previous ACTIVE archived | `[ ]` |
| 6D.5 | On ARCHIVED flow, click **Delete** | Flow permanently removed from list | `[ ]` |

### 6E — Flow Detail
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6E.1 | Click on a flow name to view detail | Flow detail page shows rule tree / payload info | `[ ]` |
| 6E.2 | Sandbox test form visible on detail page | Test form present | `[ ]` |
| 6E.3 | Submit sandbox answers | Results shown without saving a case | `[ ]` |

### 6F — Analytics Dashboard
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6F.1 | Visit analytics page | Metrics visible (total cases, outcomes breakdown) | `[ ]` |
| 6F.2 | Charts / graphs render without errors | No blank areas or JS console errors | `[ ]` |

### 6G — Data Import (CSV)
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6G.1 | Visit `/admin/import` | CSV upload page renders | `[ ]` |
| 6G.2 | Upload a non-CSV file (e.g. `.txt`) | Error: **"File must be a CSV."** | `[ ]` |
| 6G.3 | Upload a CSV with wrong columns | Error: **"Missing required columns: ..."** | `[ ]` |
| 6G.4 | Upload a valid CSV with columns `student_id, outcome, visit_date, notes` | Import summary shown: total/imported/skipped | `[ ]` |

**Sample valid CSV content:**
```
student_id,outcome,visit_date,notes
STU123,PHARMACY,2026-01-15T10:00:00,Headache after exam
STU123,SELF_CARE,2026-02-01T14:30:00,Mild cold symptoms
```

### 6H — Audit Log
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6H.1 | Visit audit log page | List of events: logins, case creations, flow approvals | `[ ]` |
| 6H.2 | Each entry shows actor, action, timestamp | Readable format, no raw IDs only | `[ ]` |
| 6H.3 | Click on a log entry (if diff available) | Shows what changed (before/after) | `[ ]` |

### 6I — Admin Access Control
| # | Step | Expected | Result |
|---|------|----------|--------|
| 6I.1 | Visit pharmacy token scanner as admin | Should be **403** or redirect | `[ ]` |

---

## 7. Error Pages & Edge Cases

| # | Step | Expected | Result |
|---|------|----------|--------|
| 7.1 | Visit `http://localhost:8000/this-page-does-not-exist` | Custom 404 page shown (not raw FastAPI JSON) | `[ ]` |
| 7.2 | While logged in as student, visit `/admin/flows` | **403 Forbidden** page | `[ ]` |
| 7.3 | While logged in as student, visit `/admin/import` | **403 Forbidden** page | `[ ]` |
| 7.4 | Try accessing a case ID that does not exist: `/cases/00000000-0000-0000-0000-000000000000` | 404 page | `[ ]` |

---

## 8. HTMX Interactions (Dynamic UI)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 8.1 | On triage flow, advance through questions | **Page does not full-reload** between questions (HTMX partial swap) | `[ ]` |
| 8.2 | Login with wrong credentials | Error message appears in-place, no full reload | `[ ]` |
| 8.3 | Create new flow from modal | Modal closes, new card appears in list without full reload | `[ ]` |
| 8.4 | Delete a flow | Flow card disappears from list without full reload | `[ ]` |
| 8.5 | Override a case | Status updates inline | `[ ]` |
| 8.6 | Token validation in pharmacy | Result appears below form without reload | `[ ]` |

---

## 9. Session & Security

| # | Step | Expected | Result |
|---|------|----------|--------|
| 9.1 | Login, note session cookie `ct_session` in browser DevTools → Application → Cookies | Cookie present and `HttpOnly` | `[ ]` |
| 9.2 | Manually delete `ct_session` cookie | Navigating to `/dashboard` redirects to `/login` | `[ ]` |
| 9.3 | Login error messages never reveal raw stack traces or SQL | Only user-friendly messages shown | `[ ]` |
| 9.4 | Login error messages never confirm whether the email exists (says "Incorrect email or password" for both wrong email AND wrong password) | Same generic message in both cases | `[ ]` |

---

## 10. Cross-Role Quick Smoke Test

Run this after any major deployment to confirm nothing is catastrophically broken.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 10.1 | Student can login → see dashboard → start triage → get outcome | Full flow completes | `[ ]` |
| 10.2 | Clinician can login → see pending case → override it | Override saved | `[ ]` |
| 10.3 | Pharmacist can login → validate token `ABC123` (re-seed first) | Prescription shown | `[ ]` |
| 10.4 | Admin can login → view flows → see analytics | Pages load | `[ ]` |
| 10.5 | All 4 accounts can logout cleanly | Redirected to `/login` | `[ ]` |

---

## 🔁 How to Re-Seed Between Test Runs

```bash
docker exec coen453-app-1 python seed.py
```

This wipes all data and recreates:
- 4 test accounts
- 1 production-grade triage flow (ACTIVE)
- 3 sample cases (PENDING flagged, TRIAGED/pharmacy, CLOSED/self-care)
- Token `ABC123` valid for 24 hours

---

*Last updated: 2026-04-01 — CampusTriage v1.0*
