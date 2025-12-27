#!/bin/sh
set -e

DEFAULT_CONFIG_PATH="/app/servers.yml"
CONFIG_PATH="${CONDOR_CONFIG_PATH:-$DEFAULT_CONFIG_PATH}"

if [ "$CONFIG_PATH" != "$DEFAULT_CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$CONFIG_PATH")"
fi

if [ -f "$CONFIG_PATH" ]; then
  if [ "$CONFIG_PATH" != "$DEFAULT_CONFIG_PATH" ]; then
    ln -sf "$CONFIG_PATH" "$DEFAULT_CONFIG_PATH"
  fi
else
  if [ -n "${HBOT_API_HOST:-}" ]; then
    mkdir -p "$(dirname "$CONFIG_PATH")"
    {
      echo "servers:"
      echo "  main:"
      echo "    host: ${HBOT_API_HOST}"
      echo "    port: ${HBOT_API_PORT:-8001}"
      echo "    username: ${HBOT_API_USERNAME:-admin}"
      echo "    password: ${HBOT_API_PASSWORD:-admin}"
      if [ -n "${HBOT_API_SCHEME:-}" ]; then
        echo "    scheme: ${HBOT_API_SCHEME}"
      fi
      echo "default_server: main"
    } > "$CONFIG_PATH"

    if [ "$CONFIG_PATH" != "$DEFAULT_CONFIG_PATH" ]; then
      ln -sf "$CONFIG_PATH" "$DEFAULT_CONFIG_PATH"
    fi
  else
    echo "WARN: ${CONFIG_PATH} not found and HBOT_API_HOST not set; using existing /app/servers.yml if provided." >&2
  fi
fi

exec "$@"
