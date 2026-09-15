// Piclaw classic meter markup, backed by Vibes server metrics (not Pi RPC).
import { html, useEffect, useState } from '../vendor/preact-htm.js';
import { getSystemMetrics } from '../api.js';
import { disclosureTriangle } from './disclosure-triangle.js';

export const METERS_KEY = 'vibes_system_meters_collapsed';
const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
export const formatPercent = value => finite(value) && value <= 100 ? `${Math.round(value)}%` : '—';
export function formatBytes(value) {
    if (!finite(value)) return '—';
    const units = ['B', 'K', 'M', 'G', 'T'];
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)}${units[unit]}`;
}
export function sparkline(series, percentage = false) {
    const points = Array.isArray(series) ? series.slice(-30) : [];
    const valid = points.filter(finite);
    if (!valid.length) return '';
    const min = percentage ? 0 : Math.min(...valid);
    const max = percentage ? 100 : Math.max(...valid);
    let started = false;
    return points.map((value, index) => {
        if (!finite(value) || (percentage && value > 100)) { started = false; return ''; }
        const x = points.length > 1 ? index / (points.length - 1) * 56 : 0;
        const y = max > min ? 16 - (value - min) / (max - min) * 16 : 8;
        const segment = `${started ? 'L' : 'M'} ${x.toFixed(2)} ${y.toFixed(2)}`;
        started = true;
        return points.length === 1 ? `${segment} L 56 ${y.toFixed(2)}` : segment;
    }).filter(Boolean).join(' ');
}
function readCollapsed() {
    try { return localStorage.getItem(METERS_KEY) === 'true'; } catch { return false; }
}

export function SystemMeters({ toggleRequest = 0 }) {
    const [collapsed, setCollapsed] = useState(readCollapsed);
    const [metrics, setMetrics] = useState(null);
    const [error, setError] = useState(false);
    const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 600px)').matches);
    useEffect(() => {
        const query = window.matchMedia('(max-width: 600px)');
        const change = () => setNarrow(query.matches);
        query.addEventListener('change', change);
        return () => query.removeEventListener('change', change);
    }, []);
    useEffect(() => {
        if (toggleRequest) setCollapsed(value => !value);
    }, [toggleRequest]);
    useEffect(() => {
        try { localStorage.setItem(METERS_KEY, String(collapsed)); } catch { /* optional preference */ }
    }, [collapsed]);
    useEffect(() => {
        let disposed = false, timer, controller;
        const refresh = async () => {
            if (disposed || document.visibilityState === 'hidden') return;
            controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 5000);
            try {
                const next = await getSystemMetrics(controller.signal);
                if (!disposed) {
                    const age = Date.now() - next?.sampled_at;
                    if (!finite(next?.sampled_at) || age > 10000 || age < -60000) throw Error('Stale metrics');
                    setMetrics(next); setError(false);
                }
            } catch {
                if (!disposed) { setError(true); setMetrics(null); }
            } finally {
                clearTimeout(timeout); controller = null;
                if (!disposed) timer = setTimeout(refresh, 2000);
            }
        };
        const visibility = () => {
            clearTimeout(timer);
            if (document.visibilityState !== 'hidden' && !controller) void refresh();
        };
        void refresh();
        document.addEventListener('visibilitychange', visibility);
        return () => { disposed = true; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', visibility); };
    }, []);
    const rows = [
        ['cpu', 'CPU', metrics?.cpu_percent, metrics?.cpu_series, true, 'Host CPU utilisation'],
        ['ram', 'RAM', metrics?.ram_percent, metrics?.ram_series, true, `Host RAM: ${formatBytes(metrics?.ram_used_bytes)} / ${formatBytes(metrics?.ram_total_bytes)}`],
        ...(finite(metrics?.process_rss_bytes) ? [['rss', 'RSS', metrics.process_rss_bytes, metrics.process_rss_series_bytes, false, 'Vibes server process resident memory (not agent children)']] : []),
        ...(finite(metrics?.vram_percent) && metrics?.vram_total_bytes > 0 ? [['vram', 'VRAM', metrics.vram_percent, metrics.vram_series, true, `GPU memory (${metrics.gpu_provider}): ${formatBytes(metrics.vram_used_bytes)} / ${formatBytes(metrics.vram_total_bytes)}`]] : []),
        ...(finite(metrics?.buffer_cache_bytes) ? [['buf', 'BUF', metrics.buffer_cache_bytes, metrics.buffer_cache_series_bytes, false, 'Host buffer/cache memory']] : []),
        ...(metrics?.swap_total_bytes > 0 ? [['swap', 'SWP', metrics.swap_percent, metrics.swap_series, true, `Host swap: ${formatBytes(metrics.swap_used_bytes)} / ${formatBytes(metrics.swap_total_bytes)}`]] : []),
    ];
    const summary = ['cpu', 'ram', 'buf', 'vram', 'swap'].map(kind => rows.find(row => row[0] === kind)).filter(Boolean)
        .map(([, label, value, , percentage]) => `${label} ${percentage ? formatPercent(value) : formatBytes(value)}`).join(' • ');
    const unavailable = error || metrics?.available === false;
    const description = `Vibes server${metrics?.hostname ? ` ${metrics.hostname}` : ''} — OS view, not browser or inference-server usage. GPU metrics only when available from Linux DRM.`;
    return html`
        <div class=${`system-meters-hud system-meters-hud-overlay${collapsed ? ' is-collapsed' : ''}`} data-testid="system-meters" data-state=${unavailable ? 'unavailable' : metrics ? 'ready' : 'loading'}>
            <button type="button" class="system-meters-card" aria-label=${collapsed ? 'Show server resource meters' : 'Collapse server resource meters'} aria-expanded=${!collapsed} title=${description} onClick=${() => setCollapsed(value => !value)}>
                ${collapsed ? html`<span class="system-meters-collapse-tab" aria-hidden="true">${disclosureTriangle('left')}</span>` : html`
                    ${unavailable || !metrics ? html`<span class="system-meters-source">${unavailable ? 'Server metrics unavailable' : 'Loading server metrics…'}</span>` : null}
                    ${narrow ? html`<span class="system-meters-compact-summary">${summary}</span>` : rows.map(([kind, label, value, series, percentage, title]) => html`
                        <span class=${`system-meters-row ${kind}`} title=${title}>
                            <span class="system-meters-label">${label}</span>
                            <svg class="system-meters-spark" viewBox="0 0 56 16" preserveAspectRatio="none" aria-hidden="true"><path d=${sparkline(series, percentage)} /></svg>
                            <span class="system-meters-value">${percentage ? formatPercent(value) : formatBytes(value)}</span>
                        </span>`)}
                `}
            </button>
        </div>`;
}
