from __future__ import annotations

import json
import os
import random
import time

import grpc

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
# def wait_for_peers(num_nodes, peer_svc, namespace, grpc_port, timeout=300):
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


def choose_target(topo: dict, mode: str) -> int:
    rng = random.Random(topo.get("seed", 42))
    source = topo["message_source"]
    nodes = topo["nodes"]

    if mode == "node_failure":
        candidates = [int(k) for k in nodes.keys() if int(k) != source]
        return rng.choice(candidates)

    if mode in ("ch_failure", "overload"):
        chs = [int(k) for k, v in nodes.items() if v["is_cluster_head"]]
        return rng.choice(chs)

    raise ValueError(f"unsupported mode {mode}")


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
    trigger_time = float(failure["trigger_time"])
    mode = failure["mode"]
    overload_ms = int(failure.get("overload_delay_ms", 200))

    log_event(event="controller_started", run_id=run_id, failure_mode=mode)
    wait_for_peers(num_nodes, peer_svc, namespace, grpc_port)
    log_event(event="all_peers_ready", run_id=run_id)

    with grpc.insecure_channel(peer_addr(source_id, peer_svc, namespace, grpc_port)) as channel:
        stub = peer_pb2_grpc.PeerServiceStub(channel)
        stub.StartRun(
            peer_pb2.StartRequest(run_id=run_id, message_id="m1"),
            timeout=3,
        )
    log_event(event="source_triggered", run_id=run_id, peer_id=source_id, message_id="m1")

    time.sleep(trigger_time)
    target = choose_target(topo, mode)
    # log_event(event="failure_triggered", run_id=run_id, failure_mode=mode, target_peer=target)
    
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

    time.sleep(float(topo.get("settle_time", 15.0)))
    log_event(event="run_finished", run_id=run_id)


if __name__ == "__main__":
    main()