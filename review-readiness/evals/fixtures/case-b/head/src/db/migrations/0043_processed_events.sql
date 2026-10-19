CREATE TABLE processed_events (
  event_id     TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_processed_events_event_id ON processed_events(event_id);
