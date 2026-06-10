"""api/integrations — connectors that let the brain read the operator's external
world (Google Gmail + Calendar, read-only in v0). Each connector stores its
credentials in the settings sidecar and exposes read helpers that the tool layer
wraps as untrusted reference data."""
