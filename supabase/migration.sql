-- Job Hunter — Supabase Schema
-- Run this migration to set up the tracking database

-- Application status enum
CREATE TYPE application_status AS ENUM (
  'saved',       -- JD saved, not yet tailored
  'intake',      -- JD parsed and stored
  'tailored',    -- Resume/CL customized
  'ready',       -- PDFs generated, ready to submit
  'applied',     -- Submitted
  'interviewing',-- In interview process
  'rejected',    -- Rejected or ghosted
  'offer',       -- Received offer
  'withdrawn'    -- Withdrew application
);

-- Material type enum
CREATE TYPE material_type AS ENUM (
  'resume',
  'cover_letter'
);

-- ============================================
-- APPLICATIONS TABLE
-- Every job applied for with link, tracked here
-- ============================================
CREATE TABLE applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Job details
  company TEXT NOT NULL,
  role_title TEXT NOT NULL,
  jd_url TEXT NOT NULL,                    -- REQUIRED: the job listing link
  jd_text TEXT,                            -- Full JD for future context
  platform TEXT,                           -- LinkedIn, Workday, Greenhouse, direct, etc.
  location TEXT,                           -- Remote, hybrid, on-site + city
  salary_range TEXT,                       -- As listed or researched
  clearance_required TEXT,                 -- None, public trust, secret, etc.
  
  -- Status tracking
  status application_status DEFAULT 'saved',
  applied_at TIMESTAMPTZ,                  -- When actually submitted
  follow_up_at TIMESTAMPTZ,                -- When to follow up
  
  -- Contacts
  recruiter_name TEXT,
  recruiter_email TEXT,
  referral_source TEXT,                    -- Who referred / how found
  
  -- Notes
  notes TEXT,                              -- Knockout questions, interview notes, etc.
  rejection_reason TEXT,                   -- If rejected, why (for pattern analysis)
  
  -- JD analysis (structured)
  jd_keywords JSONB DEFAULT '[]',          -- [{keyword, category}] extracted from JD
  
  -- Meta
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- MATERIALS TABLE
-- Every resume and cover letter ever generated
-- Stored with full markdown for context retrieval
-- ============================================
CREATE TABLE materials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
  
  -- Content
  type material_type NOT NULL,
  filename TEXT NOT NULL,                  -- e.g., resume.pdf, cover_letter.pdf
  content_md TEXT NOT NULL,                -- Full markdown source for context retrieval
  file_path TEXT,                          -- Local path to PDF
  version INT DEFAULT 1,                  -- Version number if revised
  
  -- Meta
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_company ON applications(company);
CREATE INDEX idx_applications_created ON applications(created_at DESC);
CREATE INDEX idx_applications_follow_up ON applications(follow_up_at) 
  WHERE follow_up_at IS NOT NULL AND status = 'applied';
CREATE INDEX idx_materials_application ON materials(application_id);
CREATE INDEX idx_materials_type ON materials(type);

-- Full text search on JD content for finding similar past applications
ALTER TABLE applications ADD COLUMN jd_search tsvector 
  GENERATED ALWAYS AS (to_tsvector('english', COALESCE(jd_text, '') || ' ' || COALESCE(role_title, '') || ' ' || COALESCE(company, ''))) STORED;
CREATE INDEX idx_applications_jd_search ON applications USING gin(jd_search);

-- Full text search on materials for retrieving past resumes/CLs by content
ALTER TABLE materials ADD COLUMN content_search tsvector
  GENERATED ALWAYS AS (to_tsvector('english', COALESCE(content_md, ''))) STORED;
CREATE INDEX idx_materials_content_search ON materials USING gin(content_search);

-- ============================================
-- AUTO-UPDATE updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER applications_updated_at
  BEFORE UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- USEFUL VIEWS
-- ============================================

-- Pipeline summary
CREATE VIEW pipeline_summary AS
SELECT 
  status,
  COUNT(*) as count,
  array_agg(company || ' - ' || role_title ORDER BY created_at DESC) as roles
FROM applications
GROUP BY status
ORDER BY 
  CASE status
    WHEN 'saved' THEN 1
    WHEN 'intake' THEN 2
    WHEN 'tailored' THEN 3
    WHEN 'ready' THEN 4
    WHEN 'applied' THEN 5
    WHEN 'interviewing' THEN 6
    WHEN 'offer' THEN 7
    WHEN 'rejected' THEN 8
    WHEN 'withdrawn' THEN 9
  END;

-- Overdue follow-ups
CREATE VIEW overdue_followups AS
SELECT 
  company,
  role_title,
  applied_at,
  follow_up_at,
  NOW() - follow_up_at AS overdue_by
FROM applications
WHERE status = 'applied'
  AND follow_up_at < NOW()
ORDER BY follow_up_at ASC;
