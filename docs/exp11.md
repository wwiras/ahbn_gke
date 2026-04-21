# Exp11 - Churn in Kubernetes

This experiment validates AHBN under pod churn in Kubernetes. Unlike Exp10, which injects a single failure, Exp11 deletes and recreates multiple peer pods during an active multi-message dissemination run.

## Recommended configuration
- Topology: BA, `baM: 2`
- Nodes: 20
- Clusters: 4
- Workload: 6 messages, 0.8s spacing
- Churn: 3 events, 1.0s spacing, mixed CH/non-CH targets

## Run
```bash
IMAGE=wwiras/ahbn-peer:v11 ./scripts/run_exp11.sh
```

## Expected outputs
- `exp11_summary.csv`
- `exp11_timeline.png`
- `exp11_adaptation.png`
- `logs.jsonl`

## Expected behavior
- AHBN should show visible `failure_reaction`, `mode_switched`, and `fanout_changed` events shortly after churn.
- Delivery should continue despite pod deletion because the StatefulSet recreates the pod and AHBN temporarily becomes more gossip-heavy.
- Duplicates will rise versus stable runs, but not catastrophically.
