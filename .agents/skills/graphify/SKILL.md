---
name: graphify
description: Navigate and maintain the repository's Graphify code-relationship graph. Use before reading or changing implementation code in this project, when tracing execution paths, and after every code change.
---

# Graphify workflow

Use Graphify as the first source for code discovery; do not substitute raw file search for implementation exploration.

1. Check freshness before code inspection:
   - Read `graphify-out/GRAPH_REPORT.md` and compare its `Built from commit` value with `git rev-parse HEAD`.
   - If they differ, run `graphify update .`. Stop and report the failure if the command fails or is unavailable.
2. Query the graph for the subsystem, entry point, and persistence/admin paths relevant to the request. Use the generated graph/report to identify the exact symbols before opening implementation files.
3. Read only the implementation files identified by that query.
4. After each code change, run `graphify update .`, then query the changed symbol and its callers/callees again. Stop and report a Graphify failure; do not fall back to unstructured code search.

## Project graph locations

- `graphify-out/GRAPH_REPORT.md`: freshness record and high-level navigation.
- `graphify-out/graph.json`: symbol and relationship graph.
- `graphify-out/.graphify_analysis.json`: communities and cross-cutting relationships.
- `graphify-out/manifest.json`: file hashes used by the current graph.

For an IV-surface task, begin with `run_iv_surface`, `process_run`, `load_inputs`, `update_run`, `insert_run`, `insert_points`, and the IV admin/routes nodes, then follow the graph edges to identify status and persistence behavior.
