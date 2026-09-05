#!/bin/sh
# Periodic PostgreSQL backup with retention.
#
# Deliberately a shell loop rather than cron: the container is the schedule,
# so `docker compose ps` shows whether backups are running and
# `docker compose logs backup` shows whether they are succeeding. A cron
# daemon inside a container fails quietly, which is the worst property a
# backup can have.
#
# Each run writes a compressed custom-format dump (pg_restore can read it
# selectively) and then deletes dumps older than the retention window.
#
# Restore is documented in DEPLOYMENT.md - and a backup nobody has restored
# is not a backup, so please run that drill once before term starts.
set -eu

BACKUP_DIR=/backups
UPLOAD_DIR=/uploads
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

log() {
    # One JSON object per line, matching the application's log format.
    printf '{"ts":"%s","service":"backup","message":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1"
}

log "backup service started (every ${INTERVAL_HOURS}h, keeping ${RETENTION_DAYS}d)"

while true; do
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    TARGET="${BACKUP_DIR}/autograde-${STAMP}.dump"

    if pg_dump -h db -U autograde -d autograde -Fc -f "$TARGET.partial" 2>/tmp/err; then
        # Rename only on success, so a partial dump is never mistaken for a
        # usable one by the retention sweep or by a panicking operator.
        mv "$TARGET.partial" "$TARGET"
        log "wrote $(basename "$TARGET") ($(du -h "$TARGET" | cut -f1))"

        # Student files live outside the database. A dump on its own restores
        # a gradebook whose submissions have all vanished, so the archive is
        # written beside it under the same name - which is also how Restore
        # finds it. Automatic backups used to skip this, so the newest backup
        # in the list, the one a professor would naturally pick, was the one
        # that could not bring their students' files back.
        if [ -d "$UPLOAD_DIR" ]; then
            FILES="${BACKUP_DIR}/autograde-${STAMP}-files.tgz"
            if tar czf "$FILES.partial" -C "$UPLOAD_DIR" . 2>/tmp/err; then
                mv "$FILES.partial" "$FILES"
                log "wrote $(basename "$FILES") ($(du -h "$FILES" | cut -f1))"
            else
                rm -f "$FILES.partial"
                log "FILE ARCHIVE FAILED: $(tr -d '\n' < /tmp/err | head -c 200)"
            fi
        fi
    else
        rm -f "$TARGET.partial"
        log "BACKUP FAILED: $(tr -d '\n' < /tmp/err | head -c 300)"
    fi

    DELETED=$(find "$BACKUP_DIR" \( -name 'autograde-*.dump' -o \
        -name 'autograde-*-files.tgz' \) -type f \
        -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
    [ "$DELETED" -gt 0 ] && log "pruned ${DELETED} file(s) older than ${RETENTION_DAYS}d"

    sleep "$((INTERVAL_HOURS * 3600))"
done
