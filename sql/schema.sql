-- ============================================================
-- OS&D AI-Assisted Exception Prioritization - Database Schema
-- ============================================================
-- Run this file against your PostgreSQL database to set up
-- all required tables. Safe to re-run (uses IF NOT EXISTS).
-- ============================================================

-- 1. Exception Scores
--    Stores the computed score for each unique exception.
CREATE TABLE IF NOT EXISTS exception_scores (
    exception_hash  TEXT PRIMARY KEY,
    osd_number      TEXT,
    score           INT NOT NULL,
    bucket          TEXT NOT NULL,
    reason          TEXT,
    model_version   TEXT,
    features_snapshot JSONB,
    semantic_severity TEXT,
    risk_flags      JSONB,
    created_at      TIMESTAMP DEFAULT now()
);

-- Ensure new columns exist on older databases (safe to re-run)
ALTER TABLE IF EXISTS exception_scores
    ADD COLUMN IF NOT EXISTS semantic_severity TEXT;

ALTER TABLE IF EXISTS exception_scores
    ADD COLUMN IF NOT EXISTS risk_flags JSONB;

-- 2. Exception Feedback
--    Stores user feedback (+1 / -1) linked to an exception hash.
CREATE TABLE IF NOT EXISTS exception_feedback (
    id              SERIAL PRIMARY KEY,
    exception_hash  TEXT NOT NULL,
    features_snapshot JSONB,
    feedback        INT NOT NULL,           -- +1 or -1
    created_at      TIMESTAMP DEFAULT now(),
    processed_at    TIMESTAMP,
    processed_model_version TEXT
);

-- Ensure new columns exist on older databases (safe to re-run)
ALTER TABLE IF EXISTS exception_feedback
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP;

ALTER TABLE IF EXISTS exception_feedback
    ADD COLUMN IF NOT EXISTS processed_model_version TEXT;

-- 3. AI Model State (single-row table)
--    Holds the current model version, learned weights, and metadata.
CREATE TABLE IF NOT EXISTS ai_model_state (
    id              INT PRIMARY KEY DEFAULT 1,
    model_version   TEXT NOT NULL,
    weights         JSONB NOT NULL,
    trained_at      TIMESTAMP,
    feedback_count  INT DEFAULT 0
);

-- Seed the initial model state (v1.0 default weights) if not present.
INSERT INTO ai_model_state (id, model_version, weights, trained_at, feedback_count)
VALUES (
    1,
    'v1.0',
    '{
        "hazmatFlag": 3.5,
        "highValue": 2.5,
        "value1k": 1.0,
        "agingOver48h": 1.5,
        "agingOver96h": 2.5,
        "largeShipment": 1.2,
        "stalledInvestigation": 1.5,
        "activeInvestigation": 0.5,
        "recoveryInProgress": -1.0,
        "congestedRegion": 1.0
    }'::jsonb,
    now(),
    0
)
ON CONFLICT (id) DO NOTHING;

-- 4. CSV Upload Audit
--    Tracks every upload lifecycle for operational observability.
CREATE TABLE IF NOT EXISTS csv_uploads (
    id                  BIGSERIAL PRIMARY KEY,
    upload_name         TEXT NOT NULL,
    source_system       TEXT,
    upload_status       TEXT NOT NULL DEFAULT 'processing',
    total_rows          INT NOT NULL DEFAULT 0,
    unique_rows         INT NOT NULL DEFAULT 0,
    new_rows            INT NOT NULL DEFAULT 0,
    duplicate_rows      INT NOT NULL DEFAULT 0,
    processing_seconds  NUMERIC(10, 3),
    uploaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    completed_at        TIMESTAMP,
    error_message       TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_csv_uploads_uploaded_at
    ON csv_uploads(uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_csv_uploads_status
    ON csv_uploads(upload_status);

-- 5. Normalized Exception Records
--    Stores the raw + normalized operational investigation context.
CREATE TABLE IF NOT EXISTS exception_records (
    exception_hash          TEXT PRIMARY KEY,
    upload_id               BIGINT REFERENCES csv_uploads(id) ON DELETE SET NULL,
    exception_type          TEXT,
    exception_sequence      TEXT,
    pro_number              TEXT,
    osd_number              TEXT,
    terminal                TEXT,
    event_date              TEXT,
    investigation_notes     TEXT,
    investigation_answers   JSONB,
    operational_metadata    JSONB,
    raw_payload             JSONB,
    root_cause              TEXT,
    recommendation          TEXT,
    confidence_score        NUMERIC(5, 2),
    ai_status               TEXT NOT NULL DEFAULT 'processed',
    created_at              TIMESTAMP NOT NULL DEFAULT now(),
    updated_at              TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exception_records_type
    ON exception_records(exception_type);

CREATE INDEX IF NOT EXISTS idx_exception_records_terminal
    ON exception_records(terminal);

CREATE INDEX IF NOT EXISTS idx_exception_records_created_at
    ON exception_records(created_at DESC);


-- ============================================================
-- Root Cause Categorization & Prevention Engine Tables
-- ============================================================

-- 6. Exception Master
--    Central registry for all exceptions across all types (OV, NB, AS, DS, BNF, PR, RD, RF, DD, OH, MSD)
CREATE TABLE IF NOT EXISTS exception_master (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) NOT NULL,
    exception_category  VARCHAR(50),  -- Mapped from type_code (Overage, Shortage, Damage, On-Hand, Misdelivery)
    entry_user          VARCHAR(100),
    entry_status        VARCHAR(50),  -- Complete, In Progress, etc.
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exception_master_pronumber
    ON exception_master(pronumber);

CREATE INDEX IF NOT EXISTS idx_exception_master_type_code
    ON exception_master(type_code);

CREATE INDEX IF NOT EXISTS idx_exception_master_created_at
    ON exception_master(created_at DESC);


-- 7. Investigation: OV (Overage)
--    Structured investigation responses for OV exception type
CREATE TABLE IF NOT EXISTS investigation_ov (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'OV' NOT NULL,
    
    -- OD400 (Freight on Hand) Check
    od400_chk           VARCHAR(5),
    od400_chk_resp      TEXT,
    
    -- Bill (BL) Check
    bl_chk              VARCHAR(5),
    bl_chk_resp         TEXT,
    
    -- Delivery (DR) Check
    dr_chk              VARCHAR(5),
    dr_chk_resp         TEXT,
    
    -- Proof of Service (PS) Check
    ps_chk              VARCHAR(5),
    ps_chk_resp         TEXT,
    
    -- Consignee Check
    consignee_chk       VARCHAR(5),
    consignee_chk_resp  TEXT,
    
    -- Shipment Check
    shipmentchk         VARCHAR(5),
    shipmentchk_resp    TEXT,
    
    -- Metadata
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_ov_pronumber
    ON investigation_ov(pronumber);


-- 8. Investigation: NB (No Bill)
--    Placeholder for NB exception type
--    TODO: Add CHK/CHK_RESP columns when NB data file is provided
CREATE TABLE IF NOT EXISTS investigation_nb (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'NB' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_nb_pronumber
    ON investigation_nb(pronumber);


-- 9. Investigation: AS (All Short)
--    Placeholder for AS exception type
--    TODO: Add CHK/CHK_RESP columns when AS data file is provided
CREATE TABLE IF NOT EXISTS investigation_as (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'AS' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_as_pronumber
    ON investigation_as(pronumber);


-- 10. Investigation: DS (Delivery Short)
--     Placeholder for DS exception type
--     TODO: Add CHK/CHK_RESP columns when DS data file is provided
CREATE TABLE IF NOT EXISTS investigation_ds (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'DS' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_ds_pronumber
    ON investigation_ds(pronumber);


-- 11. Investigation: BNF (Bill No Freight)
--     Placeholder for BNF exception type
--     TODO: Add CHK/CHK_RESP columns when BNF data file is provided
CREATE TABLE IF NOT EXISTS investigation_bnf (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'BNF' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_bnf_pronumber
    ON investigation_bnf(pronumber);


-- 12. Investigation: PR (Partial Refusal)
--     Placeholder for PR exception type
--     TODO: Add CHK/CHK_RESP columns when PR data file is provided
CREATE TABLE IF NOT EXISTS investigation_pr (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'PR' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_pr_pronumber
    ON investigation_pr(pronumber);


-- 13. Investigation: RD (Refused Damage)
--     Placeholder for RD exception type
--     TODO: Add CHK/CHK_RESP columns when RD data file is provided
CREATE TABLE IF NOT EXISTS investigation_rd (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'RD' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_rd_pronumber
    ON investigation_rd(pronumber);


-- 14. Investigation: RF (Arbitrary Refusal)
--     Placeholder for RF exception type
--     TODO: Add CHK/CHK_RESP columns when RF data file is provided
CREATE TABLE IF NOT EXISTS investigation_rf (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'RF' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_rf_pronumber
    ON investigation_rf(pronumber);


-- 15. Investigation: DD (Delivered Damage)
--     Placeholder for DD exception type
--     TODO: Add CHK/CHK_RESP columns when DD data file is provided
CREATE TABLE IF NOT EXISTS investigation_dd (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'DD' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_dd_pronumber
    ON investigation_dd(pronumber);


-- 16. Investigation: OH (On Hand)
--     Placeholder for OH exception type
--     TODO: Add CHK/CHK_RESP columns when OH data file is provided
CREATE TABLE IF NOT EXISTS investigation_oh (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'OH' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_oh_pronumber
    ON investigation_oh(pronumber);


-- 17. Investigation: MSD (Misdelivery)
--     Placeholder for MSD exception type
--     TODO: Add CHK/CHK_RESP columns when MSD data file is provided
CREATE TABLE IF NOT EXISTS investigation_msd (
    id                  SERIAL PRIMARY KEY,
    pronumber           VARCHAR(20) NOT NULL,
    type_code           VARCHAR(5) DEFAULT 'MSD' NOT NULL,
    
    error_message       TEXT,
    date_added          TIMESTAMP,
    date_updated        TIMESTAMP,
    entry_status        VARCHAR(50),
    entry_user          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_investigation_msd_pronumber
    ON investigation_msd(pronumber);


-- 18. AI Analysis Results
--     Stores root cause classifications and prevention recommendations
CREATE TABLE IF NOT EXISTS ai_analysis_results (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pronumber                   VARCHAR(20) NOT NULL,
    exception_number            VARCHAR(20),  -- Primary identifier from source data
    type_code                   VARCHAR(5) NOT NULL,
    exception_category          VARCHAR(50),
    
    -- Analysis Results
    root_cause                  VARCHAR(100) NOT NULL,
    root_cause_summary          TEXT,  -- Concise summary of root cause conclusion
    confidence                  VARCHAR(10),  -- 'High' | 'Medium' | 'Low'
    reasoning                   TEXT,
    analysis                    TEXT,  -- 2-4 sentence explanation of evidence to conclusion
    
    -- Structured Data (JSONB)
    supporting_evidence         JSONB,  -- Array of evidence items
    prevention_recommendations  JSONB,  -- Array of recommendation strings
    key_signals                 JSONB,  -- Array of {check_code, answer, signal}
    
    -- Metadata
    analyzed_at                 TIMESTAMP NOT NULL,
    model_used                  VARCHAR(50),  -- e.g., 'ollama:mistral', 'gpt-3.5-turbo'
    created_at                  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_pronumber
    ON ai_analysis_results(pronumber);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_exception_number
    ON ai_analysis_results(exception_number);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_type_code
    ON ai_analysis_results(type_code);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_created_at
    ON ai_analysis_results(created_at DESC);

