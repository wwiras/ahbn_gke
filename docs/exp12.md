# Exp12 - Mixed Resource Heterogeneity in Kubernetes

This experiment validates AHBN under heterogeneous resource conditions in Kubernetes. Unlike Exp10 (failure realism) and Exp11 (churn realism), Exp12 evaluates whether AHBN can sustain dissemination when a subset of peers experiences degraded forwarding capability due to simulated resource pressure.

The experiment injects additional forwarding delay into selected low-resource peers during an active multi-message dissemination workload. AHBN is expected to react adaptively by increasing forwarding aggressiveness and temporarily shifting toward more gossip-oriented dissemination behavior.

## Recommended configuration
- Topology: BA, `baM: 2`
- Nodes: 20
- Clusters: 4
- Workload: 30 messages, 0.5s spacing
- Resource stress:
  - 6 low-resource peers
  - `350ms` overload delay
  - trigger at `0.6s`
- Settle time: `25s`

## Run
```bash
IMAGE=wwiras/ahbn-peer:v20 ./scripts/run_exp12.sh
```

## Repeatability recommendation
For thesis-quality evaluation, repeat the experiment across multiple executions:

```bash
for i in {1..10}; do
  echo "===== Exp12 run $i ====="
  IMAGE=wwiras/ahbn-peer:v20 ./scripts/run_exp12.sh
  sleep 10
done
```

The final analysis should use averaged metrics across all runs rather than a single execution.

## Expected outputs
- `exp12_summary.csv`
- `exp12_timeline.png`
- `exp12_adaptation.png`
- `exp12_resource_latency.png`
- `logs.jsonl`

## Expected behavior
- AHBN should show visible adaptive fanout increases shortly after overload injection.
- Low-resource peers should exhibit noticeably higher forwarding latency compared to normal peers.
- Dissemination should continue despite heterogeneous forwarding delays because AHBN temporarily increases dissemination intensity.
- Delivery ratio should remain relatively stable across repeated runs, although duplicates may increase due to more aggressive forwarding behavior.
- Adaptive fanout should remain consistently above the configured baseline fanout during stress periods.

## Experimental interpretation
Exp12 demonstrates resource realism in a cloud-native environment. The experiment validates that AHBN can adapt dissemination behavior in response to heterogeneous peer capability rather than only explicit failures or churn.

A successful Exp12 run typically shows:
- stable delivery ratio under stress,
- increased adaptive fanout,
- moderate duplication growth,
- and reproducible behavior across repeated Kubernetes executions.

This experiment serves as the resource heterogeneity validation stage of the AHBN realism pipeline:
- Exp10 → failure realism
- Exp11 → churn realism
- Exp12 → heterogeneous resource realism