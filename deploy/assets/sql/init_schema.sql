-- RFP Summarizer SQL Schema
-- Mirrors the OpenAI function-call output structure.
-- Run once against the target database after creation.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_runs')
CREATE TABLE rfp_runs (
    run_id          NVARCHAR(20)    NOT NULL PRIMARY KEY,   -- e.g. 20260318_175934
    rfp_blob_name   NVARCHAR(500)   NOT NULL,
    summary         NVARCHAR(MAX)   NULL,
    chunking_enabled BIT            NOT NULL DEFAULT 0,
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_fees')
CREATE TABLE rfp_fees (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    fee_type        NVARCHAR(200)   NOT NULL,
    fee             NVARCHAR(MAX)   NOT NULL,
    pages           NVARCHAR(500)   NULL        -- JSON array of ints, e.g. [1,3,5]
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_dates')
CREATE TABLE rfp_dates (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    date_type       NVARCHAR(200)   NOT NULL,
    date_value      NVARCHAR(500)   NOT NULL,
    pages           NVARCHAR(500)   NULL
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_best_lead_orgs')
CREATE TABLE rfp_best_lead_orgs (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    reason          NVARCHAR(MAX)   NOT NULL,
    best_lead_org   NVARCHAR(500)   NOT NULL,
    pages           NVARCHAR(500)   NULL
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_cross_sell_opps')
CREATE TABLE rfp_cross_sell_opps (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    reason          NVARCHAR(MAX)   NOT NULL,
    cross_sell_opp  NVARCHAR(MAX)   NOT NULL,
    pages           NVARCHAR(500)   NULL
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_capabilities')
CREATE TABLE rfp_capabilities (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    reason          NVARCHAR(MAX)   NOT NULL,
    capability      NVARCHAR(MAX)   NOT NULL,
    pages           NVARCHAR(500)   NULL
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'rfp_diversity_allocation')
CREATE TABLE rfp_diversity_allocation (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    run_id          NVARCHAR(20)    NOT NULL REFERENCES rfp_runs(run_id) ON DELETE CASCADE,
    reason          NVARCHAR(MAX)   NOT NULL,
    has_diversity   BIT             NOT NULL DEFAULT 0,
    pages           NVARCHAR(500)   NULL
);
GO

-- Indexes for common query patterns
CREATE NONCLUSTERED INDEX IX_rfp_fees_run        ON rfp_fees(run_id);
CREATE NONCLUSTERED INDEX IX_rfp_dates_run       ON rfp_dates(run_id);
CREATE NONCLUSTERED INDEX IX_rfp_lead_orgs_run   ON rfp_best_lead_orgs(run_id);
CREATE NONCLUSTERED INDEX IX_rfp_cross_sell_run  ON rfp_cross_sell_opps(run_id);
CREATE NONCLUSTERED INDEX IX_rfp_capabilities_run ON rfp_capabilities(run_id);
CREATE NONCLUSTERED INDEX IX_rfp_diversity_run   ON rfp_diversity_allocation(run_id);
GO
