/**
 * Format a Unix timestamp (ms) as a relative time string.
 *
 * Returns a compact label such as "just now", "5m ago", "2h ago",
 * or "3d ago". Anything under 60 seconds is shown as "just now".
 */
export function formatTimeAgo(createdAt: number): string {
  // A negative delta (a future timestamp) already floors below the 60s tier,
  // so no clamp is needed to read it as "just now".
  const delta = Date.now() - createdAt;
  const seconds = Math.floor(delta / 1000);

  if (seconds < 60) {
    return 'just now';
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Reconnect backoff for the notification stream, in milliseconds.
 *
 * `attempt` is 1 for the first reconnect. The delay doubles from `baseMs` and
 * is capped at `maxMs`, so a server that stays down is retried at a fixed
 * ceiling rather than ever faster.
 */
export function reconnectDelay(
  attempt: number,
  baseMs: number,
  maxMs: number
): number {
  return Math.min(baseMs * 2 ** (attempt - 1), maxMs);
}
