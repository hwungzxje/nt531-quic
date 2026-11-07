#!/usr/bin/env bash
# Only return workers which actually belong to this named network namespace.
nginx_workers() {
  local pid cmd
  for pid in $(ip netns pids server); do
    [[ -r /proc/$pid/cmdline ]] || continue
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline")
    [[ "$cmd" == "nginx: worker process"* ]] && printf '%s\n' "$pid"
  done
  return 0
}
require_root() { [[ $(id -u) == 0 ]] || { echo 'Run with sudo on the dedicated testbed.' >&2; return 1; }; }
