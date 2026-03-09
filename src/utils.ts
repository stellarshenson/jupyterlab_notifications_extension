/**
 * Format a Unix timestamp (ms) as a relative time string.
 *
 * Returns a compact label such as "just now", "5m ago", "2h ago",
 * or "3d ago". Anything under 60 seconds is shown as "just now".
 */
export function formatTimeAgo(createdAt: number): string {
  const delta = Math.max(0, Date.now() - createdAt);
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
 * Append a parenthesised relative-time suffix to a message string.
 *
 * Example: appendTimeAgo("Task done", ts) => "Task done (2m ago)"
 */
export function appendTimeAgo(message: string, createdAt: number): string {
  return `${message} (${formatTimeAgo(createdAt)})`;
}
