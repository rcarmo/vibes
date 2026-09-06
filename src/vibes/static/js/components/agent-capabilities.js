import { html } from '../vendor/preact-htm.js';

export function AgentCapabilities({ agent }) {
    const caps = agent?.reported_capabilities;
    if (agent?.status !== 'running' || !caps || typeof caps !== 'object') return null;
    const fields = [
        ['Session resume', caps.loadSession],
        ['Image prompts', caps.promptCapabilities?.image],
        ['Audio prompts', caps.promptCapabilities?.audio],
        ['Embedded context', caps.promptCapabilities?.embeddedContext],
        ['MCP HTTP', caps.mcpCapabilities?.http],
        ['MCP SSE', caps.mcpCapabilities?.sse],
    ].filter(([, value]) => typeof value === 'boolean');
    if (!fields.length) return null;
    return html`<details class="compose-agent-capabilities"><summary>Agent-reported capabilities</summary>
        <p>Connection declarations only; not verified execution or session availability.</p>
        <ul>${fields.map(([label, value]) => html`<li>${label}: ${value ? 'reported supported' : 'reported unsupported'}</li>`)}</ul>
    </details>`;
}
