# Deployment Architecture — Shared Review Interface

> **Status:** Design document only — Phase 1.  
> No hosted service has been deployed. A local development URL is not a shareable production link.

---

## 1. Purpose

The Twi Translation Benchmark Lab requires human reviewers — qualified Asante Twi speakers and narrators — to evaluate machine-generated translations. Reviewers must be able to:

- Open the review interface on their own device without installing any software.
- Review experiment results submitted by the content team at a convenient time.
- Submit quality scores, error category labels, corrections, and notes.
- Return to continue or revise their work without losing progress.
- Be prevented from accidentally submitting duplicate assessments.

This document specifies the architecture that satisfies these requirements. It is a forward-looking design guide for Phases 4 and 5, not a Phase 1 deliverable.

---

## 2. Core Architectural Principle

**Separate the translation worker from the reviewer interface.**

| Component | Where it runs | Who needs access |
|-----------|--------------|-----------------|
| OPUS-MT inference | Developer's local machine | Developer only |
| Khaya API calls | Developer's machine or CI | Developer only |
| Experiment result storage | Hosted database | Everyone (authenticated) |
| Review web interface | Hosted web server | Reviewers (authenticated) |
| Review submissions | Hosted database | Reviewers + content lead |

The developer's computer can be offline when reviewers are working. The reviewer interface depends only on the hosted database, not on the developer's local machine.

---

## 3. Component Diagram

```
┌───────────────────────────────────────────────────────────────┐
│  Developer workstation (local)                                │
│                                                               │
│  ┌────────────┐   ┌───────────┐   ┌──────────────────────┐   │
│  │ OPUS-MT    │   │ Khaya API │   │  twi_lab CLI         │   │
│  │ (local     │   │ client    │   │  (translation worker │   │
│  │  inference)│   │           │   │   + experiment mgr)  │   │
│  └─────┬──────┘   └─────┬─────┘   └──────────┬───────────┘   │
│        └─────────────────┴──────────────────┐ │               │
│                                             ▼ │               │
│                                    ExperimentRun +            │
│                                    TranslationResult records  │
└───────────────────────────────────────────┬───────────────────┘
                                            │  Upload via
                                            │  authenticated API
                                            ▼
┌───────────────────────────────────────────────────────────────┐
│  Hosted infrastructure                                        │
│                                                               │
│  ┌─────────────────────────────────┐                         │
│  │  Review API (FastAPI or similar) │                         │
│  │  - Reviewer auth (JWT/session)   │◄──── HTTPS ────────┐   │
│  │  - Review assignment management  │                     │   │
│  │  - Submission endpoint           │                     │   │
│  │  - Result read endpoint          │                     │   │
│  └──────────────┬──────────────────┘                     │   │
│                 │                                         │   │
│  ┌──────────────▼──────────────────┐   ┌─────────────────┴─┐ │
│  │  Hosted database (PostgreSQL)   │   │  Review web app   │ │
│  │  - experiments                  │   │  (HTML/JS SPA)    │ │
│  │  - translation_results          │   │  Hosted on CDN    │ │
│  │  - review_assignments           │   │  or web server    │ │
│  │  - review_submissions           │   └───────────────────┘ │
│  │  - reviewer_sessions            │                         │
│  └─────────────────────────────────┘                         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                                            ▲
                              HTTPS + auth token
                                            │
                              ┌─────────────┴────────────┐
                              │  Reviewer's device       │
                              │  (browser only, no       │
                              │   local software needed) │
                              └──────────────────────────┘
```

---

## 4. Data Model Extensions for Phase 4

Phase 1 schemas (`TranslationResult`, `ExperimentRun`) are already compatible with this design. Phase 4 must add:

### 4.1 `ReviewAssignment`

Links a reviewer to a specific translation result for blind evaluation.

| Field | Type | Notes |
|-------|------|-------|
| `assignment_id` | UUID | Primary key |
| `experiment_id` | str | FK to ExperimentRun |
| `passage_id` | str | FK to BenchmarkPassage |
| `result_ids` | List[UUID] | Translation results for this passage (blinded) |
| `reviewer_id` | str | Pseudonymous reviewer identifier |
| `status` | enum | `assigned`, `in_progress`, `submitted`, `locked` |
| `assigned_at` | datetime | When assigned |
| `deadline` | datetime or None | Optional review deadline |

### 4.2 `ReviewSubmission`

Captures a reviewer's judgement on one translation result.

| Field | Type | Notes |
|-------|------|-------|
| `submission_id` | UUID | Primary key |
| `assignment_id` | UUID | FK to ReviewAssignment |
| `result_id` | UUID | Which blinded translation was evaluated |
| `reviewer_id` | str | Pseudonymous ID (never real name in DB) |
| `overall_score` | int | 1–5 Likert scale |
| `error_categories` | List[str] | e.g. `["mistranslation", "omission", "register"]` |
| `correction_twi` | str or None | Reviewer's improved translation |
| `notes` | str or None | Free-text comments |
| `is_critical_error` | bool | True if the translation has a meaning-changing error |
| `submitted_at` | datetime | Submission timestamp |
| `is_locked` | bool | True after final submission; prevents edits |

### 4.3 `ReviewerSession`

Stores identity and authentication state for reviewers.

| Field | Type | Notes |
|-------|------|-------|
| `reviewer_id` | str | Pseudonymous stable ID |
| `display_name` | str | Optional display name for internal tracking |
| `role` | enum | `reviewer`, `lead_reviewer`, `admin` |
| `created_at` | datetime | Account creation |
| `last_active_at` | datetime | Last session activity |

---

## 5. Security Requirements

| Requirement | Implementation approach |
|-------------|------------------------|
| No public access to unpublished data | All API routes require a valid auth token |
| Secrets never in browser | JWT signed server-side; API keys only on server/worker |
| Reviewer cannot see engine identity | Engine name is stored encrypted or omitted from reviewer-facing API response; decrypted only after submission is locked |
| Duplicate submission prevention | `is_locked` flag set on first final submission; server rejects subsequent write attempts |
| Reviewer isolation | Each reviewer only sees their own assigned passages; no cross-reviewer result leakage |

---

## 6. Reviewer Workflow

```
1. Content lead uploads experiment results → hosted DB
2. Admin creates review assignments (one per reviewer per passage set)
3. Reviewer opens shared URL in browser → logs in
4. Reviewer sees assigned passages with blinded engine labels
5. Reviewer submits scores, corrections, notes
6. Reviewer marks assignment "complete" → record locked
7. Content lead views aggregated results and disagreement analysis
```

---

## 7. Hosting Options (Phase 4/5 Decision)

These are candidate options; a final decision will be made in Phase 4 based on team access, budget, and maintenance preference.

| Option | API Backend | Database | Frontend | Suitable for |
|--------|-------------|----------|----------|-------------|
| **Option A** | Railway / Render (FastAPI) | PostgreSQL (managed) | Static files on same host | Low-cost, easy setup |
| **Option B** | Fly.io (FastAPI) | Supabase (PostgreSQL) | Vercel or Netlify | Good free tiers |
| **Option C** | Google Cloud Run | Cloud SQL | Firebase Hosting | Scalable, GCP ecosystem |
| **Option D** | Self-hosted VPS | PostgreSQL on VPS | Nginx | Full control, minimal cost |

**Recommendation:** Option A or B for initial Phase 4 deployment. Migrate if scale demands it.

---

## 8. Phase 1 Compatibility Checklist

The following properties of Phase 1 schema design ensure forward compatibility:

- [x] `TranslationResult.result_id` is a UUID → can be FK in `ReviewSubmission`
- [x] `ExperimentRun.experiment_id` is a UUID → can be FK in `ReviewAssignment`
- [x] `BenchmarkPassage.passage_id` is a stable string ID → used in assignments
- [x] `TranslationResult` records engine provenance separately from passage data → blinding is straightforward (omit `engine_name` from reviewer-facing view)
- [x] No personally identifiable information (PII) in Phase 1 schemas
- [x] `ExperimentRun.configuration` is a JSON dict → stores environment snapshot
- [x] All timestamps use UTC → safe for multi-timezone reviewer access

---

## 9. What is NOT Built in Phase 1

- No hosted web application
- No hosted database
- No authentication system
- No review assignment management
- No reviewer-facing UI
- No API server

Phase 1 documents this design and ensures data contracts are compatible. Deployment begins in Phase 4.

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| **Blinded evaluation** | Reviewer does not know which engine produced which translation during evaluation |
| **Translation worker** | The local machine or process that runs OPUS-MT and calls Khaya |
| **Shared storage** | The hosted database accessible to both the translation worker (write) and reviewers (read/write) |
| **Content lead** | The person responsible for managing the review workflow and final publication decisions |
