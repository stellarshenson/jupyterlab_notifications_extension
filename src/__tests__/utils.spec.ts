import { formatTimeAgo, appendTimeAgo } from '../utils';

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

  it('handles future timestamps by clamping to "just now"', () => {
    expect(formatTimeAgo(Date.now() + 60000)).toBe('just now');
  });

  it('handles zero timestamp', () => {
    const result = formatTimeAgo(0);
    expect(result).toMatch(/^\d+d ago$/);
  });
});

describe('appendTimeAgo', () => {
  it('appends parenthesised time suffix to message', () => {
    const result = appendTimeAgo('Task completed', Date.now());
    expect(result).toBe('Task completed (just now)');
  });

  it('preserves original message content', () => {
    const result = appendTimeAgo('Server restarted', Date.now() - 120000);
    expect(result).toBe('Server restarted (2m ago)');
  });
});
