# Field storage

Production JSON demo fixtures have been removed. Fields and account selections
are stored in SQL tables; no catalog entries are seeded automatically.
See [persistent fields](../../docs/field-storage.md) for the schema and API contract.
Estimator test inputs live under `tests/`. Explicitly requested temporary UI
samples can be added with `scripts/seed_field_samples.py` and removed with its
`--restore` option; see the persistent-fields document. No samples run automatically.
