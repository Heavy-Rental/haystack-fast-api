# Academy/paid compose vendors pack sync and Neo4j populate workers

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-28 |
| **Deciders** | haystack-fast-api |
| **Trace** | HR-244; FR-PDH-010; FR-KG-011 persist; S4 T0–T2; S8.1 T3; S8.2 T4 |
| **OpenSpec** | [`../specs/project-setup/spec.md`](../specs/project-setup/spec.md); [`../specs/portal-dual-hop/spec.md`](../specs/portal-dual-hop/spec.md) |
| **Change** | [`../changes/archive/2026-08-28-hr-244-deploy-pipeline-sync-workers/`](../changes/archive/2026-08-28-hr-244-deploy-pipeline-sync-workers/) |

## Context and Problem Statement

Academy/paid compose started `postgres-haystack-sync` and `neo4j-populate` with `python -m postgres_haystack_sync` / `python -m neo4j_populate` from the FastAPI uvicorn image. Those modules are not in the `app` package, so the sidecars crash-looped and fleet data never reached Haystack Postgres or Neo4j.

The jobs originated in the **config pack** (devcontainer). The FastAPI service is a reader/client (`FLEET_BACKEND=sql`, `trigger_neo4j_populate` POST). Deploy still needs the workers on the Haystack host.

## Considered Options

* Keep `python -m` in the uvicorn image and add the modules to this Python package
* Require the config pack on the academy/paid guest
* Vendor pack scripts into the Ansible role and run them in dedicated images

## Decision Outcome

Chosen option: **vendor pack scripts into `deploy-pipeline/ansible/roles/haystack`**.

| Plane | Owner |
|-------|--------|
| Local / devcontainer compose | Config pack (`heavy-rental-devcontainer-configuration` / Haystack-Fast-API) |
| Academy/paid compose sidecars | This repo: Ansible copies `sync-from-primary.sh`, `populate_neo4j.py`, `populate-neo4j-from-haystack.sh` to `{{ compose_dir }}/workers/` |
| FastAPI request path | Still does **not** run ETL. `trigger_neo4j_populate` POSTs `NEO4J_POPULATE_URL`; `neo4j_cypher_read` reads Bolt |

Compose rules that stay:

* `postgres-haystack-sync` uses `postgres:17` + bash entrypoint (not the uvicorn image)
* `neo4j-populate` uses `python:3.12-slim` + wrapper (not `python -m neo4j_populate`)
* This compose file MUST NOT start a `neo4j:` service (Neo4j remains estate / pack)
* Haystack `GET :8000/health` remains the ALB gate; worker `ps` MUST NOT fail the play

### Consequences

* Good: academy/paid guests get the same merge-sync and SQL→Cypher jobs as local compose without putting ETL in `app/`.
* Bad / accepted: this repo holds **copies** of pack scripts; pack remains the job origin. `neo4j-populate` installs pip deps on container start. Pack D0 singular table names (`asset,booking,category`) vs haystack ORM plural tables remains a follow-up.
