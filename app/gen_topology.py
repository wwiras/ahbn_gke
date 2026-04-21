from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import yaml


def build_graph(
    num_nodes: int,
    topology_type: str,
    edge_prob: float,
    ba_m: int,
    seed: int,
    max_tries: int = 100,
):
    if topology_type == "er":
        for attempt in range(max_tries):
            attempt_seed = seed + attempt
            g = nx.erdos_renyi_graph(num_nodes, edge_prob, seed=attempt_seed)
            if nx.is_connected(g):
                return g

        raise RuntimeError(
            f"Failed to generate a connected ER graph with "
            f"num_nodes={num_nodes}, edge_prob={edge_prob} "
            f"after {max_tries} attempts. "
            f"Increase edgeProb or use topology.type=ba."
        )

    elif topology_type == "ba":
        g = nx.barabasi_albert_graph(num_nodes, ba_m, seed=seed)
        return g

    else:
        raise ValueError("topology.type must be er or ba")


def assign_clusters(num_nodes: int, num_clusters: int):
    cluster_size = max(1, num_nodes // num_clusters)
    cluster_heads = []
    cluster_of = {}
    members = {i: [] for i in range(num_clusters)}

    for cid in range(num_clusters):
        head = cid * cluster_size
        if head < num_nodes:
            cluster_heads.append(head)

    for node_id in range(num_nodes):
        cid = min(node_id // cluster_size, num_clusters - 1)
        cluster_of[node_id] = cid
        members[cid].append(node_id)

    return cluster_heads, cluster_of, members


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())

    experiment = cfg.get("experiment", "exp10")
    strategy = cfg.get("strategy", "ahbn")
    num_nodes = int(cfg.get("numNodes", 20))
    fanout = int(cfg.get("fanout", 3))
    num_clusters = int(cfg.get("numClusters", 4))
    message_source = int(cfg.get("messageSource", 0))
    settle_time = float(cfg.get("settleTime", 15.0))

    topo_cfg = cfg.get("topology", {})
    topology_type = topo_cfg.get("type", "er")
    edge_prob = float(topo_cfg.get("edgeProb", 0.2))
    ba_m = int(topo_cfg.get("baM", 2))
    seed = int(topo_cfg.get("seed", 42))

    failure_cfg = cfg.get("failure", {})
    failure_mode = failure_cfg.get("mode", "node_failure")
    trigger_time = float(failure_cfg.get("triggerTime", 1.0))
    overload_delay_ms = int(failure_cfg.get("overloadDelayMs", 200))
    num_events = int(failure_cfg.get("numEvents", 3))
    interval_sec = float(failure_cfg.get("intervalSec", 1.0))
    target_type = str(failure_cfg.get("targetType", "mixed"))

    workload_cfg = cfg.get("workload", {})
    message_count = int(workload_cfg.get("messageCount", 1))
    message_interval = float(workload_cfg.get("messageInterval", 0.0))

    g = build_graph(num_nodes, topology_type, edge_prob, ba_m, seed)
    actual_nodes = g.number_of_nodes()

    cluster_heads, cluster_of, members = assign_clusters(actual_nodes, num_clusters)

    nodes = {}
    for node_id in range(actual_nodes):
        cid = cluster_of[node_id]
        head = cluster_heads[cid]
        gateways = []
        if node_id in cluster_heads:
            idx = cluster_heads.index(node_id)
            if idx > 0:
                gateways.append(cluster_heads[idx - 1])
            if idx < len(cluster_heads) - 1:
                gateways.append(cluster_heads[idx + 1])

        nodes[str(node_id)] = {
            "neighbors": sorted(list(g.neighbors(node_id))),
            "cluster_id": cid,
            "is_cluster_head": node_id in cluster_heads,
            "cluster_head_id": head,
            "cluster_members": [n for n in members[cid] if n != node_id],
            "gateway_neighbors": gateways,
        }

    topo = {
        "run_id": experiment,
        "seed": seed,
        "strategy": strategy,
        "num_nodes": actual_nodes,
        "topology_type": topology_type,
        "edge_prob": edge_prob,
        "ba_m": ba_m,
        "message_source": message_source,
        "fanout": fanout,
        "num_clusters": num_clusters,
        "settle_time": settle_time,
        "failure": {
            "mode": failure_mode,
            "trigger_time": trigger_time,
            "overload_delay_ms": overload_delay_ms,
            "num_events": num_events,
            "interval_sec": interval_sec,
            "target_type": target_type,
        },
        "workload": {
            "message_count": message_count,
            "message_interval": message_interval,
        },
        "ahbn": {
            "mode_threshold": 0.5,
            "min_fanout": 1,
            "max_fanout": 6,
        },
        "nodes": nodes,
    }

    out = Path(args.out)
    out.write_text(json.dumps(topo, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
