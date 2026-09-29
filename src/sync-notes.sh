#!/bin/bash
# sync-notes.sh
# Syncs files from the folders specified in sources.conf into the notes repo, then auto commit & push

set -o pipefail   # so `git pull | tee` reports git's failure, not tee's success

# ─── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine the profile name: env var > .sync-profile file > hostname
if [[ -n "$SYNC_PROFILE" ]]; then
    PROFILE="$SYNC_PROFILE"
elif [[ -f "$SCRIPT_DIR/.sync-profile" ]]; then
    PROFILE="$(head -1 "$SCRIPT_DIR/.sync-profile" | tr -d '[:space:]')"
else
    PROFILE="$(hostname -s)"
fi

# Config file priority: command-line argument > sources.<profile>.conf > sources.conf
if [[ -n "$1" ]]; then
    CONFIG_FILE="$1"
elif [[ -f "$SCRIPT_DIR/sources.${PROFILE}.conf" ]]; then
    CONFIG_FILE="$SCRIPT_DIR/sources.${PROFILE}.conf"
else
    CONFIG_FILE="$SCRIPT_DIR/sources.conf"
fi

NOTES_REPO="${NOTES_REPO:-$(pwd)}"              # defaults to the current working directory, can be overridden via env var
LOG_FILE="$SCRIPT_DIR/sync-notes.log"

# ─── Utility functions ─────────────────────────────────────────────────────────

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "ERROR: $*"
    exit 1
}

# ─── Pre-flight checks ─────────────────────────────────────────────────────────

[[ -f "$CONFIG_FILE" ]] || die "Config file not found: $CONFIG_FILE"
[[ -d "$NOTES_REPO" ]] || die "Notes repo not found: $NOTES_REPO"
command -v rsync &>/dev/null || die "rsync is not installed"
command -v git &>/dev/null || die "git is not installed"

# ─── Git pull (pull the latest changes before rsync) ──────────────────────────

log "Starting git pull"
cd "$NOTES_REPO" || die "Failed to enter the notes repo"
git pull --rebase 2>&1 | tee -a "$LOG_FILE" || die "git pull failed, please resolve conflicts manually"

# ─── Parse INI ─────────────────────────────────────────────────────────────────
# Read the config, and run the sync for the previous group each time a new [section] is encountered

do_sync() {
    local section="$1"
    local src="$2"
    local dst="$3"
    local include_ext="$4"
    local exclude_file="$5"
    local exclude_dir="$6"
    local recursive="$7"

    # Expand ~
    src="${src/#\~/$HOME}"
    local target="$NOTES_REPO/$dst"

    log "── [$section] ──────────────────────────────"

    # Check that the source exists
    if [[ ! -d "$src" ]]; then
        log "WARN: source folder does not exist, skipping: $src"
        return
    fi

    mkdir -p "$target"

    # ── Build the rsync arguments ──────────────────────────────

    local rsync_args=(-a --delete)

    # When recursive = no, only sync the top level
    if [[ "$recursive" == "no" ]]; then
        rsync_args+=(--max-depth=1)
    fi

    # exclude_dir: exclude the specified subfolders
    if [[ -n "$exclude_dir" ]]; then
        IFS=',' read -ra dirs <<< "$exclude_dir"
        for d in "${dirs[@]}"; do
            d="${d// /}"   # strip whitespace
            rsync_args+=(--exclude="$d/")
        done
    fi

    # exclude_file: exclude the specified filenames
    if [[ -n "$exclude_file" ]]; then
        IFS=',' read -ra files <<< "$exclude_file"
        for f in "${files[@]}"; do
            f="${f// /}"
            rsync_args+=(--exclude="$f")
        done
    fi

    # include_ext: only sync the specified extensions
    if [[ -n "$include_ext" ]]; then
        rsync_args+=(--include="*/")   # folders must be included for recursion to work
        IFS=',' read -ra exts <<< "$include_ext"
        for ext in "${exts[@]}"; do
            ext="${ext// /}"
            rsync_args+=(--include="*.$ext")
        done
        rsync_args+=(--exclude="*")    # exclude everything else
    fi

    log "rsync $src -> $target"
    rsync "${rsync_args[@]}" "$src/" "$target/" 2>&1 | tee -a "$LOG_FILE"
    log "Done: [$section]"
}

# ─── Main parsing loop ─────────────────────────────────────────────────────────

current_section=""
src="" dst="" include_ext="" exclude_file="" exclude_dir="" recursive="yes"

flush() {
    if [[ -n "$current_section" && -n "$src" && -n "$dst" ]]; then
        do_sync "$current_section" "$src" "$dst" \
                "$include_ext" "$exclude_file" "$exclude_dir" "$recursive"
    fi
    # reset
    src="" dst="" include_ext="" exclude_file="" exclude_dir="" recursive="yes"
}

while IFS= read -r line || [[ -n "$line" ]]; do
    # skip blank lines and comments
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    # detect [section]
    if [[ "$line" =~ ^\[(.+)\]$ ]]; then
        flush
        current_section="${BASH_REMATCH[1]}"
        continue
    fi

    # parse key = value
    if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        val="${BASH_REMATCH[2]}"
        key="${key// /}"   # strip whitespace
        val="${val# }"     # strip leading whitespace
        val="${val% }"     # strip trailing whitespace

        case "$key" in
            src)          src="$val" ;;
            dst)          dst="$val" ;;
            include_ext)  include_ext="$val" ;;
            exclude_file) exclude_file="$val" ;;
            exclude_dir)  exclude_dir="$val" ;;
            recursive)    recursive="$val" ;;
            *)            log "WARN: unknown parameter: $key" ;;
        esac
    fi
done < "$CONFIG_FILE"

flush   # handle the last section

# ─── Git commit & push ──────────────────────────────────────────────────────────

log "────────────────────────────────────────────"
log "Starting git sync"

cd "$NOTES_REPO" || die "Failed to enter the notes repo"

if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    git commit -m "auto-sync: $(date '+%Y-%m-%d %H:%M:%S')"
    git push 2>&1 | tee -a "$LOG_FILE"
    log "git push done"
else
    log "No changes, skipping git commit"
fi

log "All done"
