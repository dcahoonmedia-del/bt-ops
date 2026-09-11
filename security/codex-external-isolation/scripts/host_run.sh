#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="${ROOT}/results"
IMAGE="${IMAGE:-bt-ops-codex-isolation:0.154.0}"
NETWORK="${NETWORK:-codex-iso-net}"
SUBNET="${SUBNET:-172.28.154.0/24}"
CONTAINER="${CONTAINER:-codex-iso-test0}"
PCAP="${RESULTS}/startup.pcap"
INSPECT_JSON="${RESULTS}/docker-inspect.json"

mkdir -p "${RESULTS}/timeline"
find "${RESULTS}" -mindepth 1 -maxdepth 1 ! -name timeline -exec rm -rf {} +
mkdir -p "${RESULTS}/timeline"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need docker
need python3
if ! command -v tcpdump >/dev/null 2>&1 && ! command -v tshark >/dev/null 2>&1; then
  echo "tcpdump or tshark is required for startup network evidence" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not available" >&2
  exit 1
fi

echo "==> building isolated image ${IMAGE}"
docker build -t "${IMAGE}" "${ROOT}"

if docker network inspect "${NETWORK}" >/dev/null 2>&1; then
  docker network rm "${NETWORK}" >/dev/null || true
fi
docker network create --driver bridge --subnet "${SUBNET}" "${NETWORK}" >/dev/null
BRIDGE="$(docker network inspect -f '{{.Id}}' "${NETWORK}" | cut -c1-12)"
IFACE="br-${BRIDGE}"
if ! ip link show "${IFACE}" >/dev/null 2>&1; then
  IFACE="$(ip -o link show | awk -F': ' '/br-/{print $2}' | while read -r name; do
    if ip -o addr show dev "${name}" | grep -q '172.28.154.'; then
      echo "${name}"
      break
    fi
  done)"
fi
echo "==> capture interface ${IFACE:-unknown}"

TCPDUMP_PID=""
cleanup() {
  if [[ -n "${TCPDUMP_PID}" ]] && kill -0 "${TCPDUMP_PID}" 2>/dev/null; then
    sudo kill -INT "${TCPDUMP_PID}" 2>/dev/null || true
    wait "${TCPDUMP_PID}" 2>/dev/null || true
  fi
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ -n "${IFACE}" ]] && ip link show "${IFACE}" >/dev/null 2>&1 && command -v tcpdump >/dev/null 2>&1; then
  sudo tcpdump -i "${IFACE}" -n -s 0 -w "${PCAP}" >/tmp/codex-iso-tcpdump.log 2>&1 &
  TCPDUMP_PID=$!
  sleep 1
else
  echo "warning: could not start tcpdump on ${IFACE:-none}" >&2
fi

echo "==> launching isolated container"
set +e
docker run --name "${CONTAINER}" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=128m \
  --tmpfs /opt/codex-isolation/runtime:rw,nosuid,uid=1000,gid=1000,size=512m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  --memory 2g \
  --cpus 2 \
  --network "${NETWORK}" \
  --user 1000:1000 \
  --env CODEX_HOME=/opt/codex-isolation/runtime/home \
  --env HOME=/opt/codex-isolation/runtime/user \
  --env OPENAI_API_KEY= \
  --env CODEX_API_KEY= \
  --mount "type=bind,src=${RESULTS},dst=/opt/codex-isolation/results" \
  "${IMAGE}" --phase all --network-evidence /opt/codex-isolation/results/startup-network.json
DOCKER_RC=$?
set -e

docker inspect "${CONTAINER}" > "${INSPECT_JSON}" || true

if [[ -n "${TCPDUMP_PID}" ]]; then
  sudo kill -INT "${TCPDUMP_PID}" 2>/dev/null || true
  wait "${TCPDUMP_PID}" 2>/dev/null || true
  TCPDUMP_PID=""
  sudo chown "$(id -u):$(id -g)" "${PCAP}" 2>/dev/null || true
fi

python3 - "${RESULTS}" <<'PY'
import json, subprocess, shutil, sys
from pathlib import Path

results = Path(sys.argv[1])
pcap = results / "startup.pcap"
forbidden_markers = (
    "github.com",
    "githubusercontent.com",
    "plugins.git",
    "openai/plugins",
    "cdn.openai.com",
)
hosts = []
dns = []
conversations = []
raw = ""
if pcap.exists() and pcap.stat().st_size > 24 and shutil.which("tshark"):
    raw = subprocess.check_output(
        [
            "tshark", "-r", str(pcap), "-T", "fields",
            "-e", "frame.time_epoch",
            "-e", "ip.dst",
            "-e", "ipv6.dst",
            "-e", "tcp.dstport",
            "-e", "udp.dstport",
            "-e", "tls.handshake.extensions_server_name",
            "-e", "http.host",
            "-e", "dns.qry.name",
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    for line in raw.splitlines():
        parts = (line.split("\t") + [""] * 8)[:8]
        ts, ip, ip6, tcp, udp, sni, http_host, dns_name = parts
        rec = {
            "ts": ts,
            "dst": ip or ip6,
            "tcp": tcp,
            "udp": udp,
            "sni": sni,
            "http_host": http_host,
            "dns": dns_name,
        }
        conversations.append(rec)
        for value in (sni, http_host, dns_name):
            if value:
                hosts.append(value)
        if dns_name:
            dns.append(dns_name)
elif pcap.exists() and shutil.which("tcpdump"):
    raw = subprocess.check_output(["tcpdump", "-nn", "-r", str(pcap)], text=True, stderr=subprocess.DEVNULL)
    for line in raw.splitlines():
        conversations.append({"raw": line})
        hosts.append(line)

haystack = "\n".join(hosts + [raw]).lower()
forbidden = sorted({marker for marker in forbidden_markers if marker.lower() in haystack})
payload = {
    "pcap": str(pcap),
    "pcap_bytes": pcap.stat().st_size if pcap.exists() else 0,
    "hosts": sorted(set(h for h in hosts if h)),
    "dns_queries": sorted(set(dns)),
    "conversation_count": len(conversations),
    "conversations": conversations[:200],
    "forbidden_hits": forbidden,
    "github_plugin_update_traffic": bool(forbidden),
}
(results / "startup-network.json").write_text(json.dumps(payload, indent=2) + "\n")

report_path = results / "report.json"
if report_path.exists():
    report = json.loads(report_path.read_text())
    report["network"] = payload
    if forbidden:
        report["verdict"] = {
            "status": "FAIL",
            "reason": "startup network included GitHub/plugin/update traffic",
            "preflight_passed": False,
            "forbidden_hits": forbidden,
        }
    elif report.get("verdict", {}).get("status") == "pending_network_merge":
        pass
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
print(json.dumps({"forbidden_hits": forbidden, "hosts": payload["hosts"], "dns": payload["dns_queries"]}, indent=2))
PY

echo "==> container exit ${DOCKER_RC}"
if [[ -f "${RESULTS}/report.json" ]]; then
  python3 -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); print(json.dumps(json.loads(p.read_text()).get("verdict"), indent=2))' "${RESULTS}/report.json"
fi
exit 0
