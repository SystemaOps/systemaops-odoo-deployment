#!/bin/bash
# Remote Phase 2 deployment script. Runs ON the customer VM.
#
# Transferred and executed by .github/workflows/deploy-to-vm.yml.
# It is self-contained: everything it needs is read from the extracted
# artifact's own metadata (deployment_summary.json, install_modules.json).
#
# Usage: remote_deploy.sh /path/to/extracted/workspace
set -euo pipefail

WORKSPACE_DIR="$(cd "${1:?usage: remote_deploy.sh <workspace_dir>}" && pwd)"
SUMMARY="$WORKSPACE_DIR/deployment_summary.json"
INSTALL="$WORKSPACE_DIR/install_modules.json"

if [[ ! -f "$SUMMARY" ]]; then
  echo "ERROR: deployment_summary.json not found in $WORKSPACE_DIR" >&2
  exit 1
fi

DEPLOYMENT_ID="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['deployment_id'])")"
DB_NAME="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['database_name'])")"
PREFIX="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['container_prefix'])")"
ODOO_PORT="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['odoo_port'])")"
DOMAIN="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['domain'])")"
VM_DOMAIN="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['vm_domain'])")"
MODULES="$(python3 -c "import json;print(','.join(json.load(open('$INSTALL'))['install_modules']))")"

TARGET_DOMAIN="${VM_DOMAIN:-$DOMAIN}"
ODOO_SERVICE="odoo_${PREFIX}"
DB_SERVICE="db_${PREFIX}"
NETWORK="odoo_net_${PREFIX}"

echo "==> Phase 2 deploy: $DEPLOYMENT_ID"
echo "    db=$DB_NAME services=$ODOO_SERVICE/$DB_SERVICE network=$NETWORK"
echo "    modules=$MODULES"

log() { echo "==> $*"; }

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "docker already installed ($(docker --version))"
  else
    log "installing docker"
    apt-get update -y >/dev/null
    apt-get install -y docker.io docker-compose-v2 python3 >/dev/null
    systemctl enable --now docker
  fi
  if ! docker compose version >/dev/null 2>&1; then
    mkdir -p /usr/local/lib/docker/cli-plugins
    ARCH="$(uname -m)"; [ "$ARCH" = "x86_64" ] && ARCH="x86_64"
    curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
  docker compose version
}

start_stack() {
  cd "$WORKSPACE_DIR"
  log "building and starting stack"
  for i in 1 2 3; do
    if docker compose up -d --build --wait 2>/dev/null || docker compose up -d --build; then
      break
    fi
    log "compose up attempt $i failed; retrying in 10s"
    [ "$i" = "3" ] && { echo "ERROR: stack failed to start after 3 attempts" >&2; exit 1; }
    sleep 10
  done

  log "waiting for db container healthy"
  for i in $(seq 1 60); do
    if docker exec "$DB_SERVICE" pg_isready -U "odoo_${PREFIX}" -d "$DB_NAME" >/dev/null 2>&1; then
      break
    fi
    [ "$i" = "60" ] && { echo "ERROR: db not ready after 60s" >&2; exit 1; }
    sleep 2
  done
}

init_database() {
  log "initializing database (base modules)"
  docker compose run --rm "$ODOO_SERVICE" odoo -d "$DB_NAME" -i base --stop-after-init --no-http

  if [[ -n "$MODULES" ]]; then
    log "installing modules: $MODULES"
    docker compose run --rm "$ODOO_SERVICE" odoo -d "$DB_NAME" -i "$MODULES" --stop-after-init --no-http
  fi

  log "restarting odoo to serve the installed database"
  docker compose restart "$ODOO_SERVICE"

  log "waiting for odoo to answer on port $ODOO_PORT"
  for i in $(seq 1 90); do
    if curl -fsS -o /dev/null "http://localhost:$ODOO_PORT/web/login" 2>/dev/null; then
      break
    fi
    [ "$i" = "90" ] && { echo "ERROR: odoo did not answer after 3 minutes" >&2; exit 1; }
    sleep 2
  done
}

setup_nginx() {
  if [[ -z "$TARGET_DOMAIN" ]]; then
    log "no domain configured; Odoo exposed directly on port $ODOO_PORT"
    return
  fi
  log "setting up nginx for domain $TARGET_DOMAIN"
  if ! docker ps -q --filter "name=nginx_${PREFIX}" | grep -q .; then
    docker run -d \
      --name "nginx_${PREFIX}" \
      --network "$NETWORK" \
      --restart unless-stopped \
      -p 80:80 \
      -p 443:443 \
      -v "$WORKSPACE_DIR/nginx.conf:/etc/nginx/conf.d/odoo.conf:ro" \
      nginx:alpine
  fi
  log "nginx running; add an A record for $TARGET_DOMAIN -> this server and issue TLS (certbot) manually"
}

register_monitoring() {
  MONITORING_DIR="$WORKSPACE_DIR/monitoring"
  if [[ ! -f "$MONITORING_DIR/docker-compose.monitoring.yml" ]]; then
    log "monitoring config not packaged; skipping"
    return
  fi
  log "starting monitoring stack (node-exporter :9100, prometheus :9090, grafana :3002, cadvisor :8080)"
  cd "$MONITORING_DIR"
  DB_PASSWORD="$(grep -m1 '^db_password' "$WORKSPACE_DIR/config/odoo.conf" | cut -d= -f2 | tr -d ' ')"
  ADMIN_PASSWORD="$(grep -m1 '^admin_passwd' "$WORKSPACE_DIR/config/odoo.conf" | cut -d= -f2 | tr -d ' ')"
  ODOO_NETWORK="$(docker network ls --format '{{.Name}}' | grep "odoo_net_${PREFIX}" | head -1 || true)"
  if [[ -z "$ODOO_NETWORK" ]]; then
    log "WARNING: could not find the odoo docker network; monitoring stack skipped"
    return 1
  fi
  export DB_USER="odoo_${PREFIX}"
  export DB_PASSWORD="${DB_PASSWORD:-odoo}"
  export DB_HOST="${DB_SERVICE}"
  export POSTGRES_DB="${DB_NAME}"
  export ODOO_NETWORK="${ODOO_NETWORK}"
  export GF_SECURITY_ADMIN_PASSWORD="${ADMIN_PASSWORD:?admin_passwd missing from odoo.conf}"
  export GRAFANA_PORT="3002"
  docker compose -f docker-compose.monitoring.yml up -d || {
    log "WARNING: monitoring stack failed to start; deploy continues"
    return 1
  }

  log "waiting for grafana dashboard to answer on port 3002"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://localhost:3002/api/health" 2>/dev/null; then
      break
    fi
    [ "$i" = "30" ] && { log "WARNING: grafana did not answer on :3002 after 60s"; }
    sleep 2
  done
}

cd "$WORKSPACE_DIR"
ensure_docker
start_stack
init_database
setup_nginx
register_monitoring || true

echo "==> Phase 2 deploy complete: http://${TARGET_DOMAIN:-$ODOO_PORT}" 