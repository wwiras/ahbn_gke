# Exp8 - Cluster Head Bottleneck Realism in Kubernetes

This experiment validates AHBN under cluster-head bottleneck conditions in Kubernetes. Unlike the controlled Python simulator experiments, Exp8 evaluates whether AHBN can sustain dissemination performance when dissemination-critical peers experience forwarding slowdown in a real cloud-native environment.

The experiment injects artificial forwarding delay into selected cluster heads (CHs) during an active multi-message dissemination workload. This simulates overloaded dissemination hubs, congested forwarding paths, or temporarily degraded relay peers commonly observed in large-scale distributed systems.

AHBN is expected to react adaptively by increasing dissemination aggressiveness and temporarily shifting toward more gossip-oriented forwarding behavior to compensate for bottleneck pressure.

## Recommended configuration
- Topology: BA, `baM: 2`
- Nodes: 20
- Clusters: 4
- Workload: 20–30 messages
- Message spacing: `0.3s – 0.5s`
- Bottleneck injection:
  - CH-only overload
  - `600ms–800ms` forwarding delay
  - trigger at `0.5s`
- Settle time: `20s–25s`

## Run
```bash
IMAGE=wwiras/ahbn-peer:v21 ./scripts/run_exp8.sh
```

## Optional repeatability evaluation
For stronger statistical confidence and thesis-quality evaluation, the experiment may optionally be repeated across multiple executions:

```bash
for i in {1..10}; do
  echo "===== Exp8 run $i ====="

  helm uninstall ahbn -n ahbn-exp10 || true
  kubectl delete namespace ahbn-exp10 --ignore-not-found=true

  sleep 20

  IMAGE=wwiras/ahbn-peer:v21 ./scripts/run_exp8.sh

  sleep 15
done
```
> **Note:** We are using ahbn-exp10 as namespace for all experiments

Repeated executions help validate:
- dissemination stability,
- adaptive consistency,
- and reproducibility under Kubernetes scheduling variability.

The final analysis may use averaged metrics across all runs rather than relying on a single execution.

## Expected outputs
- `exp8_summary.csv`
- `exp8_timeline.png`
- `exp8_adaptation.png`
- `logs.jsonl`

## Expected behavior
- AHBN should show visible adaptive fanout increases shortly after bottleneck injection.
- Dissemination should temporarily slow during CH overload periods but continue progressing afterward.
- AHBN should increasingly favor gossip-oriented dissemination when CH forwarding latency becomes excessive.
- Delivery ratio should remain relatively stable despite dissemination bottlenecks.
- Duplicate forwarding may increase moderately because AHBN temporarily increases forwarding aggressiveness to preserve dissemination continuity.
- Adaptive fanout should remain consistently above the configured baseline fanout during overload periods.

## Experimental interpretation

Exp8 demonstrates dissemination realism under forwarding bottlenecks in a cloud-native Kubernetes environment. The experiment validates that AHBN can dynamically compensate for overloaded dissemination hubs rather than relying entirely on static cluster-based forwarding.

A successful Exp8 run typically shows:
- temporary dissemination slowdown during overload,
- adaptive fanout escalation,
- continued delivery progression,
- moderate duplication growth,
- and stable dissemination recovery after bottleneck periods.

Unlike pure cluster dissemination, which may suffer severe propagation slowdown when CHs become overloaded, AHBN should redistribute dissemination pressure through more adaptive forwarding behavior.

## Kubernetes realism significance

Exp8 serves as the first realism-promotion stage of the AHBN Kubernetes validation pipeline. The experiment demonstrates that AHBN behavior remains observable and adaptive under real orchestration, pod scheduling, and inter-pod communication conditions rather than only within a discrete-event simulator.

The experiment includes:
- StatefulSet-based peer deployment,
- real inter-pod gRPC dissemination,
- Kubernetes-managed networking,
- distributed workload injection,
- and infrastructure-backed dissemination tracing.

## Realism validation pipeline

This experiment forms part of the AHBN Kubernetes realism progression:

- Exp8  → bottleneck realism
- Exp10 → failure realism
- Exp11 → churn realism
- Exp12 → heterogeneous resource realism