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
GRAFANA_PORT="$(python3 -c "import json;print(json.load(open('$SUMMARY')).get('grafana_port', 3002))")"
ADMIN_NAME="$(python3 -c "import json;print(json.load(open('$SUMMARY')).get('admin_name', 'admin'))")"
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

set_admin_login() {
  ADMIN_PASSWORD="$(grep -m1 '^admin_passwd' "$WORKSPACE_DIR/config/odoo.conf" | cut -d= -f2 | tr -d ' ')"
  log "setting ERP admin login to '$ADMIN_NAME'"
  docker compose run --rm -T "$ODOO_SERVICE" odoo shell -d "$DB_NAME" --no-http <<EOF || true
u = env['res.users'].search([('login','=','admin')], limit=1)
if u:
    u.login = '$ADMIN_NAME'
    u.password = '$ADMIN_PASSWORD'
    env.cr.commit()
EOF
  docker compose restart "$ODOO_SERVICE"
}

set_company_branding() {
  COMPANY_NAME="$(python3 -c "import json;print(json.load(open('$SUMMARY')).get('company_name', '') or '')" 2>/dev/null || true)"
  if [[ -z "$COMPANY_NAME" ]]; then
    log "no company_name in summary; skipping company branding"
    return
  fi
  log "branding ERP as '$COMPANY_NAME' (company name + monitoring menu)"
  docker compose run --rm -T "$ODOO_SERVICE" odoo shell -d "$DB_NAME" --no-http <<EOF || true
company = env['res.company'].search([], limit=1)
if company:
    company.name = '$COMPANY_NAME'
# Root monitoring menu -> company name; submenu -> 'Monitoring'
root = env['ir.ui.menu'].search([('name','in',['SystemaOps','Monitoring']),('parent_id','=',False)], limit=1)
if root:
    root.name = '$COMPANY_NAME'
sub = env['ir.ui.menu'].search([('name','in',['$COMPANY_NAME','SystemaOps'])], limit=1)
if sub and sub.parent_id and sub.parent_id.id != sub.id:
    sub.name = 'Monitoring'
env.cr.commit()
EOF
  docker compose restart "$ODOO_SERVICE"
}

setup_nginx() {
  if [[ -z "$TARGET_DOMAIN" ]]; then
    log "no domain configured; Odoo exposed directly on port $ODOO_PORT"
    return
  fi
  log "setting up nginx for domain $TARGET_DOMAIN"

  WEBROOT="$WORKSPACE_DIR/certbot-webroot"
  mkdir -p "$WEBROOT"

  # Bootstrap HTTP config serves the ACME challenge so certbot can validate.
  docker rm -f "nginx_${PREFIX}" >/dev/null 2>&1 || true
  docker run -d \
    --name "nginx_${PREFIX}" \
    --network "$NETWORK" \
    --restart unless-stopped \
    -p 80:80 \
    -p 443:443 \
    -v "$WORKSPACE_DIR/nginx.conf:/etc/nginx/conf.d/odoo.conf:ro" \
    -v "$WEBROOT:/var/www/certbot" \
    -v "$WORKSPACE_DIR/certbot:/etc/letsencrypt" \
    nginx:alpine

  log "waiting for nginx to answer on port 80"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://localhost/.well-known/acme-challenge/probe" 2>/dev/null || docker exec "nginx_${PREFIX}" nginx -t >/dev/null 2>&1; then
      break
    fi
    [ "$i" = "30" ] && { log "WARNING: nginx did not become ready; skipping TLS issuance"; }
    sleep 2
  done

  # Issue certificate via certbot (webroot method).
  if docker run --rm \
      -v "$WEBROOT:/var/www/certbot" \
      -v "$WORKSPACE_DIR/certbot:/etc/letsencrypt" \
      certbot/certbot certonly \
      --webroot -w /var/www/certbot \
      -d "$TARGET_DOMAIN" \
      --agree-tos --no-eff-email \
      -m "${CERTBOT_EMAIL:-admin@systemaops.com}" \
      --non-interactive; then
    log "certificate issued for $TARGET_DOMAIN; enabling HTTPS"
    if [[ -f "$WORKSPACE_DIR/nginx-ssl.conf" ]]; then
      docker rm -f "nginx_${PREFIX}" >/dev/null 2>&1 || true
      docker run -d \
        --name "nginx_${PREFIX}" \
        --network "$NETWORK" \
        --restart unless-stopped \
        -p 80:80 \
        -p 443:443 \
        -v "$WORKSPACE_DIR/nginx-ssl.conf:/etc/nginx/conf.d/odoo.conf:ro" \
        -v "$WEBROOT:/var/www/certbot" \
        -v "$WORKSPACE_DIR/certbot:/etc/letsencrypt" \
        nginx:alpine
    fi
  else
    log "WARNING: certbot could not obtain a certificate for $TARGET_DOMAIN"
    log "         ensure the domain's A record points to this server and retry"
  fi

  # Install a daily renewal timer (systemd) so the cert never expires.
  RENEW_UNIT="/etc/systemd/system/systemaops-renew-${PREFIX}.service"
  RENEW_TIMER="/etc/systemd/system/systemaops-renew-${PREFIX}.timer"
  cat > "$RENEW_UNIT" <<EOF
[Unit]
Description=Renew Let's Encrypt certificate for $TARGET_DOMAIN

[Service]
Type=oneshot
ExecStart=docker run --rm -v $WEBROOT:/var/www/certbot -v $WORKSPACE_DIR/certbot:/etc/letsencrypt certbot/certbot renew --webroot -w /var/www/certbot
ExecStartPost=/bin/sh -c 'docker exec nginx_${PREFIX} nginx -s reload 2>/dev/null || true'
EOF
  cat > "$RENEW_TIMER" <<EOF
[Unit]
Description=Daily Let's Encrypt renewal for $TARGET_DOMAIN

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable --now "systemaops-renew-${PREFIX}.timer" 2>/dev/null || \
      log "WARNING: could not enable renew timer"
  else
    (crontab -l 2>/dev/null; echo "0 3 * * * docker run --rm -v $WEBROOT:/var/www/certbot -v $WORKSPACE_DIR/certbot:/etc/letsencrypt certbot/certbot renew --webroot -w /var/www/certbot >> /var/log/systemaops-renew-${PREFIX}.log 2>&1") | crontab -
  fi
  log "nginx running with HTTPS for $TARGET_DOMAIN; renewal scheduled"
}

setup_backups() {
  log "installing automated database backups"
  BACKUP_ROOT="/srv/backups"
  BACKUP_SCRIPT="/usr/local/sbin/systemaops-backup.sh"
  mkdir -p "$BACKUP_ROOT"

  cp "$WORKSPACE_DIR/backup_odoo.sh" "$BACKUP_SCRIPT"
  chmod +x "$BACKUP_SCRIPT"

  OFF_TARGET="$(python3 -c "import json;print(json.load(open('$SUMMARY')).get('offsite_target',''))" 2>/dev/null || true)"

  BACKUP_UNIT="/etc/systemd/system/systemaops-backup.service"
  BACKUP_TIMER="/etc/systemd/system/systemaops-backup.timer"
  cat > "$BACKUP_UNIT" <<EOF
[Unit]
Description=SystemaOps customer Odoo database backups

[Service]
Type=oneshot
Environment=BACKUP_ROOT=$BACKUP_ROOT
Environment=RETENTION_DAYS=7
Environment=OFFSITE_TARGET=$OFF_TARGET
ExecStart=$BACKUP_SCRIPT $WORKSPACE_DIR/..
EOF
  cat > "$BACKUP_TIMER" <<EOF
[Unit]
Description=Nightly SystemaOps customer backups

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable --now systemaops-backup.timer 2>/dev/null || \
      log "WARNING: could not enable backup timer"
  else
    (crontab -l 2>/dev/null; echo "30 2 * * * OFFSITE_TARGET=$OFF_TARGET $BACKUP_SCRIPT $WORKSPACE_DIR/.. >> /var/log/systemaops-backup.log 2>&1") | crontab -
  fi

  log "running initial backup"
  BACKUP_ROOT="$BACKUP_ROOT" RETENTION_DAYS=7 OFFSITE_TARGET="$OFF_TARGET" "$BACKUP_SCRIPT" "$WORKSPACE_DIR/.." && \
    log "initial backup completed to $BACKUP_ROOT${OFF_TARGET:+ and offsite to $OFF_TARGET}" || \
    log "WARNING: initial backup reported a problem (containers may still be starting)"
}

register_monitoring() {
  MONITORING_DIR="$WORKSPACE_DIR/monitoring"
  if [[ ! -f "$MONITORING_DIR/docker-compose.monitoring.yml" ]]; then
    log "monitoring config not packaged; skipping"
    return
  fi
  log "starting monitoring stack (node-exporter :9100, prometheus :9090, grafana :$GRAFANA_PORT, cadvisor :8080)"
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
  export GRAFANA_PORT="${GRAFANA_PORT:-3002}"
  docker compose -f docker-compose.monitoring.yml up -d || {
    log "WARNING: monitoring stack failed to start; deploy continues"
    return 1
  }

  log "waiting for grafana dashboard to answer on port $GRAFANA_PORT"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://localhost:${GRAFANA_PORT}/api/health" 2>/dev/null; then
      break
    fi
    [ "$i" = "30" ] && { log "WARNING: grafana did not answer on :$GRAFANA_PORT after 60s"; }
    sleep 2
  done
}

cd "$WORKSPACE_DIR"
ensure_docker
start_stack
init_database
set_admin_login
set_company_branding
setup_nginx
register_monitoring || true
setup_backups || true

echo "==> Phase 2 deploy complete: http://${TARGET_DOMAIN:-$ODOO_PORT}" 