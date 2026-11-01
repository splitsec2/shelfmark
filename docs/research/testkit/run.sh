#!/bin/bash
# Runs every case for one variant and records it. Deliberately no `set -e`: a failing
# case is a result to record, and must not stop the cases after it.
set -uo pipefail

V=$1
ARCH=$2
KIT=$(cd "$(dirname "$0")" && pwd)
WS=$(dirname "$KIT")
R=$WS/results
L=$R/logs
mkdir -p "$L" "$R/trivy"
TSV=$R/results.tsv
PORT=18084

rec() { printf '%s\t%s\t%s\t%s\t%s\n' "$V" "$ARCH" "$1" "$2" "${3:-}" | tee -a "$TSV"; }
stop_app() { docker rm -f app >/dev/null 2>&1 || true; }

# Waits for /api/health. Prints seconds taken; returns 1 if it never answers or the container dies.
wait_health() {
    local limit=$1 i
    for ((i = 0; i < limit; i += 1)); do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health")" = 200 ]; then
            echo "$i"
            return 0
        fi
        [ "$(docker inspect -f '{{.State.Running}}' app 2>/dev/null)" = true ] || { echo "exited@$i"; return 1; }
        sleep 1
    done
    echo "timeout@$limit"
    return 1
}

start_app() {
    local image=$1
    shift
    stop_app
    docker run -d --name app -p "$PORT:8084" "$@" "$image" >/dev/null
}

logs_app() { docker logs app >"$L/$1.docker.log" 2>&1; }

# Runs smoke.py as uid 1000 in the running app; samples Chrome's real command line meanwhile.
smoke_exec() {
    local label=$1 url=${2:-https://example.com} want=${3:-Example Domain} user=${4:-1000:1000} rc
    docker cp "$KIT/smoke.py" app:/tmp/smoke.py >/dev/null
    (for _ in $(seq 1 40); do docker exec app ps -eo uid,args 2>/dev/null | grep -E 'type=renderer|remote-debugging' | head -3; sleep 3; done) >"$L/$label.ps.txt" 2>&1 &
    local sampler=$!
    timeout -k 10 "${SMOKE_TIMEOUT:-300}" docker exec -u "$user" -e HOME=/tmp/shelfmark/home app sh -c 'mkdir -p "$HOME"; python /tmp/smoke.py "$@"' _ "$url" "$want" >"$L/$label.log" 2>&1
    rc=$?
    kill "$sampler" 2>/dev/null
    wait "$sampler" 2>/dev/null
    echo "$rc"
}

cf_case() { # label
    local label=$1 rc
    rc=$(SMOKE_TIMEOUT=1000 smoke_exec "$label" https://www.scrapingcourse.com/cloudflare-challenge 'You bypassed')
    rec "$label" "$([ "$rc" = 0 ] && echo PASS || echo NOTSOLVED)" "rc=$rc attempts=$(grep -c 'Bypass attempt' "$L/$label.log") still_protected=$(grep -c 'still shows protection' "$L/$label.log") $(result_line "$label")"
}

result_line() { grep -m1 '^RESULT' "$L/$1.log" | cut -c1-170; }
mp4_size() { docker exec app sh -c 'ls -l /var/log/shelfmark/recording/*.mp4 2>/dev/null | tail -1' | awk '{print $5+0}'; }

# ---------- host facts
for m in ip_tables iptable_filter iptable_nat iptable_mangle iptable_raw ip6_tables ip6table_filter ip6table_raw xt_owner wireguard; do
    sudo modprobe "$m" 2>/dev/null || echo "modprobe $m failed" >>"$L/modprobe.txt"
done
{
    uname -a
    docker version --format 'docker {{.Server.Version}}'
    docker info --format 'storage={{.DriverStatus}} security={{.SecurityOptions}}'
    sysctl kernel.apparmor_restrict_unprivileged_userns kernel.unprivileged_userns_clone 2>&1
    git -C "$WS/src" log -1 --format='code %H %s'
    git -C "$WS/src" status --short
} >"$L/host.txt" 2>&1

# ---------- 1 build
cd "$WS/src" || exit 1
for target in shelfmark shelfmark-lite; do
    t0=$SECONDS
    if docker buildx build --progress=plain --load --target "$target" -t "t:$target" \
        --build-arg BUILD_VERSION="test-$V" --build-arg RELEASE_VERSION="test-$V" . >"$L/build-$target.log" 2>&1; then
        size=$(docker image inspect -f '{{.Size}}' "t:$target")
        gz=$(docker save "t:$target" | gzip -6 | wc -c)
        rec "build.$target" PASS "secs=$((SECONDS - t0)) image_bytes=$size saved_gzip_bytes=$gz"
    else
        rec "build.$target" FAIL "secs=$((SECONDS - t0)) $(grep -E 'ERROR|error:' "$L/build-$target.log" | tail -1 | cut -c1-160)"
    fi
done
cd "$WS" || exit 1
docker image inspect t:shelfmark >/dev/null 2>&1 || { rec abort FAIL "no full image"; exit 0; }

# ---------- 2 scan
for target in shelfmark shelfmark-lite; do
    docker image inspect "t:$target" >/dev/null 2>&1 || continue
    if docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$R/trivy:/out" -v trivycache:/root/.cache \
        ghcr.io/aquasecurity/trivy:0.76.1 image --image-src docker --scanners vuln --list-all-pkgs --format json \
        --output "/out/$target.json" --timeout 30m "t:$target" >"$L/trivy-$target.log" 2>&1; then
        rec "scan.$target" PASS
    else
        rec "scan.$target" FAIL "$(tail -1 "$L/trivy-$target.log" | cut -c1-160)"
    fi
done

sudo chmod -R a+rX "$R"

# ---------- 3 binaries and versions the scripts depend on
docker run --rm --entrypoint sh t:shelfmark -c 'for b in wg wg-quick iptables ip6tables ip tor supervisord supervisorctl gosu curl ffmpeg Xvfb chromium zip ping unrar 7z mount nslookup dig; do command -v $b >/dev/null 2>&1 && echo "$b=yes" || echo "$b=NO"; done; chromium --version; tor --version | head -1; ffmpeg -version 2>/dev/null | head -1' >"$L/binaries.txt" 2>&1
rec binaries INFO "missing: $(grep -E '=NO$' "$L/binaries.txt" | cut -d= -f1 | tr '\n' ' ')"

# ---------- tkinter chain, explicitly, under Xvfb
docker run --rm --user 1000:1000 --entrypoint sh t:shelfmark -c 'Xvfb :77 -ac -screen 0 1024x768x24 >/dev/null 2>&1 & sleep 3; DISPLAY=:77 python -c "import tkinter, pyautogui, mouseinfo; root = tkinter.Tk(); print(\"OK tk\", tkinter.TkVersion, \"pyautogui\", pyautogui.__version__, \"size\", pyautogui.size()); root.destroy()"' >"$L/tk.txt" 2>&1
rec tk_import "$(grep -q '^OK tk' "$L/tk.txt" && echo PASS || echo FAIL)" "$(tail -1 "$L/tk.txt" | cut -c1-150)"

# ---------- scanners other than Trivy, and what they see
SYFT=ghcr.io/anchore/syft@sha256:4cc92b64ca74ffca4c94d4c8fcc01f217731375300be14d0b6eeb2e82eaa110a
GRYPE=ghcr.io/anchore/grype@sha256:621d56d1d68106b787022c81546f7e0a36202a25d1239f0c20195fab8c16f7ea
mkdir -p "$R/grype"
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$R/grype:/out" "$SYFT" docker:t:shelfmark -o cyclonedx-json=/out/sbom.json >"$L/syft.log" 2>&1
rec syft "$([ -s "$R/grype/sbom.json" ] && echo PASS || echo FAIL)" "$(python3 -c 'import json,sys;c=json.load(open(sys.argv[1]))["components"];print("components=%d chrome=%s tor=%s"%(len(c),[x["name"] for x in c if "chrom" in x["name"].lower()][:3],[x["name"] for x in c if x["name"].lower()=="tor"]))' "$R/grype/sbom.json" 2>&1 | tail -1 | cut -c1-140)"
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$R/grype:/out" -v grypecache:/.cache "$GRYPE" docker:t:shelfmark -o json --file /out/all.json >"$L/grype.log" 2>&1
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$R/grype:/out" -v grypecache:/.cache "$GRYPE" docker:t:shelfmark --only-notfixed -o json --file /out/notfixed.json >"$L/grype-notfixed.log" 2>&1
sudo chmod -R a+rX "$R"
rec grype INFO "$(python3 -c 'import json,sys,collections as C
a=json.load(open(sys.argv[1]))["matches"];n=json.load(open(sys.argv[2]))["matches"]
print("all=%d notfixed=%d states=%s"%(len(a),len(n),dict(C.Counter(m["vulnerability"]["fix"]["state"] for m in a))))' "$R/grype/all.json" "$R/grype/notfixed.json" 2>&1 | tail -1 | cut -c1-150)"

# ---------- software outside the package manager
docker run --rm --entrypoint sh t:shelfmark -c 'for b in "$(readlink -f "$(command -v chromium)")" "$(command -v tor)"; do echo "== $b"; ldd "$b" 2>&1; done; chromium --version; tor --version | head -1; apk info -v 2>/dev/null; dpkg-query -W -f="\${Package} \${Version}\n" 2>/dev/null' >"$L/packages.txt" 2>&1
rec ldd_not_found INFO "count=$(grep -c 'not found' "$L/packages.txt")"
if [ "$V" = wolfi ]; then
    docker run --rm --entrypoint sh t:shelfmark -c 'for b in "$(readlink -f "$(command -v chromium)")" "$(command -v tor)"; do echo "== $b"; ldd "$b" | awk "/=>/{print \$3}" | sort -u | while read -r l; do printf "%s: " "$l"; apk info -W "$l" 2>&1 | head -1; done; done' >"$L/apk-owners.txt" 2>&1
    rec apk_owned INFO "libs=$(grep -c ': ' "$L/apk-owners.txt") unowned=$(grep -E ': ' "$L/apk-owners.txt" | grep -vc 'owned by')"
fi

# ---------- 4 default start: root start, gosu to uid 1000
start_app t:shelfmark
h=$(wait_health 180) && rec default.health PASS "secs=$h" || rec default.health FAIL "$h"
for _ in $(seq 1 45); do
    st=$(docker inspect -f '{{.State.Health.Status}}' app 2>/dev/null)
    [ "$st" = starting ] || break
    sleep 2
done
rec default.docker_healthcheck "$([ "$st" = healthy ] && echo PASS || echo FAIL)" "$st"
docker exec app ps -eo uid,args >"$L/default.ps.txt" 2>&1
rec default.app_uid INFO "$(grep -m1 gunicorn "$L/default.ps.txt" | awk '{print "gunicorn uid=" $1}')"
rc=$(smoke_exec default.smoke)
rec default.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line default.smoke)"
rec default.chrome_flags INFO "no-sandbox_in_cmdline=$(grep -c -- '--no-sandbox' "$L/default.smoke.ps.txt") chrome_uids=$(awk '{print $1}' "$L/default.smoke.ps.txt" | sort -u | tr '\n' ',')"
cf_case default.cloudflare
logs_app default
stop_app

# ---------- 5 RAR
samples=$(mktemp -d)
url=$(curl -s https://pypi.org/pypi/rarfile/json | python3 -c 'import json,sys;print([u["url"] for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0])')
curl -fsSL "$url" | tar -xz -C "$samples" --strip-components=3 --wildcards '*/test/files/*.rar'
chmod -R a+rX "$samples"
docker run --rm --user 1000:1000 -v "$samples:/rar:ro" -v "$KIT/rar.py:/tmp/rar.py:ro" --entrypoint python t:shelfmark /tmp/rar.py /rar >"$L/rar.json" 2>&1
rec rar INFO "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print("tool=%s ok=%d fail=%d"%(d["tool"],d["ok"],d["fail"]))' "$L/rar.json" 2>&1 | tail -1 | cut -c1-150)"

# ---------- 6 Debug by env, root start
start_app t:shelfmark -e DEBUG=true
h=$(wait_health 300) && rec debug_env.health PASS "secs=$h" || rec debug_env.health FAIL "$h"
rc=$(smoke_exec debug_env.smoke)
rec debug_env.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line debug_env.smoke)"
rec debug_env.recording INFO "mp4_bytes=$(mp4_size) ffmpeg=$(docker exec app sh -c 'command -v ffmpeg || echo none')"
docker exec -u 0 app bash /app/genDebug.sh >"$L/debug_env.gendebug.log" 2>&1
rec debug_env.gendebug "$([ $? = 0 ] && echo PASS || echo FAIL)" "$(docker exec app sh -c 'ls -1 /tmp/*.zip 2>/dev/null | wc -l') zip"
logs_app debug_env
stop_app

# ---------- 7 Debug only in the config file, root start
cfg=$(mktemp -d)
mkdir -p "$cfg/plugins"
echo '{"DEBUG": true}' >"$cfg/plugins/advanced.json"
chmod -R a+rwX "$cfg"
start_app t:shelfmark -v "$cfg:/config"
h=$(wait_health 300) && rec debug_cfg.health PASS "secs=$h" || rec debug_cfg.health FAIL "$h"
rc=$(smoke_exec debug_cfg.smoke)
rec debug_cfg.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line debug_cfg.smoke)"
rec debug_cfg.recording INFO "mp4_bytes=$(mp4_size) ffmpeg=$(docker exec app sh -c 'command -v ffmpeg || echo none')"
logs_app debug_cfg
stop_app

# ---------- 8 non-root start, Debug off and on
start_app t:shelfmark --user 1000:1000
h=$(wait_health 180) && rec nonroot.health PASS "secs=$h" || rec nonroot.health FAIL "$h"
rc=$(smoke_exec nonroot.smoke)
rec nonroot.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line nonroot.smoke)"
logs_app nonroot
start_app t:shelfmark --user 1000:1000 -e DEBUG=true
h=$(wait_health 180) && rec nonroot_debug.health PASS "secs=$h" || rec nonroot_debug.health FAIL "$h"
rc=$(smoke_exec nonroot_debug.smoke)
rec nonroot_debug.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line nonroot_debug.smoke)"
rec nonroot_debug.recording INFO "mp4_bytes=$(mp4_size) warned=$(grep -c 'ffmpeg is not installed' "$L/nonroot_debug.smoke.log")"
logs_app nonroot_debug
stop_app

# ---------- 9 Debug on, apt cannot reach a mirror (proxy pointed at a closed port)
if [ "$V" != wolfi ]; then
    aptno=$(mktemp)
    echo 'Acquire::http::Proxy "http://127.0.0.1:9"; Acquire::https::Proxy "http://127.0.0.1:9"; Acquire::Retries "0";' >"$aptno"
    chmod a+r "$aptno"
    t0=$SECONDS
    start_app t:shelfmark -e DEBUG=true -v "$aptno:/etc/apt/apt.conf.d/99block:ro"
    h=$(wait_health 300) && rec apt_fail.health PASS "secs=$h" || rec apt_fail.health FAIL "$h"
    rc=$(smoke_exec apt_fail.smoke)
    rec apt_fail.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line apt_fail.smoke)"
    logs_app apt_fail
    rec apt_fail.really_blocked INFO "ffmpeg=$(docker exec app sh -c 'command -v ffmpeg || echo none') could_not_install=$(grep -c 'Could not install ffmpeg' "$L/apt_fail.docker.log") warned=$(grep -c 'ffmpeg is not installed' "$L/apt_fail.smoke.log") mp4=$(mp4_size)"
    stop_app
    # No network at all: startup must not hang on apt.
    start_app t:shelfmark -e DEBUG=true --network none
    sleep 60
    rec no_network.state INFO "running=$(docker inspect -f '{{.State.Running}}' app) health_inside=$(docker exec app curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8084/api/health 2>&1)"
    logs_app no_network
    stop_app
fi

# ---------- ownership: Debug only in config, fresh volume and existing uid-1000 volume
own_check() { # label
    local label=$1
    docker exec app sh -c 'find /config /var/log/shelfmark /app -user root -not -path "/app/.venv/*" 2>/dev/null | sort' >"$L/$label.rootowned.txt" 2>&1
    docker exec app sh -c 'find /config /var/log/shelfmark -user root 2>/dev/null | sort' >"$L/$label.rootowned-data.txt" 2>&1
    local w=ok f
    for f in /config/.t /config/plugins/.t /var/log/shelfmark/.t; do docker exec -u 1000:1000 app sh -c "touch $f && rm $f" 2>/dev/null || w="fail:$f"; done
    rec "$label.ownership" "$([ "$w" = ok ] && [ ! -s "$L/$label.rootowned-data.txt" ] && echo PASS || echo FAIL)" "writes=$w root_in_data_dirs=$(wc -l <"$L/$label.rootowned-data.txt") root_in_app=$(wc -l <"$L/$label.rootowned.txt")"
}
docker volume rm -f smfresh >/dev/null 2>&1
docker volume create smfresh >/dev/null
docker run --rm --user 1000:1000 -v smfresh:/config --entrypoint sh t:shelfmark -c 'mkdir -p /config/plugins && echo "{\"DEBUG\": true}" >/config/plugins/advanced.json' >"$L/fresh-seed.txt" 2>&1
start_app t:shelfmark -v smfresh:/config
h=$(wait_health 300) && rec fresh_volume.health PASS "secs=$h" || rec fresh_volume.health FAIL "$h"
rc=$(smoke_exec fresh_volume.smoke)
rec fresh_volume.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc mp4=$(mp4_size)"
own_check fresh_volume
logs_app fresh_volume
stop_app
exist=$(mktemp -d)
sudo chown 1000:1000 "$exist"
start_app t:shelfmark -v "$exist:/config"
h=$(wait_health 180)
rec existing_volume.first_start INFO "debug_off secs=$h"
stop_app
sudo python3 -c 'import json,sys;p=sys.argv[1]+"/plugins/advanced.json";d=json.load(open(p));d["DEBUG"]=True;json.dump(d,open(p,"w"))' "$exist"
sudo chown 1000:1000 "$exist/plugins/advanced.json"
start_app t:shelfmark -v "$exist:/config"
h=$(wait_health 300) && rec existing_volume.health PASS "debug_config_only secs=$h" || rec existing_volume.health FAIL "$h"
rc=$(smoke_exec existing_volume.smoke)
rec existing_volume.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc mp4=$(mp4_size)"
own_check existing_volume
sudo find "$exist" -user root | wc -l | sed 's/^/root_owned_on_host=/' >"$L/existing_volume.hostroot.txt"
rec existing_volume.host_view INFO "$(cat "$L/existing_volume.hostroot.txt")"
logs_app existing_volume
stop_app

# ---------- 10 Tor
start_app t:shelfmark -e USING_TOR=true --cap-add NET_ADMIN --cap-add NET_RAW
h=$(wait_health 420) && rec tor.health PASS "secs=$h" || rec tor.health FAIL "$h"
logs_app tor
rec tor.routed "$(grep -q 'Traffic is routed through Tor' "$L/tor.docker.log" && echo PASS || echo FAIL)" "$(grep -m1 -E 'Traffic is|Could not reach|NOT using' "$L/tor.docker.log" | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<ip>/' | cut -c1-110)"
rec tor.check_api INFO "$(docker exec app curl -s --max-time 40 https://check.torproject.org/api/ip 2>&1 | sed -E 's/"IP":"[^"]*"/"IP":"<ip>"/' | cut -c1-80)"
rc=$(smoke_exec tor.smoke)
rec tor.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line tor.smoke)"
stop_app

# ---------- 11 WireGuard, with the runner as the other end of a real tunnel
sudo apt-get install -y -qq wireguard-tools >/dev/null 2>&1
wgd=$(mktemp -d)
srv_key=$(wg genkey); srv_pub=$(echo "$srv_key" | wg pubkey)
cli_key=$(wg genkey); cli_pub=$(echo "$cli_key" | wg pubkey)
gw=$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')
out_if=$(ip route show default | awk '{print $5; exit}')
sudo ip link add wgsrv type wireguard && {
    echo "$srv_key" >"$wgd/srv.key"
    sudo wg set wgsrv listen-port 51820 private-key "$wgd/srv.key" peer "$cli_pub" allowed-ips 10.66.66.2/32
    sudo ip addr add 10.66.66.1/24 dev wgsrv
    sudo ip link set wgsrv up
    sudo sysctl -q -w net.ipv4.ip_forward=1
    sudo iptables -I FORWARD 1 -i wgsrv -j ACCEPT
    sudo iptables -I FORWARD 1 -o wgsrv -j ACCEPT
    sudo iptables -t nat -A POSTROUTING -s 10.66.66.0/24 -o "$out_if" -j MASQUERADE
    sudo iptables -I INPUT 1 -p udp --dport 51820 -j ACCEPT
    rec wg.host_side PASS "kernel module ok"
} || rec wg.host_side FAIL "could not create the runner's interface"
cat >"$wgd/wg0.conf" <<CONF
[Interface]
PrivateKey = $cli_key
Address = 10.66.66.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = $srv_pub
Endpoint = $gw:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 15
CONF
chmod a+r "$wgd/wg0.conf"
start_app t:shelfmark -e USING_WIREGUARD=true -e LAN_NETWORK=172.16.0.0/12 --cap-add NET_ADMIN --cap-add NET_RAW \
    --sysctl net.ipv4.conf.all.src_valid_mark=1 --sysctl net.ipv6.conf.all.disable_ipv6=1 --sysctl net.ipv6.conf.default.disable_ipv6=1 \
    -v "$wgd/wg0.conf:/config/wg0.conf:ro"
h=$(wait_health 180) && rec wg.health PASS "secs=$h" || rec wg.health FAIL "$h"
logs_app wg
sed -i -E 's/(PrivateKey|PublicKey)( = |: ).*/\1 <redacted>/' "$L/wg.docker.log"
hs=$(sudo wg show wgsrv latest-handshakes 2>/dev/null | awk '{print $2}')
rec wg.handshake "$([ "${hs:-0}" -gt 0 ] && echo PASS || echo FAIL)" "latest=${hs:-none}"
before=$(sudo wg show wgsrv transfer 2>/dev/null | awk '{print $2}')
code=$(docker exec app curl -s -o /dev/null -w '%{http_code}' --max-time 25 https://example.com 2>&1)
after=$(sudo wg show wgsrv transfer 2>/dev/null | awk '{print $2}')
rec wg.egress_via_tunnel "$([ "$code" = 200 ] && [ "${after:-0}" -gt "${before:-0}" ] && echo PASS || echo FAIL)" "http=$code rx_before=${before:-?} rx_after=${after:-?}"
rc=$(smoke_exec wg.smoke)
rec wg.smoke "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc $(result_line wg.smoke)"
sudo ip link del wgsrv 2>/dev/null
if [ "$(docker inspect -f '{{.State.Running}}' app 2>/dev/null)" = true ]; then
    code=$(docker exec app curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://example.com 2>&1)
    rec wg.killswitch "$([ "$code" != 200 ] && echo PASS || echo FAIL)" "http_with_tunnel_down=$code"
else
    rec wg.killswitch NOTRUN "container not running"
fi
stop_app

# ---------- 12 lite
if docker image inspect t:shelfmark-lite >/dev/null 2>&1; then
    start_app t:shelfmark-lite
    h=$(wait_health 180) && rec lite.health PASS "secs=$h" || rec lite.health FAIL "$h"
    docker exec app ps -eo uid,args >"$L/lite.ps.txt" 2>&1
    logs_app lite
    stop_app
fi

# ---------- 13 sandbox: what does Chrome get as uid 1000 without --no-sandbox?
curl -fsSL https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json -o "$WS/moby.json"
python3 - "$WS/moby.json" "$WS/allow-ns.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
keep = []
for s in d["syscalls"]:
    names = [n for n in s["names"] if n not in ("clone", "unshare", "setns")]
    if names:
        s["names"] = names
        keep.append(s)
keep.append({"names": ["clone", "unshare", "setns"], "action": "SCMP_ACT_ALLOW"})
d["syscalls"] = keep
json.dump(d, open(sys.argv[2], "w"))
PY
cat >"$WS/Dockerfile.sbx" <<'DF'
FROM t:shelfmark
RUN sed -i 's/sandbox=False/sandbox=True/' /app/shelfmark/bypass/internal_bypasser.py && grep -c 'sandbox=True' /app/shelfmark/bypass/internal_bypasser.py
DF
docker build -q -t t:sbx -f "$WS/Dockerfile.sbx" "$WS" >"$L/sbx-build.log" 2>&1

sbx_case() { # name, then docker options
    local name=$1
    shift
    timeout -k 5 60 docker run --rm --user 1000:1000 -e HOME=/tmp/shelfmark/home "$@" -v "$KIT/sbx.py:/tmp/sbx.py:ro" --entrypoint sh t:shelfmark \
        -c 'mkdir -p "$HOME"; python /tmp/sbx.py' >"$L/sbx.$name.json" 2>&1
    rec "sandbox.$name.chrome" INFO "$(cut -c1-330 "$L/sbx.$name.json" | tail -1)"
    # Only worth the full app run if Chrome came up sandboxed.
    if grep -q '"renderer_pidns_isolated": true' "$L/sbx.$name.json"; then
        start_app t:sbx "$@"
        h=$(wait_health 180)
        rc=$(smoke_exec "sandbox.$name.smoke")
        rec "sandbox.$name.app_smoke" "$([ "$rc" = 0 ] && echo PASS || echo FAIL)" "rc=$rc health=$h $(result_line "sandbox.$name.smoke")"
        cf_case "sandbox.$name.cloudflare"
        stop_app
    fi
}

# Control: flag on, default profile.
timeout -k 5 60 docker run --rm --user 1000:1000 -e HOME=/tmp/shelfmark/home -v "$KIT/sbx.py:/tmp/sbx.py:ro" --entrypoint sh t:shelfmark \
    -c 'mkdir -p "$HOME"; python /tmp/sbx.py --no-sandbox' >"$L/sbx.control.json" 2>&1
rec sandbox.control_flag_on.chrome INFO "$(cut -c1-330 "$L/sbx.control.json" | tail -1)"
rec sandbox.host_userns_restrict INFO "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null)"
sbx_case default_host_default
sbx_case allowns_host_default --security-opt "seccomp=$WS/allow-ns.json"

rec finished PASS "elapsed=$SECONDS"
exit 0
