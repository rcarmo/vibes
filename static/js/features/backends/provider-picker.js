import { html } from '../../vendor/preact-htm.js';
import { describeProvider } from './provider-utils.js';

export function ProviderPicker({
    providers = [],
    selectedProvider = null,
    activeBackendId = null,
    disabled = false,
    onChange,
}) {
    const providerOptions = (providers || []).filter(Boolean);
    if (providerOptions.length === 0) return null;

    const handleChange = (event) => {
        const next = event.target.value;
        if (!next || next === activeBackendId) return;
        const provider = providerOptions.find((item) => item.id === next);
        if (provider && !provider.available) return;
        onChange?.(next);
    };

    return html`
        <select
            class="compose-backend-picker"
            value=${selectedProvider?.id || ''}
            onChange=${handleChange}
            title=${describeProvider(selectedProvider)}
            aria-label="Backend for new turns"
            disabled=${disabled}
        >
            ${providerOptions.map((provider) => html`
                <option key=${provider.id} value=${provider.id} disabled=${!provider.available} title=${describeProvider(provider)}>
                    ${provider.label || provider.id}${provider.available ? '' : ` — ${provider.status || 'unavailable'}`}
                </option>
            `)}
        </select>
    `;
}
