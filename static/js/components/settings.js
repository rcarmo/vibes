import { html, useCallback, useEffect, useState } from '../vendor/preact-htm.js';

/**
 * Settings dialog — a tabbed modal for all app configuration.
 */

const TABS = [
    { id: 'general', label: 'General', icon: '⚙️' },
    { id: 'appearance', label: 'Appearance', icon: '🎨' },
    { id: 'models', label: 'Models', icon: '🤖' },
    { id: 'editor', label: 'Editor', icon: '✏️' },
    { id: 'permissions', label: 'Permissions', icon: '🔒' },
    { id: 'actions', label: 'Quick Actions', icon: '⚡' },
    { id: 'developer', label: 'Developer', icon: '🛠️' },
    { id: 'workspace', label: 'Workspace', icon: '📁' },
];

function SettingRow({ label, description, children }) {
    return html`
        <div class="settings-row">
            <div class="settings-row-info">
                <div class="settings-row-label">${label}</div>
                ${description && html`<div class="settings-row-desc">${description}</div>`}
            </div>
            <div class="settings-row-control">${children}</div>
        </div>
    `;
}

function GeneralTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Agent</h3>
            <${SettingRow} label="Agent name" description="Display name for the AI assistant">
                <input type="text" value=${settings.agentName || 'Agent'}
                    onInput=${(e) => onChange('agentName', e.target.value)} />
            <//>
            <${SettingRow} label="User name" description="Your display name in the chat">
                <input type="text" value=${settings.userName || 'You'}
                    onInput=${(e) => onChange('userName', e.target.value)} />
            <//>
        </div>
        <div class="settings-section">
            <h3>Behavior</h3>
            <${SettingRow} label="Auto-scroll" description="Scroll to bottom on new messages">
                <input type="checkbox" checked=${settings.autoScroll !== false}
                    onChange=${(e) => onChange('autoScroll', e.target.checked)} />
            <//>
            <${SettingRow} label="Show timestamps" description="Display message timestamps">
                <input type="checkbox" checked=${settings.showTimestamps !== false}
                    onChange=${(e) => onChange('showTimestamps', e.target.checked)} />
            <//>
        </div>
    `;
}

function AppearanceTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Theme</h3>
            <${SettingRow} label="Color scheme" description="Light, dark, or system preference">
                <select value=${settings.colorScheme || 'system'}
                    onChange=${(e) => onChange('colorScheme', e.target.value)}>
                    <option value="system">System</option>
                    <option value="dark">Dark</option>
                    <option value="light">Light</option>
                </select>
            <//>
            <${SettingRow} label="Font size" description="Base font size in pixels">
                <input type="number" min="10" max="24" value=${settings.fontSize || 14}
                    onInput=${(e) => onChange('fontSize', parseInt(e.target.value))} />
            <//>
            <${SettingRow} label="Font family" description="Override the default system font">
                <input type="text" value=${settings.fontFamily || ''}
                    placeholder="system-ui, sans-serif"
                    onInput=${(e) => onChange('fontFamily', e.target.value)} />
            <//>
        </div>
    `;
}

function ModelsTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Backend Provider</h3>
            <${SettingRow} label="Default backend" description="Backend to use for new conversations">
                <input type="text" value=${settings.defaultAgent || ''}
                    placeholder="(auto-detect)"
                    onInput=${(e) => onChange('defaultAgent', e.target.value)} />
            <//>
            <${SettingRow} label="Default model" description="Model to request from the agent">
                <input type="text" value=${settings.defaultModel || ''}
                    placeholder="(agent default)"
                    onInput=${(e) => onChange('defaultModel', e.target.value)} />
            <//>
        </div>
    `;
}

function EditorTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Code Editor</h3>
            <${SettingRow} label="Tab size" description="Number of spaces per tab">
                <input type="number" min="1" max="8" value=${settings.tabSize || 4}
                    onInput=${(e) => onChange('tabSize', parseInt(e.target.value))} />
            <//>
            <${SettingRow} label="Word wrap" description="Wrap long lines in the editor">
                <input type="checkbox" checked=${settings.wordWrap !== false}
                    onChange=${(e) => onChange('wordWrap', e.target.checked)} />
            <//>
            <${SettingRow} label="Vim mode" description="Enable Vim keybindings in the editor">
                <input type="checkbox" checked=${settings.vimMode === true}
                    onChange=${(e) => onChange('vimMode', e.target.checked)} />
            <//>
        </div>
    `;
}

function DeveloperTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Debugging</h3>
            <${SettingRow} label="Debug mode" description="Show debug information in console">
                <input type="checkbox" checked=${settings.debugMode === true}
                    onChange=${(e) => onChange('debugMode', e.target.checked)} />
            <//>
            <${SettingRow} label="ACP wire logging" description="Log raw ACP JSON-RPC messages">
                <input type="checkbox" checked=${settings.acpWireLog === true}
                    onChange=${(e) => onChange('acpWireLog', e.target.checked)} />
            <//>
            <${SettingRow} label="Show SSE events" description="Log SSE events in browser console">
                <input type="checkbox" checked=${settings.showSSEEvents === true}
                    onChange=${(e) => onChange('showSSEEvents', e.target.checked)} />
            <//>
        </div>
    `;
}

function WorkspaceTab({ settings, onChange }) {
    return html`
        <div class="settings-section">
            <h3>Workspace</h3>
            <${SettingRow} label="Workspace path" description="Root directory for file browsing">
                <input type="text" value=${settings.workspacePath || ''}
                    placeholder="/workspace"
                    onInput=${(e) => onChange('workspacePath', e.target.value)} />
            <//>
            <${SettingRow} label="Show hidden files" description="Display dotfiles in the explorer">
                <input type="checkbox" checked=${settings.showHidden === true}
                    onChange=${(e) => onChange('showHidden', e.target.checked)} />
            <//>
        </div>
    `;
}

function PermissionsTab() {
    const [patterns, setPatterns] = useState([]);
    const [newPattern, setNewPattern] = useState('');
    const [loading, setLoading] = useState(true);

    const loadWhitelist = useCallback(async () => {
        try {
            const resp = await fetch('/agent/whitelist');
            if (resp.ok) {
                const data = await resp.json();
                setPatterns(data.patterns || []);
            }
        } catch (e) { console.error('Failed to load whitelist', e); }
        setLoading(false);
    }, []);

    useEffect(() => { loadWhitelist(); }, []);

    const handleAdd = async () => {
        const pattern = newPattern.trim();
        if (!pattern) return;
        try {
            const resp = await fetch('/agent/whitelist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pattern }),
            });
            if (resp.ok) {
                setNewPattern('');
                loadWhitelist();
            }
        } catch (e) { console.error('Failed to add pattern', e); }
    };

    const handleRemove = async (pattern) => {
        try {
            await fetch('/agent/whitelist', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pattern }),
            });
            loadWhitelist();
        } catch (e) { console.error('Failed to remove pattern', e); }
    };

    return html`
        <div class="settings-section">
            <h3>Tool Whitelist</h3>
            <p style="color: var(--text-secondary); font-size: var(--font-size-sm); margin-bottom: 12px;">
                Patterns that auto-approve agent tool requests without prompting.
            </p>
            <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                <input type="text" value=${newPattern}
                    onInput=${(e) => setNewPattern(e.target.value)}
                    onKeyDown=${(e) => e.key === 'Enter' && handleAdd()}
                    placeholder="e.g. tools/read_file, bash*"
                    style="flex: 1; padding: 6px 10px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); color: var(--text-primary); font-size: var(--font-size-sm);" />
                <button onClick=${handleAdd} style="padding: 6px 12px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--accent-color); color: white; cursor: pointer; font-size: var(--font-size-sm);">Add</button>
            </div>
            ${loading && html`<div style="color: var(--text-secondary)">Loading...</div>`}
            ${!loading && patterns.length === 0 && html`<div style="color: var(--text-secondary); font-size: var(--font-size-sm)">No patterns configured. All tool requests will prompt.</div>`}
            ${patterns.map((p) => html`
                <div class="settings-row">
                    <code style="font-size: var(--font-size-sm); color: var(--text-primary)">${p}</code>
                    <button onClick=${() => handleRemove(p)} style="border: none; background: none; color: var(--danger-color); cursor: pointer; font-size: 16px;" title="Remove">✕</button>
                </div>
            `)}
        </div>
    `;
}

function QuickActionsTab() {
    const [agents, setAgents] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/agents')
            .then(r => r.json())
            .then(data => {
                const list = Array.isArray(data) ? data : data.agents || [];
                setAgents(list);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const triggerAction = async (agentId, actionId) => {
        try {
            await fetch(`/agent/${agentId}/action/${actionId}`, { method: 'POST' });
        } catch (e) { console.error('Action failed', e); }
    };

    return html`
        <div class="settings-section">
            <h3>Quick Actions</h3>
            <p style="color: var(--text-secondary); font-size: var(--font-size-sm); margin-bottom: 12px;">
                Custom endpoints configured in config/endpoints.json. Actions are triggered against the active agent.
            </p>
            ${loading && html`<div style="color: var(--text-secondary)">Loading...</div>`}
            ${!loading && agents.length === 0 && html`<div style="color: var(--text-secondary); font-size: var(--font-size-sm)">No agents configured.</div>`}
            ${agents.map(a => html`
                <div style="margin-bottom: 12px">
                    <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px">${a.name || a.id}</div>
                    ${(a.actions || []).length === 0
                        ? html`<div style="color: var(--text-secondary); font-size: var(--font-size-xs)">No actions available</div>`
                        : (a.actions || []).map(action => html`
                            <button onClick=${() => triggerAction(a.id, action.id)}
                                style="margin: 2px 4px 2px 0; padding: 4px 10px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); color: var(--text-primary); cursor: pointer; font-size: var(--font-size-sm);">
                                ${action.label || action.id}
                            </button>
                        `)
                    }
                </div>
            `)}
        </div>
    `;
}

const TAB_COMPONENTS = {
    general: GeneralTab,
    appearance: AppearanceTab,
    models: ModelsTab,
    editor: EditorTab,
    permissions: PermissionsTab,
    actions: QuickActionsTab,
    developer: DeveloperTab,
    workspace: WorkspaceTab,
};

const STORAGE_KEY = 'vibes-settings';

function loadSettings() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function saveSettings(settings) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function SettingsDialog({ open, onClose }) {
    const [activeTab, setActiveTab] = useState('general');
    const [settings, setSettings] = useState(loadSettings);

    const handleChange = useCallback((key, value) => {
        setSettings((prev) => {
            const next = { ...prev, [key]: value };
            saveSettings(next);
            // Apply immediate effects
            if (key === 'colorScheme') {
                document.documentElement.setAttribute('data-theme', value === 'system' ? '' : value);
            }
            if (key === 'fontSize') {
                document.documentElement.style.setProperty('--font-size-md', value + 'px');
            }
            return next;
        });
    }, []);

    useEffect(() => {
        if (!open) return;
        const handleEsc = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [open, onClose]);

    if (!open) return null;

    const TabComponent = TAB_COMPONENTS[activeTab] || GeneralTab;

    return html`
        <div class="settings-overlay" onClick=${onClose}>
            <div class="settings-dialog" onClick=${(e) => e.stopPropagation()}>
                <div class="settings-sidebar">
                    <div class="settings-sidebar-title">Settings</div>
                    ${TABS.map((tab) => html`
                        <button
                            class="settings-tab-btn ${activeTab === tab.id ? 'active' : ''}"
                            onClick=${() => setActiveTab(tab.id)}
                        >
                            <span class="settings-tab-icon">${tab.icon}</span>
                            <span>${tab.label}</span>
                        </button>
                    `)}
                </div>
                <div class="settings-content">
                    <div class="settings-content-header">
                        <h2>${TABS.find((t) => t.id === activeTab)?.label || 'Settings'}</h2>
                        <button class="settings-close-btn" onClick=${onClose}>✕</button>
                    </div>
                    <div class="settings-content-body">
                        <${TabComponent} settings=${settings} onChange=${handleChange} />
                    </div>
                </div>
            </div>
        </div>
    `;
}

export function getSettings() {
    return loadSettings();
}

const OOBE_KEY = 'vibes-oobe-done';

export function FirstRunWizard({ onComplete }) {
    const [agentName, setAgentName] = useState('');
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);

    if (localStorage.getItem(OOBE_KEY)) return null;

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const resp = await fetch('/health');
            if (resp.ok) {
                const data = await resp.json();
                setTestResult({ ok: true, agent: data.agent || 'connected' });
            } else {
                setTestResult({ ok: false, error: 'Server returned ' + resp.status });
            }
        } catch (e) {
            setTestResult({ ok: false, error: e.message });
        }
        setTesting(false);
    };

    const handleFinish = () => {
        if (agentName) {
            const s = loadSettings();
            s.agentName = agentName;
            saveSettings(s);
        }
        localStorage.setItem(OOBE_KEY, '1');
        onComplete?.();
    };

    return html`
        <div class="settings-overlay">
            <div class="settings-dialog" style="max-width: 480px; height: auto; max-height: 400px;" onClick=${(e) => e.stopPropagation()}>
                <div class="settings-content" style="width: 100%">
                    <div class="settings-content-header">
                        <h2>Welcome to Vibes 🌟</h2>
                    </div>
                    <div class="settings-content-body">
                        <div class="settings-section">
                            <p style="color: var(--text-secondary); margin-bottom: 16px;">Let's make sure everything is connected.</p>
                            <${SettingRow} label="Agent name" description="Give your AI assistant a name">
                                <input type="text" value=${agentName} placeholder="Agent"
                                    onInput=${(e) => setAgentName(e.target.value)} />
                            <//>
                            <div style="margin-top: 16px; display: flex; gap: 8px; align-items: center;">
                                <button onClick=${handleTest} disabled=${testing}
                                    style="padding: 8px 16px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--accent-color); color: white; cursor: pointer;">
                                    ${testing ? 'Testing...' : 'Test Connection'}
                                </button>
                                ${testResult?.ok && html`<span style="color: #4ec9b0;">✓ Connected (${testResult.agent})</span>`}
                                ${testResult && !testResult.ok && html`<span style="color: var(--danger-color);">✗ ${testResult.error}</span>`}
                            </div>
                        </div>
                        <div style="margin-top: 20px; display: flex; justify-content: flex-end; gap: 8px;">
                            <button onClick=${handleFinish}
                                style="padding: 8px 20px; border: none; border-radius: var(--radius-md); background: var(--accent-color); color: white; cursor: pointer; font-weight: 500;">
                                ${testResult?.ok ? 'Get Started' : 'Skip'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}
