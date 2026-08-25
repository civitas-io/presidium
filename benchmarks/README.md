# Presidium M8 performance benchmarks

Real, kept (not deleted after use, per this org's spike-code convention), reproducible harness
backing `docs/design/performance-research.md`. Two layers, matching the doc's own real/isolated
distinction:

- **`cel_microbench.py`** -- the isolated, no-network, no-HTTP `CelPolicyEngine.evaluate()`
  microbenchmark. Reproduces (and makes reproducible, since no prior script existed) the ~88µs/
  eval baseline `docs/vision/roadmap.md`'s M8 section cites.
- **`serve_m7.py`** -- boots a real, standalone M7 server (`HTTPGateway` + `PresidiumGatewayAgent`
  + `HealthCheckAgent`, real `civitas.Runtime`/`Supervisor`) with a configurable rule count,
  bound to a real port on a real host -- not a pytest fixture, a real long-running process
  suitable for hitting with an external, independent load generator.
- **`run_matrix.sh`** -- drives `ab` (Apache Bench, a real, separate process/connection per
  request, not asyncio tasks sharing one connection in the same process as the code under test)
  against a running `serve_m7.py` instance across a rule-count x concurrency matrix, saving raw
  output per cell.
- **`opa_equivalent.rego`** + **`run_opa_matrix.sh`** -- the one real, fair, same-hardware
  comparison point identified by the council session in `docs/design/performance-research.md`
  (OPA is free, open source, and independently replicable, unlike AGT/Kastra's internals).

## Usage

```bash
# Isolated CEL microbenchmark (no server, no network)
uv run --package presidium python benchmarks/cel_microbench.py --rules 20

# Real HTTP server, on this host or a remote one
uv run --package presidium python benchmarks/serve_m7.py --port 8080 --rules 20 --no-mtls

# From a separate machine/process, against the server above
./benchmarks/run_matrix.sh http://<host>:8080 results/
```

See `docs/design/performance-research.md` for the real, dated results and recommendation this
harness produced -- this directory is the reusable *mechanism*, not the findings themselves.
