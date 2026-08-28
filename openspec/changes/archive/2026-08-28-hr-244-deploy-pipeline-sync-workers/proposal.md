# Proposal: HR-244 deploy-pipeline vendors pack sync workers (as-built stamp)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** |
| **Date** | 2026-08-28 |
| **Ticket** | HR-244 |
| **MADR** | [`../../../adrs/0012-deploy-pipeline-vendors-pack-sync-workers.md`](../../../adrs/0012-deploy-pipeline-vendors-pack-sync-workers.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

S4 T0–T2 and S8.1–S8.2 stamped pack compose as the only home for `postgres-haystack-sync` and `neo4j-populate`. Academy/paid deploy in this repo then started those services with `python -m` from the uvicorn image. The modules do not exist in `app/`, so sidecars crash-looped.

HR-244 vendors the pack scripts into the Ansible haystack role and runs them in dedicated images. Specs and engineer docs must stop saying “config pack only” without the deploy-pipeline copy.

## What was verified

| Item | This repo |
|------|-----------|
| Scripts | `deploy-pipeline/ansible/roles/haystack/files/sync-from-primary.sh`, `populate_neo4j.py`, `populate-neo4j-from-haystack.sh` |
| Ansible | copy to `{{ compose_dir }}/workers/`; SOURCE/TARGET/PG env aliases; 60s poll + post-sync populate defaults |
| Compose | `postgres:17` + bash sync; `python:3.12-slim` + populate wrapper; `restart: unless-stopped`; no `neo4j:` service |
| App | unchanged — still POSTs `NEO4J_POPULATE_URL`; still does not run ETL in request handlers |

## Out of scope

- Moving ETL into the FastAPI `app` package
- Starting Neo4j on the Haystack guest
- Aligning pack singular table names with haystack ORM plurals
