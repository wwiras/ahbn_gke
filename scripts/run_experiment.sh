#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-}"
if [ -z "$CONFIG" ]; then
  echo "Usage: $0 experiments/exp10.yaml"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_TS="$(date +%Y%m%d_%H%M%S)"
EXP_NAME="$(basename "$CONFIG" .yaml)"
RUN_ID="${EXP_NAME}-${OUT_TS}"
OUTDIR="${ROOT_DIR}/outputs/${RUN_ID}"
NAMESPACE="${NAMESPACE:-ahbn-exp10}"
RELEASE="${RELEASE:-ahbn}"
IMAGE="${IMAGE:-}"

mkdir -p "${OUTDIR}"

if [ -z "$IMAGE" ]; then
  echo "ERROR: set IMAGE, e.g."
  echo 'IMAGE=wwiras/ahbn-peer:v4 ./scripts/run_exp10.sh'
  exit 1
fi

collect_debug() {
  echo "[debug] Collecting diagnostics ..."
  kubectl -n "${NAMESPACE}" get pods -o wide > "${OUTDIR}/pods.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" get statefulset peer > "${OUTDIR}/statefulset.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" describe statefulset peer > "${OUTDIR}/statefulset_describe.txt" 2>/dev/null || true
  kubectl -n "${NAMESPACE}" logs job/ahbn-controller > "${OUTDIR}/controller.log" 2>/dev/null || true

  : > "${OUTDIR}/logs.jsonl"
  for p in $(kubectl -n "${NAMESPACE}" get pods -l app=ahbn-peer -o name 2>/dev/null | sort); do
    kubectl -n "${NAMESPACE}" logs "${p}" >> "${OUTDIR}/logs.jsonl" 2>/dev/null || true
    kubectl -n "${NAMESPACE}" logs "${p}" --previous >> "${OUTDIR}/logs.jsonl" 2>/dev/null || true
  done
  kubectl -n "${NAMESPACE}" logs job/ahbn-controller >> "${OUTDIR}/logs.jsonl" 2>/dev/null || true
}

trap 'collect_debug' EXIT

# echo "[1] Generate topology"
# python "${ROOT_DIR}/app/gen_topology.py" \
#   --config "${ROOT_DIR}/${CONFIG}" \
#   --out "${OUTDIR}/topology.json"

# NUM_NODES="$(python - <<PY
# import json
# with open("${OUTDIR}/topology.json", "r", encoding="utf-8") as f:
#     topo = json.load(f)
# print(int(topo["num_nodes"]))
# PY
# )"

echo "[1] Generate topology"
python "${ROOT_DIR}/app/gen_topology.py" \
  --config "${ROOT_DIR}/${CONFIG}" \
  --out "${OUTDIR}/topology.json"

echo "[debug] Inspect generated topology"
python - <<PY
import json
with open("${OUTDIR}/topology.json", "r", encoding="utf-8") as f:
    topo = json.load(f)

print("=== FAILURE CONFIG ===")
print(json.dumps(topo.get("failure"), indent=2))

print("=== WORKLOAD CONFIG ===")
print(json.dumps(topo.get("workload"), indent=2))
PY

NUM_NODES="$(python - <<PY
import json
with open("${OUTDIR}/topology.json", "r", encoding="utf-8") as f:
    topo = json.load(f)
print(int(topo["num_nodes"]))
PY
)"

echo "[2] Copy topology into Helm chart payload"
cp "${OUTDIR}/topology.json" "${ROOT_DIR}/helm/ahbn/topology.json"

echo "[3] Reset previous release if present"
helm uninstall "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1 || true

echo "[4] Install peers only (controller disabled)"
helm install "${RELEASE}" "${ROOT_DIR}/helm/ahbn" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --set namespace="${NAMESPACE}" \
  --set image="${IMAGE}" \
  --set numNodes="${NUM_NODES}" \
  --set controller.enabled=false

echo "[5] Wait for StatefulSet rollout"
kubectl -n "${NAMESPACE}" rollout status statefulset/peer --timeout=600s

echo "[6] Wait for all peer pods to be Ready"
kubectl -n "${NAMESPACE}" wait \
  --for=condition=ready pod \
  -l app=ahbn-peer \
  --timeout=600s

echo "[7] Safety buffer before controller start"
sleep 5

echo "[8] Start controller job"
helm upgrade "${RELEASE}" "${ROOT_DIR}/helm/ahbn" \
  --namespace "${NAMESPACE}" \
  --reuse-values \
  --set controller.enabled=true

echo "[9] Wait for controller completion"
kubectl -n "${NAMESPACE}" wait \
  --for=condition=complete job/ahbn-controller \
  --timeout=600s

echo "[10] Collect logs"
collect_debug

echo "[11] Plot results"
PLOT_SCRIPT="${ROOT_DIR}/app/plot_exp10.py"
if [ "${EXP_NAME}" = "exp11" ]; then
  PLOT_SCRIPT="${ROOT_DIR}/app/plot_exp11.py"
fi
python "${PLOT_SCRIPT}" \
  --log "${OUTDIR}/logs.jsonl" \
  --expected-nodes "${NUM_NODES}" \
  --outdir "${OUTDIR}"

echo "DONE -> ${OUTDIR}"
trap - EXIT