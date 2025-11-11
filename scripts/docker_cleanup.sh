#!/usr/bin/env bash
set -euo pipefail

# scripts/clean_docker_project.sh
#
# Usage:
#   ./scripts/clean_docker_project.sh -p <project_name> [-e .env.file] [-s ./db.sqlite3] [-y]
#
# Examples:
#   ./scripts/clean_docker_project.sh -p samtech__iot -e .env.samtech_ -s ./db.sqlite3
#   ./scripts/clean_docker_project.sh -p samtech__iot -y
#

PROJECT=""
ENVFILE=""
SQLITE_PATH=""
ASSUME_YES=false

usage() {
  cat <<EOF
Usage: $0 -p <project_name> [-e .env.file] [-s <sqlite_path>] [-y]

Options:
  -p  --project      Project name (compose project prefix), e.g. samtech__iot
  -e  --env-file     Optional .env file used with docker compose
  -s  --sqlite-path  Optional local sqlite path to delete
  -y  --yes          Assume yes to all prompts (non-interactive)
  -h  --help         Show this help
EOF
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--project) PROJECT="$2"; shift 2;;
    -e|--env-file) ENVFILE="$2"; shift 2;;
    -s|--sqlite-path) SQLITE_PATH="$2"; shift 2;;
    -y|--yes) ASSUME_YES=true; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if [[ -z "$PROJECT" ]]; then
  echo "Error: project is required."
  usage
  exit 1
fi

confirm() {
  if [[ "$ASSUME_YES" = true ]]; then
    return 0
  fi
  read -r -p "$1 [y/N]: " ans
  case "${ans:-n}" in
    y|Y|yes|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

echo "Target project: $PROJECT"
[[ -n "$ENVFILE" ]] && echo "Env-file: $ENVFILE"
[[ -n "$SQLITE_PATH" ]] && echo "Sqlite: $SQLITE_PATH"

# 1) Prefer using docker compose down if env-file provided or if user wants
if [[ -n "$ENVFILE" ]]; then
  echo
  echo "=== Step 1: docker compose down (preferred) ==="
  CMD="docker compose --env-file \"$ENVFILE\" -p \"$PROJECT\" down --rmi all --volumes --remove-orphans"
  echo "Command: $CMD"
  if confirm "Run compose down for project $PROJECT now?"; then
    eval "$CMD"
  else
    echo "Skipped compose down."
  fi
else
  echo
  echo "No env-file provided; will proceed with container-level removal."
fi

# 2) Stop & remove any running/stopped containers matching project
echo
echo "=== Step 2: Stop & remove containers matching project string ==="
CONTAINER_IDS=$(docker ps -a --filter "name=${PROJECT}" -q || true)
if [[ -n "$CONTAINER_IDS" ]]; then
  echo "Containers found:"
  docker ps -a --filter "name=${PROJECT}" --format "ID={{.ID}}\tNAME={{.Names}}\tIMAGE={{.Image}}"
  if confirm "Stop and remove these containers?"; then
    docker rm -f $CONTAINER_IDS
    echo "Containers removed."
  else
    echo "Left containers in place."
  fi
else
  echo "No containers found for project prefix ${PROJECT}."
fi

# 3) Remove volumes with project prefix
echo
echo "=== Step 3: Remove volumes with prefix '${PROJECT}' ==="
VOLS=$(docker volume ls --format '{{.Name}}' | grep "^${PROJECT}" || true)
if [[ -n "$VOLS" ]]; then
  echo "Volumes found:"
  echo "$VOLS"
  if confirm "Remove these volumes (destructive)?"; then
    echo "$VOLS" | xargs -r docker volume rm
    echo "Volumes removed."
  else
    echo "Volumes left in place."
  fi
else
  echo "No matching volumes found."
fi

# 4) Remove images containing project string
echo
echo "=== Step 4: Remove images whose repo/tag contains '${PROJECT}' ==="
IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep "${PROJECT}" || true)
if [[ -n "$IMAGES" ]]; then
  echo "Images matching:"
  echo "$IMAGES"
  if confirm "Remove these images?"; then
    echo "$IMAGES" | awk '{print $2}' | xargs -r docker rmi -f
    echo "Images removed."
  else
    echo "Images left in place."
  fi
else
  echo "No images found containing project string."
fi

# 5) Remove networks created for the project
echo
echo "=== Step 5: Remove networks with prefix '${PROJECT}' ==="
NETS=$(docker network ls --format '{{.Name}}' | grep "^${PROJECT}" || true)
if [[ -n "$NETS" ]]; then
  echo "Networks found:"
  echo "$NETS"
  if confirm "Remove these networks?"; then
    echo "$NETS" | xargs -r docker network rm
    echo "Networks removed."
  else
    echo "Networks left in place."
  fi
else
  echo "No networks found with that prefix."
fi

# 6) Optional: delete sqlite file
if [[ -n "$SQLITE_PATH" ]]; then
  echo
  echo "=== Step 6: Optional sqlite removal ==="
  if [[ -f "$SQLITE_PATH" ]]; then
    if confirm "Delete sqlite file at $SQLITE_PATH?"; then
      rm -f "$SQLITE_PATH"
      echo "Deleted $SQLITE_PATH"
    else
      echo "Left sqlite file."
    fi
  else
    echo "No sqlite file found at $SQLITE_PATH"
  fi
fi

# 7) Final prune (optional)
echo
if confirm "Run final 'docker system prune -af --volumes' to remove dangling resources (very destructive)?"; then
  docker system prune -af --volumes
  echo "System prune complete."
else
  echo "Skipped final system prune."
fi

echo
echo "Cleanup finished for project: $PROJECT"

