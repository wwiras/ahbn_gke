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