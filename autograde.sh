#!/usr/bin/env bash
# AutoGrade launcher - macOS and Linux.
#
#   ./autograde.sh start      open AutoGrade (installs it the first time)
#   ./autograde.sh stop       shut it down, keeping everything
#   ./autograde.sh restart    stop then start
#   ./autograde.sh update     rebuild after unpacking a new version
#   ./autograde.sh backup     save a copy into ./backups
#   ./autograde.sh restore    go back to a saved copy
#   ./autograde.sh status     is it running?
#   ./autograde.sh logs       the last 100 lines, for support
#
# On Windows use the "Start AutoGrade" file instead.
set -uo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.local.yml"
DEFAULT_PORT=8501
DEFAULT_API_PORT=8000

GREEN=$(printf '\033[32m'); YELLOW=$(printf '\033[33m')
RED=$(printf '\033[31m'); BOLD=$(printf '\033[1m'); OFF=$(printf '\033[0m')

say()  { printf '%s\n' "$*"; }
head_() { printf '\n%s%s%s\n' "$BOLD" "$*" "$OFF"; }
ok()   { printf '  %sOK%s   %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '  %s...%s  %s\n' "$YELLOW" "$OFF" "$*"; }
fail() {
  printf '\n  %sPROBLEM%s  %s\n' "$RED" "$OFF" "$1"
  [ $# -gt 1 ] && printf '\n  What to do: %s\n' "$2"
  printf '\n  If you are stuck, see TROUBLESHOOTING.md in this folder.\n\n'
  exit 1
}

# ---------------------------------------------------------------- docker
find_compose() {
  if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose); return 0; fi
  if command -v docker-compose >/dev/null 2>&1; then COMPOSE=(docker-compose); return 0; fi
  return 1
}

compose() { "${COMPOSE[@]}" -f "$COMPOSE_FILE" "$@"; }

require_docker() {
  command -v docker >/dev/null 2>&1 || fail \
    "Docker Desktop is not installed." \
    "Install it from https://docs.docker.com/get-docker/ then try again. INSTALL.md step 1 has the details."
  if ! docker info >/dev/null 2>&1; then
    if [ "$(uname)" = "Darwin" ] && [ -d "/Applications/Docker.app" ]; then
      warn "Docker Desktop is not running. Starting it - this takes a minute."
      open -a Docker
      for _ in $(seq 1 90); do
        sleep 2
        docker info >/dev/null 2>&1 && break
      done
    fi
  fi
  docker info >/dev/null 2>&1 || fail \
    "Docker is installed but not running." \
    "Start Docker Desktop yourself, wait for the whale icon to settle, then try again."
  find_compose || fail \
    "Docker is installed but Docker Compose is missing." \
    "Update Docker Desktop from https://docs.docker.com/get-docker/"
  ok "Docker is running"
}

# ------------------------------------------------------------------ .env
gen() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 96 | tr -d '\n=+/' | cut -c1-"${1:-48}"
  else
    head -c 400 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-"${1:-48}"
  fi
}

port_free() {
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}

find_free_port() {
  local start=$1 p
  for p in $(seq "$start" $((start + 20))); do
    port_free "$p" && { printf '%s' "$p"; return; }
  done
  printf '%s' "$start"
}

env_value() {
  [ -f .env ] || return 0
  grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-
}

port()     { local v; v=$(env_value AUTOGRADE_PORT);     printf '%s' "${v:-$DEFAULT_PORT}"; }
api_port() { local v; v=$(env_value AUTOGRADE_API_PORT); printf '%s' "${v:-$DEFAULT_API_PORT}"; }

write_env() {
  head_ "First run - setting AutoGrade up"
  local p a
  p=$(find_free_port "$DEFAULT_PORT")
  a=$(find_free_port "$DEFAULT_API_PORT")
  [ "$p" != "$DEFAULT_PORT" ] && warn "Port $DEFAULT_PORT is in use; using $p instead"

  cat > .env <<ENVEOF
# Written by the AutoGrade launcher. You do not need to edit this file.
#
# Your AI provider and your Canvas connection are configured inside
# AutoGrade, under Settings. Nothing here needs your attention.

ENVIRONMENT=production

# Where AutoGrade appears in your browser.
AUTOGRADE_PORT=${p}
AUTOGRADE_API_PORT=${a}

# --- generated secrets: do not share, do not change once in use ---
SECRET_KEY=$(gen 48)
CREDENTIAL_ENCRYPTION_KEY=$(gen 48)
POSTGRES_PASSWORD=$(gen 24)

# Accounts are created inside AutoGrade by whoever installed it.
ALLOW_OPEN_REGISTRATION=false

# --- uploads ---
UPLOAD_DIR=/app/uploads
MAX_FILE_SIZE_MB=50
MAX_REQUEST_BODY_MB=300

# --- automatic backups, into the backups folder next to this file ---
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_DAYS=30
ENVEOF
  chmod 600 .env 2>/dev/null || true
  ok "Settings written"
}

# ---------------------------------------------------------------- health
wait_healthy() {
  local deadline=$((SECONDS + ${2:-300})) shown=0
  while [ $SECONDS -lt $deadline ]; do
    if curl -sf "http://127.0.0.1:$1/api/health" >/dev/null 2>&1; then return 0; fi
    [ $shown -eq 0 ] && { warn "Waiting for AutoGrade to be ready..."; shown=1; }
    sleep 3
  done
  return 1
}

open_browser() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1
  fi
}

# --------------------------------------------------------------- actions
do_start() {
  say ""
  say "${BOLD}AutoGrade${OFF}"
  say "========="
  require_docker

  local first_run=0
  [ -f .env ] || first_run=1
  [ $first_run -eq 1 ] && write_env
  mkdir -p backups

  if [ $first_run -eq 1 ]; then
    head_ "Building AutoGrade"
    say  "  The first time takes 5 to 10 minutes and prints a lot of text."
    say  "  You only wait this long once."
    say  ""
  else
    head_ "Starting AutoGrade"
  fi

  compose up -d --build || fail "AutoGrade did not start." \
    "Run ./autograde.sh logs and look at the last few lines."

  head_ "Checking that everything is working"
  wait_healthy "$(api_port)" || fail "AutoGrade started but is not answering." \
    "Wait a minute and try again. If it keeps happening, see TROUBLESHOOTING.md."
  ok "Database, grading worker and interface are all running"

  local url="http://localhost:$(port)"
  head_ "AutoGrade is ready"
  say "  Opening $url in your browser."
  say ""
  if [ $first_run -eq 1 ]; then
    say "  The first account you create becomes the administrator."
    say "  Create yours now, then set your AI provider under"
    say "  Settings -> AI providers."
    say ""
  fi
  open_browser "$url"
}

do_stop() {
  say ""; head_ "Stopping AutoGrade"
  require_docker
  compose stop
  ok "Stopped. Your courses, grades and files are safe."
  say ""
}

do_update() {
  say ""; head_ "Updating AutoGrade"
  require_docker
  say "  Taking a backup first, so this can be undone."
  do_backup quiet
  compose up -d --build || fail "The update did not finish." \
    "Your backup is in the backups folder. See TROUBLESHOOTING.md."
  wait_healthy "$(api_port)" || fail "AutoGrade did not come back." \
    "Run ./autograde.sh restore to go back to the backup taken a moment ago."
  ok "Updated and running"
  say ""
}

do_backup() {
  [ "${1:-}" = "quiet" ] || { say ""; head_ "Backing up"; }
  require_docker
  local stamp name
  stamp=$(date +%Y-%m-%d-%H%M)
  name="autograde-$stamp"

  compose exec -T db pg_dump -U autograde -d autograde -Fc -f "/backups/$name.dump" \
    || fail "Could not back up the gradebook." "Is AutoGrade running? Start it first."

  compose exec -T api tar czf "/tmp/$name-files.tgz" -C /app/uploads .
  compose cp "api:/tmp/$name-files.tgz" "backups/$name-files.tgz" >/dev/null

  ok "Saved to the backups folder:"
  say "     $name.dump          the gradebook"
  say "     $name-files.tgz     the submitted files"
  say ""
  say "  Copy that folder somewhere else from time to time. A backup on the"
  say "  same computer does not survive losing the computer."
  say ""
}

do_restore() {
  say ""; head_ "Restoring from a backup"
  say "  This replaces everything currently in AutoGrade."
  say ""
  require_docker

  local dumps=() i=1
  while IFS= read -r f; do dumps+=("$f"); done < <(ls -t backups/*.dump 2>/dev/null)
  [ ${#dumps[@]} -gt 0 ] || fail "There are no backups in the backups folder." \
    "Run ./autograde.sh backup to make one."

  say "  Which backup?"
  say ""
  for f in "${dumps[@]}"; do
    printf '    %d) %s\n' "$i" "$(basename "$f")"
    i=$((i + 1))
  done
  say ""
  read -r -p "  Type a number and press Enter (or press Enter to cancel): " choice
  [ -n "$choice" ] || { say "  Cancelled."; return; }
  local dump="${dumps[$((choice - 1))]:-}"
  [ -n "$dump" ] || { say "  Not a valid choice."; return; }

  say ""
  warn "Everything now in AutoGrade will be replaced by $(basename "$dump")."
  read -r -p "  Type RESTORE to continue: " confirm
  [ "$confirm" = "RESTORE" ] || { say "  Cancelled."; return; }

  compose stop api worker frontend >/dev/null
  compose start db >/dev/null
  sleep 5
  compose exec -T db pg_restore -U autograde -d autograde --clean --if-exists \
    "/backups/$(basename "$dump")"
  # pg_restore returns non-zero for harmless "does not exist" notices on a
  # --clean restore, so the health check below decides whether this worked.

  compose start api worker frontend >/dev/null
  local files="backups/$(basename "$dump" .dump)-files.tgz"
  if [ -f "$files" ]; then
    sleep 5
    compose cp "$files" "api:/tmp/restore-files.tgz" >/dev/null
    compose exec -T api tar xzf /tmp/restore-files.tgz -C /app/uploads
    ok "Submitted files restored"
  else
    warn "No matching files archive; grades restored without the submissions."
  fi

  wait_healthy "$(api_port)" \
    && ok "Restored. Open AutoGrade and check a course you recognise." \
    || fail "AutoGrade did not come back after the restore." \
            "Run ./autograde.sh start. If it still fails, see TROUBLESHOOTING.md."
  say ""
}

do_status() {
  say ""; head_ "AutoGrade status"
  require_docker
  compose ps
  say ""
  if curl -sf "http://127.0.0.1:$(api_port)/api/health" >/dev/null 2>&1; then
    ok "Answering normally"
  else
    warn "Not answering. Run ./autograde.sh start"
  fi
  say ""
  say "  Web address: http://localhost:$(port)"
  say ""
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  update)  do_update ;;
  backup)  do_backup ;;
  restore) do_restore ;;
  status)  do_status ;;
  logs)    require_docker; compose logs --tail 100 ;;
  *)       say "Usage: ./autograde.sh [start|stop|restart|update|backup|restore|status|logs]" ;;
esac
