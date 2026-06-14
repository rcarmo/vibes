const RATE_LIMIT_RE = /429|rate.?limit|too many requests|requests per minute|tokens per minute|rpm|tpm/i;

export function describeRateLimit(text: unknown): string | null {
    const value = typeof text === 'string' ? text : '';
    if (!value || !RATE_LIMIT_RE.test(value)) return null;
    if (/tokens?\s*per\s*minute|tpm/i.test(value)) return '⚠ Rate limited (TPM — tokens per minute)';
    if (/requests?\s*per\s*minute|rpm/i.test(value)) return '⚠ Rate limited (RPM — requests per minute)';
    return '⚠ Rate limited';
}
