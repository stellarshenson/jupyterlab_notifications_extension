import { formatTimeAgo, reconnectDelay } from '../utils';

describe('formatTimeAgo', () => {
  it('returns "just now" for timestamps less than 60 seconds old', () => {
    expect(formatTimeAgo(Date.now())).toBe('just now');
    expect(formatTimeAgo(Date.now() - 5000)).toBe('just now');
    expect(formatTimeAgo(Date.now() - 30000)).toBe('just now');
    expect(formatTimeAgo(Date.now() - 59000)).toBe('just now');
  });

  it('returns minutes for 1-59 minutes', () => {
    expect(formatTimeAgo(Date.now() - 60000)).toBe('1m ago');
    expect(formatTimeAgo(Date.now() - 5 * 60000)).toBe('5m ago');
    expect(formatTimeAgo(Date.now() - 59 * 60000)).toBe('59m ago');
  });

  it('returns hours for 1-23 hours', () => {
    expect(formatTimeAgo(Date.now() - 3600000)).toBe('1h ago');
    expect(formatTimeAgo(Date.now() - 12 * 3600000)).toBe('12h ago');
    expect(formatTimeAgo(Date.now() - 23 * 3600000)).toBe('23h ago');
  });

  it('returns days for 1+ days', () => {
    expect(formatTimeAgo(Date.now() - 86400000)).toBe('1d ago');
    expect(formatTimeAgo(Date.now() - 7 * 86400000)).toBe('7d ago');
    expect(formatTimeAgo(Date.now() - 365 * 86400000)).toBe('365d ago');
  });

  it('reads a future timestamp as "just now"', () => {
    expect(formatTimeAgo(Date.now() + 60000)).toBe('just now');
  });

  it('handles zero timestamp', () => {
    const result = formatTimeAgo(0);
    expect(result).toMatch(/^\d+d ago$/);
  });
});

describe('reconnectDelay', () => {
  const BASE = 5000;
  const MAX = 60000;

  it('waits the base delay on the first reconnect', () => {
    expect(reconnectDelay(1, BASE, MAX)).toBe(5000);
  });

  it('doubles each attempt until the cap', () => {
    expect(reconnectDelay(2, BASE, MAX)).toBe(10000);
    expect(reconnectDelay(3, BASE, MAX)).toBe(20000);
    expect(reconnectDelay(4, BASE, MAX)).toBe(40000);
  });

  it('never exceeds the cap, however many attempts', () => {
    expect(reconnectDelay(5, BASE, MAX)).toBe(60000);
    expect(reconnectDelay(10, BASE, MAX)).toBe(60000);
    expect(reconnectDelay(99, BASE, MAX)).toBe(60000);
  });
});
