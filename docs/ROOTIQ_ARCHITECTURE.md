# RootIQ Enterprise Architecture Baseline

## Scope
- Current productionized POC scope: OV and NB exception categories.
- Architecture is category-agnostic and supports future templates (shortage, damage, misdelivery, on-hand).

## Workflow
1. External AS400 workflow exports investigation CSV.
2. RootIQ upload endpoint accepts CSV.
3. CSV rows are cleaned and validated.
4. SHA256 hash is generated per normalized row.
5. Existing hashes are reused (no duplicate AI processing).
6. New hashes are scored and enriched with AI outputs.
7. Upload lifecycle and dedup statistics are recorded.
8. Dashboard and insight APIs serve analytics.

## Key Backend Modules
- app/routes/ai.py: upload, scoring, analytics, detail APIs.
- app/services/insights.py: root cause and recommendation inference.
- app/services/analytics.py: dashboard query orchestration.
- app/hashing.py: deterministic SHA256 hash generation.
- sql/schema.sql: exception, feedback, upload audit, normalized records.
- sql/queries.sql: ingestion and analytics SQL contracts.

## API Contracts (v2)
- POST /api/ai/exceptions/upload
  - Input: multipart file (.csv)
  - Output: list of scored exceptions
- GET /api/ai/exceptions
  - Output: scored exception table data
- GET /api/ai/exceptions/{exception_hash}
  - Output: normalized detail with investigation context and AI outputs
- GET /api/ai/uploads/history
  - Output: upload processing lifecycle records
- GET /api/ai/analytics/summary
  - Output: KPI counters for dashboard
- GET /api/ai/analytics/root-causes
  - Output: root cause distribution
- GET /api/ai/analytics/terminal-risk
  - Output: terminal risk counts/confidence
- GET /api/ai/analytics/severity
  - Output: priority bucket distribution
- GET /api/ai/analytics/monthly-trends
  - Output: monthly trend series

## Hashing and Dedup Strategy
Hash input fields currently include:
- osdNumber, osdType, proNumber, manifest, trailer
- origin, destination, regionTerminal
- entryDate, createdDate, lastUpdatedDate
- totalValue, totalPieces, weight
- investigationStatus
- commodity, description, remarks

Algorithm:
- Canonicalize values with trim + stable field order.
- Join with delimiter.
- Apply SHA256 to produce exception_hash.

Dedup behavior:
- Existing hash: skip duplicate AI scoring, reuse stored result.
- New hash: score/enrich/store and expose through analytics.

## Database Additions
- csv_uploads: upload audit and processing metrics.
- exception_records: normalized exception context + AI root cause data.
- exception_scores and exception_feedback continue to power scoring feedback loop.

## Frontend Baseline Modules
- Dashboard: KPI, trend, root-cause charts.
- Exceptions: DataGrid with detail drawer.
- Upload Center: drag-and-drop upload and audit history.
- AI Insights: root cause cluster, terminal risk, severity charts.
- Login: lightweight enterprise entry screen for POC.
