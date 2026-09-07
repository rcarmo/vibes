// ACP values are optional: billed turn tokens are not context occupancy.
export function usagePresentation(usage) {
    const labels = { inputTokens: 'Input', outputTokens: 'Output', totalTokens: 'Total', thoughtTokens: 'Reasoning', cachedReadTokens: 'Cache read', cachedWriteTokens: 'Cache write' };
    const tokens = Object.entries(labels).flatMap(([key, label]) => {
        const n = usage?.turnUsage?.[key];
        return Number.isSafeInteger(n) && n >= 0 ? [`${label}: ${n.toLocaleString()}`] : [];
    });
    const cost = usage?.cost;
    const validCost = typeof cost?.amount === 'number' && Number.isFinite(cost.amount) && cost.amount >= 0 && /^[A-Z]{3}$/.test(cost.currency);
    const amount = validCost ? (cost.amount > 0 && cost.amount < 0.01 ? cost.amount.toPrecision(3) : cost.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })) : null;
    const costLabel = validCost ? `${cost.currency} ${amount}` : null;
    return {
        label: costLabel || (tokens.length ? 'Turn usage' : null),
        title: [costLabel && `Agent-reported cost: ${costLabel}`, tokens.length && `Last turn tokens — ${tokens.join(' · ')}`].filter(Boolean).join('\n'),
    };
}
