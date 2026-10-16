CREATE TABLE facility_catalog_versions (
  report_id TEXT NOT NULL REFERENCES analysis_reports(id),
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  catalog_json TEXT NOT NULL,
  PRIMARY KEY(report_id, version)
);
CREATE TABLE semantic_reviews (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES analysis_reports(id),
  created_at TEXT NOT NULL,
  review_json TEXT NOT NULL
);
CREATE TABLE resident_observations (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES analysis_reports(id),
  created_at TEXT NOT NULL,
  observation_json TEXT NOT NULL,
  image_base64 TEXT
);
CREATE TABLE governance_audit (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES analysis_reports(id),
  catalog_version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  event_json TEXT NOT NULL
);
CREATE TABLE audience_reports (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES analysis_reports(id),
  audience TEXT NOT NULL,
  created_at TEXT NOT NULL,
  document_json TEXT NOT NULL
);
