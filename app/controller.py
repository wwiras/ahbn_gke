from __future__ import annotations

import json
import os
import random
import time

import grpc
from kubernetes import client, config
from kubernetes.client.rest import ApiException

import peer_pb2
import peer_pb2_grpc


def now() -> float:
    return time.time()


def log_event(**kwargs):
    print(json.dumps({"ts": now(), **kwargs}, sort_keys=True), flush=True)


def load_topology(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def peer_addr(peer_id: int, svc: str, ns: str, port: int) -> str:
    return f"peer-{peer_id}.{svc}.{ns}.svc.cluster.local:{port}"


def wait_for_peers(num_nodes: int, svc: str, ns: str, port: int, timeout: int = 300) -> None:
    start = time.time()
    for peer_id in range(num_nodes):
        ok = False
        while time.time() - start < timeout:
            try:
                with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                    stub = peer_pb2_grpc.PeerServiceStub(channel)
                    status = stub.GetStatus(peer_pb2.Empty(), timeout=2)
                    if status.ready:
                        ok = True
                        break
            except Exception:
                pass
            time.sleep(1.0)
        if not ok:
            raise RuntimeError(f"peer-{peer_id} did not become ready")


def wait_for_peer_ready(peer_id: int, svc: str, ns: str, port: int, timeout: int = 180) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                status = stub.GetStatus(peer_pb2.Empty(), timeout=2)
                if status.ready:
                    return
        except Exception:
            pass
        time.sleep(1.0)
    raise RuntimeError(f"peer-{peer_id} did not recover within {timeout}s")


def choose_target(topo: dict, mode: str) -> int | None:
    rng = random.Random(topo.get("seed", 42))
    source = topo["message_source"]
    nodes = topo["nodes"]

    if mode == "none":
        return None

    if mode == "node_failure":
        candidates = [int(k) for k in nodes.keys() if int(k) != source]
        return rng.choice(candidates)

    if mode in ("ch_failure", "overload"):
        chs = [int(k) for k, v in nodes.items() if v["is_cluster_head"] and int(k) != source]
        if not chs:
            raise RuntimeError("No eligible cluster head found that is not the source")
        return rng.choice(chs)

    raise ValueError(f"unsupported mode {mode}")


def choose_churn_targets(topo: dict, count: int, target_type: str) -> list[int]:
    rng = random.Random(topo.get("seed", 42) + 99)
    source = topo["message_source"]
    nodes = topo["nodes"]

    candidates: list[int] = []
    for k, v in nodes.items():
        peer_id = int(k)
        if peer_id == source:
            continue
        is_ch = bool(v["is_cluster_head"])
        if target_type == "cluster_head" and not is_ch:
            continue
        if target_type == "non_ch" and is_ch:
            continue
        candidates.append(peer_id)

    if not candidates:
        raise RuntimeError(f"No eligible churn targets for target_type={target_type}")

    rng.shuffle(candidates)
    if count <= len(candidates):
        return candidates[:count]

    out: list[int] = []
    while len(out) < count:
        out.extend(candidates)
    return out[:count]


def fail_stop_peer(peer_id: int, svc: str, ns: str, port: int) -> None:
    for attempt in range(3):
        try:
            with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                stub.FailStop(peer_pb2.Empty(), timeout=3)

            log_event(
                event="fail_stop_requested",
                peer_id=peer_id,
                attempt=attempt + 1,
            )
            return

        except Exception as e:
            log_event(
                event="fail_stop_retry",
                peer_id=peer_id,
                attempt=attempt + 1,
                error=str(e),
            )
            time.sleep(1)

    raise RuntimeError(f"Failed to fail-stop peer {peer_id}")


def apply_overload(peer_id: int, svc: str, ns: str, port: int, delay_ms: int) -> None:
    with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
        stub = peer_pb2_grpc.PeerServiceStub(channel)
        stub.InjectOverload(peer_pb2.OverloadRequest(delay_ms=delay_ms), timeout=3)
    log_event(event="overload_requested", peer_id=peer_id, overload_ms=delay_ms)


def delete_peer_pod(peer_id: int, ns: str) -> None:
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    pod_name = f"peer-{peer_id}"
    try:
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=ns,
            grace_period_seconds=0,
        )
        log_event(event="pod_delete_requested", peer_id=peer_id, pod_name=pod_name)
    except ApiException as e:
        if e.status == 404:
            log_event(event="pod_delete_missing", peer_id=peer_id, pod_name=pod_name)
            return
        raise


def inject_messages(run_id: str, source_id: int, peer_svc: str, namespace: str, grpc_port: int,
                    message_count: int, message_interval: float) -> None:
    for idx in range(message_count):
        message_id = f"m{idx + 1}"
        with grpc.insecure_channel(peer_addr(source_id, peer_svc, namespace, grpc_port)) as channel:
            stub = peer_pb2_grpc.PeerServiceStub(channel)
            stub.StartRun(
                peer_pb2.StartRequest(run_id=run_id, message_id=message_id),
                timeout=3,
            )
        log_event(event="source_triggered", run_id=run_id, peer_id=source_id, message_id=message_id)
        if idx < message_count - 1 and message_interval > 0:
            time.sleep(message_interval)


def run_churn(topo: dict, peer_svc: str, namespace: str, grpc_port: int) -> None:
    failure = topo["failure"]
    trigger_time = float(failure.get("trigger_time", 1.0))
    num_events = int(failure.get("num_events", 3))
    interval_sec = float(failure.get("interval_sec", 1.0))
    target_type = str(failure.get("target_type", "mixed"))

    time.sleep(trigger_time)
    targets = choose_churn_targets(topo, num_events, target_type)

    for idx, target in enumerate(targets, start=1):
        is_ch = topo["nodes"][str(target)]["is_cluster_head"]
        log_event(
            event="churn_triggered",
            run_id=topo["run_id"],
            churn_index=idx,
            target_peer=target,
            is_cluster_head=is_ch,
            target_type=target_type,
        )
        delete_peer_pod(target, namespace)
        wait_for_peer_ready(target, peer_svc, namespace, grpc_port)
        log_event(
            event="churn_recovered",
            run_id=topo["run_id"],
            churn_index=idx,
            target_peer=target,
            is_cluster_head=is_ch,
        )
        if idx < len(targets) and interval_sec > 0:
            time.sleep(interval_sec)


def main() -> None:
    topo_path = os.environ.get("TOPOLOGY_PATH", "/config/topology.json")
    peer_svc = os.environ.get("PEER_SERVICE_NAME", "ahbn-peer")
    namespace = os.environ.get("POD_NAMESPACE", "default")
    grpc_port = int(os.environ.get("GRPC_PORT", "50051"))

    topo = load_topology(topo_path)
    run_id = topo["run_id"]
    num_nodes = topo["num_nodes"]
    source_id = topo["message_source"]
    failure = topo["failure"]
    mode = failure["mode"]
    overload_ms = int(failure.get("overload_delay_ms", 200))

    workload = topo.get("workload", {})
    message_count = int(workload.get("message_count", 1))
    message_interval = float(workload.get("message_interval", 0.0))

    log_event(event="controller_started", run_id=run_id, failure_mode=mode)
    wait_for_peers(num_nodes, peer_svc, namespace, grpc_port)
    log_event(event="all_peers_ready", run_id=run_id)

    inject_messages(
        run_id=run_id,
        source_id=source_id,
        peer_svc=peer_svc,
        namespace=namespace,
        grpc_port=grpc_port,
        message_count=message_count,
        message_interval=message_interval,
    )

    if mode == "churn":
        run_churn(topo, peer_svc, namespace, grpc_port)
    elif mode != "none":
        time.sleep(float(failure["trigger_time"]))
        target = choose_target(topo, mode)
        is_ch = topo["nodes"][str(target)]["is_cluster_head"]

        log_event(
            event="failure_triggered",
            run_id=run_id,
            failure_mode=mode,
            target_peer=target,
            is_cluster_head=is_ch,
        )

        if mode in ("node_failure", "ch_failure"):
            fail_stop_peer(target, peer_svc, namespace, grpc_port)
        elif mode == "overload":
            apply_overload(target, peer_svc, namespace, grpc_port, overload_ms)
        else:
            raise ValueError(mode)
    else:
        log_event(
            event="failure_skipped",
            run_id=run_id,
            failure_mode="none",
        )

    time.sleep(float(topo.get("settle_time", 15.0)))
    log_event(event="run_finished", run_id=run_id)


if __name__ == "__main__":
    main()
