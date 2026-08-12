# Project Environment & Setup (moved)

> **This document has moved.** Canonical location: [../openspec/specs/project-setup/spec.md](../openspec/specs/project-setup/spec.md)

Standards: **OpenSpec** · **GitHub Spec-kit** · **OpenSPDD**

See also: [specification/README.md](./README.md) · [openspec/AGENTS.md](../openspec/AGENTS.md)

### Pointer — default pytest (2026-08-12)

| Topic | Canonical |
|-------|-----------|
| CI-safe suite, no optional markers | [project-setup spec — Default pytest suite](../openspec/specs/project-setup/spec.md) |
| `tests/conftest.py` isolation (mock embedder, dim 384, stub agents) | [project-setup design — Test](../openspec/specs/project-setup/design.md) |
| Vector store/query dim match | [knowledge-graph spec](../openspec/specs/knowledge-graph/spec.md) · [indexing FR-IX-015](../openspec/specs/indexing/spec.md) |

```bash
cd haystack-fast-api
uv run pytest tests/ -q
```
