from __future__ import annotations

import json
import os
import random
import socket
import threading
import time
from concurrent import futures
from typing import Any

import grpc

import peer_pb2
import peer_pb2_grpc


def now() -> float:
    return time.time()


def log_event(**kwargs: Any) -> None:
    print(json.dumps({"ts": now(), **kwargs}, sort_keys=True), flush=True)


class PeerState:
    def __init__(self) -> None:
        self.hostname = socket.gethostname()
        self.peer_id = int(self.hostname.rsplit("-", 1)[1])

        self.config_path = os.environ.get("TOPOLOGY_PATH", "/config/topology.json")
        self.grpc_port = int(os.environ.get("GRPC_PORT", "50051"))
        self.peer_service_name = os.environ.get("PEER_SERVICE_NAME", "ahbn-peer")
        self.namespace = os.environ.get("POD_NAMESPACE", "default")

        with open(self.config_path, "r", encoding="utf-8") as f:
            topo = json.load(f)

        self.run_id = topo["run_id"]
        self.strategy = topo["strategy"]
        self.num_nodes = topo["num_nodes"]
        self.source_id = topo["message_source"]
        self.default_fanout = topo.get("fanout", 3)
        self.mode_threshold = topo.get("ahbn", {}).get("mode_threshold", 0.5)
        self.min_fanout = topo.get("ahbn", {}).get("min_fanout", 1)
        self.max_fanout = topo.get("ahbn", {}).get("max_fanout", 6)


        peer_key = str(self.peer_id)
        if peer_key not in topo["nodes"]:
            raise RuntimeError(
                f"peer_id {self.peer_id} not found in topology nodes. "
                f"Topology has {len(topo['nodes'])} nodes: "
                f"{sorted(topo['nodes'].keys())[:10]}..."
            )
        node_cfg = topo["nodes"][peer_key]
        # node_cfg = topo["nodes"][str(self.peer_id)]
        self.neighbors: list[int] = node_cfg["neighbors"]
        self.is_cluster_head: bool = bool(node_cfg["is_cluster_head"])
        self.cluster_members: list[int] = node_cfg.get("cluster_members", [])
        self.cluster_head_id: int = node_cfg.get("cluster_head_id", self.peer_id)
        self.gateway_neighbors: list[int] = node_cfg.get("gateway_neighbors", [])

        self.overload_ms = 0
        self.failed = False
        self.seen_messages: set[str] = set()
        self.lock = threading.Lock()
        self.ready = True

        self.mode = "cluster" if self.strategy == "cluster" else "gossip"
        self.fanout = self.default_fanout
        self.duplicate_count = 0
        self.forward_count = 0
        self.recv_count = 0
        
        # Local failure-pressure signal for adaptive reaction to broken paths.
        self.fail_pressure = 0.0
        self.fail_decay = 0.85
        self.fail_boost = 1.0
        self.fail_threshold = 0.25

        log_event(
            event="peer_started",
            run_id=self.run_id,
            peer_id=self.peer_id,
            strategy=self.strategy,
            mode=self.mode,
            fanout=self.fanout,
            is_cluster_head=self.is_cluster_head,
            neighbors=self.neighbors,
            cluster_head_id=self.cluster_head_id,
            gateway_neighbors=self.gateway_neighbors,
        )

    def peer_dns(self, peer_id: int) -> str:
        return (
            f"peer-{peer_id}.{self.peer_service_name}.{self.namespace}.svc.cluster.local:"
            f"{self.grpc_port}"
        )

    
    def adaptive_update(self) -> None:
        if self.strategy != "ahbn" or self.failed:
            return

        dup_pressure = self.duplicate_count / max(1, self.recv_count)
        fail_pressure = self.fail_pressure

        old_mode = self.mode
        old_fanout = self.fanout

        # Failure-driven reaction takes priority:
        # if recent forwarding failures are observed, temporarily switch
        # toward more aggressive gossip with larger fanout.
        if fail_pressure > self.fail_threshold:
            self.mode = "gossip"
            self.fanout = min(self.max_fanout, self.default_fanout + 3)

        # Otherwise use duplicate-aware control.
        elif dup_pressure > self.mode_threshold:
            self.mode = "cluster"
            self.fanout = max(self.min_fanout, self.default_fanout - 1)
        else:
            self.mode = "gossip"
            self.fanout = min(self.max_fanout, self.default_fanout + 2)

        log_event(
            event="adaptive_state",
            run_id=self.run_id,
            peer_id=self.peer_id,
            mode=self.mode,
            fanout=self.fanout,
            duplicate_count=self.duplicate_count,
            recv_count=self.recv_count,
            duplicate_ratio=dup_pressure,
            fail_pressure=fail_pressure,
            is_cluster_head=self.is_cluster_head,
            overload_ms=self.overload_ms,
            failed=self.failed,
        )

        if self.mode != old_mode:
            log_event(
                event="mode_switched",
                run_id=self.run_id,
                peer_id=self.peer_id,
                old_mode=old_mode,
                new_mode=self.mode,
                duplicate_ratio=dup_pressure,
                fail_pressure=fail_pressure,
            )

        if self.fanout != old_fanout:
            log_event(
                event="fanout_changed",
                run_id=self.run_id,
                peer_id=self.peer_id,
                old_fanout=old_fanout,
                new_fanout=self.fanout,
                duplicate_ratio=dup_pressure,
                fail_pressure=fail_pressure,
            )
    
    
    def trigger_failure_reaction(self, reason: str) -> None:
        if self.strategy != "ahbn" or self.failed:
            return

        old_mode = self.mode
        old_fanout = self.fanout

        self.fail_pressure = min(1.0, self.fail_pressure + self.fail_boost)

        # FORCE visible reaction immediately
        self.mode = "gossip"
        self.fanout = min(self.max_fanout, self.default_fanout + 3)

        if self.mode != old_mode:
            log_event(
                event="mode_switched",
                run_id=self.run_id,
                peer_id=self.peer_id,
                old_mode=old_mode,
                new_mode=self.mode,
                reason=reason,
                fail_pressure=self.fail_pressure,
            )

        if self.fanout != old_fanout:
            log_event(
                event="fanout_changed",
                run_id=self.run_id,
                peer_id=self.peer_id,
                old_fanout=old_fanout,
                new_fanout=self.fanout,
                reason=reason,
                fail_pressure=self.fail_pressure,
            )

        log_event(
            event="failure_reaction",
            run_id=self.run_id,
            peer_id=self.peer_id,
            fanout=self.fanout,
            mode=self.mode,
            fail_pressure=self.fail_pressure,
            reason=reason,
            is_cluster_head=self.is_cluster_head,
        )
    
    def cluster_targets(self, sender_id: int) -> list[int]:
        targets: list[int] = []
        if self.is_cluster_head:
            for n in self.cluster_members + self.gateway_neighbors:
                if n != sender_id:
                    targets.append(n)
        else:
            if self.cluster_head_id != sender_id:
                targets.append(self.cluster_head_id)
        return sorted(set(targets))

    def target_peers(self, sender_id: int) -> list[int]:
        if self.strategy == "gossip":
            candidates = [n for n in self.neighbors if n != sender_id]
            k = min(self.default_fanout, len(candidates))
            return random.sample(candidates, k) if k > 0 else []

        if self.strategy == "cluster":
            return self.cluster_targets(sender_id)

        # AHBN
        self.adaptive_update()

        if self.mode == "cluster":
            return self.cluster_targets(sender_id)

        # AHBN in gossip mode:
        # keep local gossip, but preserve one structural path so dissemination
        # does not die inside sparse inter-cluster connectivity.
        targets: list[int] = []

        # Local gossip neighbors
        candidates = [n for n in self.neighbors if n != sender_id]
        k = min(self.fanout, len(candidates))
        if k > 0:
            targets.extend(random.sample(candidates, k))

        # Structural backbone target
        # if self.is_cluster_head:
        #     gw_candidates = [n for n in self.gateway_neighbors if n != sender_id]
        #     if gw_candidates:
        #         targets.append(random.choice(gw_candidates))
        if self.is_cluster_head:
            gw_candidates = [n for n in self.gateway_neighbors if n != sender_id]
            targets.extend(gw_candidates)
        else:
            if self.cluster_head_id != sender_id:
                targets.append(self.cluster_head_id)

        # Deduplicate and avoid self-target
        targets = [t for t in sorted(set(targets)) if t != self.peer_id]
        return targets
    
    def forward_to_peer(self, dst_peer: int, envelope: peer_pb2.Envelope) -> None:
        if self.failed:
            return

        addr = self.peer_dns(dst_peer)
        try:
            with grpc.insecure_channel(addr) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                resp = stub.Forward(envelope, timeout=3)

                if resp.ok:
                    self.forward_count += 1

                    # Successful forwarding gradually relaxes failure pressure.
                    self.fail_pressure *= self.fail_decay

                    log_event(
                        event="forward",
                        run_id=self.run_id,
                        peer_id=self.peer_id,
                        dst_peer=dst_peer,
                        src_peer=envelope.sender_id,
                        message_id=envelope.message_id,
                        strategy=self.strategy,
                        mode=self.mode,
                        fanout=self.fanout,
                        overload_ms=self.overload_ms,
                        is_cluster_head=self.is_cluster_head,
                        fail_pressure=self.fail_pressure,
                    )
                else:
                    self.trigger_failure_reaction(reason="forward_rejected")

                    log_event(
                        event="forward_rejected",
                        run_id=self.run_id,
                        peer_id=self.peer_id,
                        dst_peer=dst_peer,
                        message_id=envelope.message_id,
                        fail_pressure=self.fail_pressure,
                    )               
                

            
        except Exception as e:
            self.trigger_failure_reaction(reason="forward_failed")

            log_event(
                event="forward_failed",
                run_id=self.run_id,
                peer_id=self.peer_id,
                dst_peer=dst_peer,
                message_id=envelope.message_id,
                error=str(e),
                fail_pressure=self.fail_pressure,
            )

    def process_envelope(self, envelope: peer_pb2.Envelope) -> tuple[bool, str]:
        if self.failed:
            log_event(
                event="dropped_failed_node",
                run_id=self.run_id,
                peer_id=self.peer_id,
                message_id=envelope.message_id,
            )
            return False, "failed"

        with self.lock:
            self.recv_count += 1

            if envelope.message_id in self.seen_messages:
                self.duplicate_count += 1
                log_event(
                    event="received_duplicate",
                    run_id=self.run_id,
                    peer_id=self.peer_id,
                    src_peer=envelope.sender_id,
                    message_id=envelope.message_id,
                    hop=envelope.hop,
                    strategy=self.strategy,
                    mode=self.mode,
                    fanout=self.fanout,
                    overload_ms=self.overload_ms,
                )
                return False, "duplicate"

            self.seen_messages.add(envelope.message_id)

        if self.overload_ms > 0:
            time.sleep(self.overload_ms / 1000.0)

        delivery_ms = int((now() - envelope.created_at) * 1000)
        log_event(
            event="received_new",
            run_id=self.run_id,
            peer_id=self.peer_id,
            src_peer=envelope.sender_id,
            message_id=envelope.message_id,
            hop=envelope.hop,
            strategy=self.strategy,
            mode=self.mode,
            fanout=self.fanout,
            latency_ms=delivery_ms,
            overload_ms=self.overload_ms,
            is_cluster_head=self.is_cluster_head,
        )

        targets = self.target_peers(sender_id=envelope.sender_id)
        next_env = peer_pb2.Envelope(
            run_id=envelope.run_id,
            message_id=envelope.message_id,
            source_id=envelope.source_id,
            sender_id=self.peer_id,
            created_at=envelope.created_at,
            hop=envelope.hop + 1,
        )

        for dst in targets:
            threading.Thread(
                target=self.forward_to_peer,
                args=(dst, next_env),
                daemon=True,
            ).start()

        return True, "ok"


class PeerService(peer_pb2_grpc.PeerServiceServicer):
    def __init__(self, state: PeerState) -> None:
        self.state = state

    def Forward(self, request, context):
        is_new, msg = self.state.process_envelope(request)
        return peer_pb2.Ack(ok=is_new, message=msg)

    def StartRun(self, request, context):
        if self.state.failed:
            return peer_pb2.Ack(ok=False, message="peer failed")

        env = peer_pb2.Envelope(
            run_id=request.run_id,
            message_id=request.message_id,
            source_id=self.state.source_id,
            sender_id=self.state.peer_id,
            created_at=now(),
            hop=0,
        )
        log_event(
            event="message_injected",
            run_id=request.run_id,
            peer_id=self.state.peer_id,
            message_id=request.message_id,
            strategy=self.state.strategy,
        )
        self.state.process_envelope(env)
        return peer_pb2.Ack(ok=True, message="run started")

    def InjectOverload(self, request, context):
        self.state.overload_ms = int(request.delay_ms)
        log_event(
            event="overload_applied",
            run_id=self.state.run_id,
            peer_id=self.state.peer_id,
            overload_ms=self.state.overload_ms,
        )
        return peer_pb2.Ack(ok=True, message="overload applied")

    def ClearOverload(self, request, context):
        self.state.overload_ms = 0
        log_event(
            event="overload_cleared",
            run_id=self.state.run_id,
            peer_id=self.state.peer_id,
        )
        return peer_pb2.Ack(ok=True, message="overload cleared")

    def FailStop(self, request, context):
        self.state.failed = True
        self.state.overload_ms = 0
        log_event(
            event="peer_failed",
            run_id=self.state.run_id,
            peer_id=self.state.peer_id,
            is_cluster_head=self.state.is_cluster_head,
        )
        return peer_pb2.Ack(ok=True, message="peer entered fail-stop state")

    def GetStatus(self, request, context):
        return peer_pb2.StatusReply(
            ready=self.state.ready,
            alive=not self.state.failed,
            peer_id=self.state.peer_id,
            is_cluster_head=self.state.is_cluster_head,
            mode=self.state.mode,
            fanout=self.state.fanout,
            seen_count=len(self.state.seen_messages),
        )


def serve() -> None:
    state = PeerState()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
    peer_pb2_grpc.add_PeerServiceServicer_to_server(PeerService(state), server)
    server.add_insecure_port(f"[::]:{state.grpc_port}")
    server.start()
    log_event(
        event="grpc_server_started",
        run_id=state.run_id,
        peer_id=state.peer_id,
        port=state.grpc_port,
    )
    server.wait_for_termination()


if __name__ == "__main__":
    serve()