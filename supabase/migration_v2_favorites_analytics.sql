-- Job Hunter v2 — Favorites, RAG Support, Analytics
-- Run AFTER migration.sql

-- ============================================
-- FAVORITES & TAGGING
-- ============================================

-- Mark applications as favorites for RAG prioritization
ALTER TABLE applications ADD COLUMN is_favorite BOOLEAN DEFAULT FALSE;
ALTER TABLE applications ADD COLUMN tags TEXT[] DEFAULT '{}';

-- Mark individual materials (resumes/CLs) as favorites
-- Favorited materials get prioritized in future tailoring context
ALTER TABLE materials ADD COLUMN is_favorite BOOLEAN DEFAULT FALSE;
ALTER TABLE materials ADD COLUMN quality_notes TEXT;  -- "strong opening", "good keyword density", etc.

-- ============================================
-- INTERVIEW & RESPONSE TRACKING
-- ============================================

ALTER TABLE applications ADD COLUMN response_received BOOLEAN DEFAULT FALSE;
ALTER TABLE applications ADD COLUMN response_date TIMESTAMPTZ;
ALTER TABLE applications ADD COLUMN interview_date TIMESTAMPTZ;
ALTER TABLE applications ADD COLUMN interview_type TEXT;  -- phone, video, onsite, panel, technical
ALTER TABLE applications ADD COLUMN interview_notes TEXT;
ALTER TABLE applications ADD COLUMN offer_amount TEXT;
ALTER TABLE applications ADD COLUMN offer_date TIMESTAMPTZ;

-- ============================================
-- INDEXES FOR ANALYTICS & RAG
-- ============================================

CREATE INDEX idx_applications_favorite ON applications(is_favorite) WHERE is_favorite = TRUE;
CREATE INDEX idx_materials_favorite ON materials(is_favorite) WHERE is_favorite = TRUE;
CREATE INDEX idx_applications_tags ON applications USING gin(tags);
CREATE INDEX idx_applications_response ON applications(response_received, response_date);

-- ============================================
-- ANALYTICS VIEWS
-- ============================================

-- Response rate by month
CREATE VIEW monthly_analytics AS
SELECT 
  DATE_TRUNC('month', created_at) AS month,
  COUNT(*) AS total_applied,
  COUNT(*) FILTER (WHERE response_received = TRUE) AS responses,
  COUNT(*) FILTER (WHERE status = 'interviewing') AS interviews,
  COUNT(*) FILTER (WHERE status = 'offer') AS offers,
  COUNT(*) FILTER (WHERE status = 'rejected') AS rejections,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE response_received = TRUE) / NULLIF(COUNT(*), 0), 1
  ) AS response_rate_pct,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status IN ('interviewing', 'offer')) / NULLIF(COUNT(*), 0), 1
  ) AS interview_rate_pct
FROM applications
WHERE status != 'saved'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month DESC;

-- Platform effectiveness
CREATE VIEW platform_analytics AS
SELECT
  COALESCE(platform, 'Unknown') AS platform,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE response_received = TRUE) AS responses,
  COUNT(*) FILTER (WHERE status IN ('interviewing', 'offer')) AS advanced,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE response_received = TRUE) / NULLIF(COUNT(*), 0), 1
  ) AS response_rate_pct
FROM applications
WHERE status != 'saved'
GROUP BY platform
ORDER BY total DESC;

-- Favorite materials for RAG retrieval
CREATE VIEW favorite_materials AS
SELECT
  m.id AS material_id,
  m.type,
  m.content_md,
  m.quality_notes,
  a.company,
  a.role_title,
  a.status,
  a.tags
FROM materials m
JOIN applications a ON a.id = m.application_id
WHERE m.is_favorite = TRUE
ORDER BY m.created_at DESC;

-- Full application detail view (for dashboard)
CREATE VIEW application_details AS
SELECT
  a.id,
  a.company,
  a.role_title,
  a.jd_url,
  a.platform,
  a.location,
  a.salary_range,
  a.status,
  a.is_favorite,
  a.tags,
  a.applied_at,
  a.follow_up_at,
  a.response_received,
  a.response_date,
  a.interview_date,
  a.interview_type,
  a.offer_amount,
  a.created_at,
  a.updated_at,
  a.notes,
  -- Aggregated materials
  (SELECT COUNT(*) FROM materials m WHERE m.application_id = a.id AND m.type = 'resume') AS resume_count,
  (SELECT COUNT(*) FROM materials m WHERE m.application_id = a.id AND m.type = 'cover_letter') AS cover_letter_count,
  (SELECT bool_or(m.is_favorite) FROM materials m WHERE m.application_id = a.id) AS has_favorite_material,
  -- Days since applied (for follow-up tracking)
  CASE 
    WHEN a.applied_at IS NOT NULL 
    THEN EXTRACT(DAY FROM NOW() - a.applied_at)::INT
    ELSE NULL
  END AS days_since_applied,
  -- Overdue flag
  CASE
    WHEN a.follow_up_at IS NOT NULL AND a.follow_up_at < NOW() AND a.status = 'applied'
    THEN TRUE
    ELSE FALSE
  END AS follow_up_overdue
FROM applications a
ORDER BY a.created_at DESC;
