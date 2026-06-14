import { html, useCallback, useEffect, useState } from '../vendor/preact-htm.js';

/**
 * Settings dialog — a tabbed modal for all app configuration.
 */

type SettingValue = string | number | boolean | null | undefined;
type SettingsMap = Record<string, SettingValue>;
type SettingsChangeHandler = (key: string, value: SettingValue) => void;
type TabId = 'general' | 'appearance' | 'models' | 'editor' | 'permissions' | 'actions' | 'developer' | 'workspace';

interface TabDefinition {
    id: TabId;
    label: string;
    icon: string;
}

interface SettingRowProps {
    label: string;
    description?: string;
    children?: unknown;
}

interface SettingsTabProps {
    settings: SettingsMap;
    onChange: SettingsChangeHandler;
}

interface SettingsDialogProps {
    open?: boolean;
    onClose: () => void;
}

interface WhitelistPayload {
    patterns?: string[];
}

interface AgentAction {
    id: string;
    label?: string;
}

interface AgentRecord {
    id: string;
    name?: string;
    actions?: AgentAction[];
}

interface AgentsPayload {
    agents?: AgentRecord[];
}

interface TestResult {
    ok: boolean;
    agent?: string;
    error?: string;
}

interface FirstRunWizardProps {
    onComplete?: () => void;
}

const TABS: TabDefinition[] = [
    { id: 'general', label: 'General', icon: '⚙️' },
    { id: 'appearance', label: 'Appearance', icon: '🎨' },
    { id: 'models', label: 'Models', icon: '🤖' },
    { id: 'editor', label: 'Editor', icon: '✏️' },
    { id: 'permissions', label: 'Permissions', icon: '🔒' },
    { id: 'actions', label: 'Quick Actions', icon: '⚡' },
    { id: 'developer', label: 'Developer', icon: '🛠️' },
    { id: 'workspace', label: 'Workspace', icon: '📁' },
];

function inputValue(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement | null)?.value || '';
}

function inputChecked(event: Event): boolean {
    return Boolean((event.target as HTMLInputElement | null)?.checked);
}

function inputInt(event: Event, fallback = 0): number {
    const value = parseInt(inputValue(event), 10);
    return Number.isFinite(value) ? value : fallback;
}

function SettingRow({ label, description, children }: SettingRowProps) {
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

function GeneralTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Agent</h3>
            <${SettingRow} label="Agent name" description="Display name for the AI assistant">
                <input type="text" value=${settings.agentName || 'Agent'}
                    onInput=${(event: Event) => onChange('agentName', inputValue(event))} />
            <//>
            <${SettingRow} label="User name" description="Your display name in the chat">
                <input type="text" value=${settings.userName || 'You'}
                    onInput=${(event: Event) => onChange('userName', inputValue(event))} />
            <//>
        </div>
        <div class="settings-section">
            <h3>Behavior</h3>
            <${SettingRow} label="Auto-scroll" description="Scroll to bottom on new messages">
                <input type="checkbox" checked=${settings.autoScroll !== false}
                    onChange=${(event: Event) => onChange('autoScroll', inputChecked(event))} />
            <//>
            <${SettingRow} label="Show timestamps" description="Display message timestamps">
                <input type="checkbox" checked=${settings.showTimestamps !== false}
                    onChange=${(event: Event) => onChange('showTimestamps', inputChecked(event))} />
            <//>
        </div>
    `;
}

function AppearanceTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Theme</h3>
            <${SettingRow} label="Color scheme" description="Light, dark, or system preference">
                <select value=${settings.colorScheme || 'system'}
                    onChange=${(event: Event) => onChange('colorScheme', inputValue(event))}>
                    <option value="system">System</option>
                    <option value="dark">Dark</option>
                    <option value="light">Light</option>
                </select>
            <//>
            <${SettingRow} label="Font size" description="Base font size in pixels">
                <input type="number" min="10" max="24" value=${settings.fontSize || 14}
                    onInput=${(event: Event) => onChange('fontSize', inputInt(event, 14))} />
            <//>
            <${SettingRow} label="Font family" description="Override the default system font">
                <input type="text" value=${settings.fontFamily || ''}
                    placeholder="system-ui, sans-serif"
                    onInput=${(event: Event) => onChange('fontFamily', inputValue(event))} />
            <//>
        </div>
    `;
}

function ModelsTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Backend Provider</h3>
            <${SettingRow} label="Default backend" description="Backend to use for new conversations">
                <input type="text" value=${settings.defaultAgent || ''}
                    placeholder="(auto-detect)"
                    onInput=${(event: Event) => onChange('defaultAgent', inputValue(event))} />
            <//>
            <${SettingRow} label="Default model" description="Model to request from the agent">
                <input type="text" value=${settings.defaultModel || ''}
                    placeholder="(agent default)"
                    onInput=${(event: Event) => onChange('defaultModel', inputValue(event))} />
            <//>
        </div>
    `;
}

function EditorTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Code Editor</h3>
            <${SettingRow} label="Tab size" description="Number of spaces per tab">
                <input type="number" min="1" max="8" value=${settings.tabSize || 4}
                    onInput=${(event: Event) => onChange('tabSize', inputInt(event, 4))} />
            <//>
            <${SettingRow} label="Word wrap" description="Wrap long lines in the editor">
                <input type="checkbox" checked=${settings.wordWrap !== false}
                    onChange=${(event: Event) => onChange('wordWrap', inputChecked(event))} />
            <//>
            <${SettingRow} label="Vim mode" description="Enable Vim keybindings in the editor">
                <input type="checkbox" checked=${settings.vimMode === true}
                    onChange=${(event: Event) => onChange('vimMode', inputChecked(event))} />
            <//>
        </div>
    `;
}

function DeveloperTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Debugging</h3>
            <${SettingRow} label="Debug mode" description="Show debug information in console">
                <input type="checkbox" checked=${settings.debugMode === true}
                    onChange=${(event: Event) => onChange('debugMode', inputChecked(event))} />
            <//>
            <${SettingRow} label="ACP wire logging" description="Log raw ACP JSON-RPC messages">
                <input type="checkbox" checked=${settings.acpWireLog === true}
                    onChange=${(event: Event) => onChange('acpWireLog', inputChecked(event))} />
            <//>
            <${SettingRow} label="Show SSE events" description="Log SSE events in browser console">
                <input type="checkbox" checked=${settings.showSSEEvents === true}
                    onChange=${(event: Event) => onChange('showSSEEvents', inputChecked(event))} />
            <//>
        </div>
    `;
}

function WorkspaceTab({ settings, onChange }: SettingsTabProps) {
    return html`
        <div class="settings-section">
            <h3>Workspace</h3>
            <${SettingRow} label="Workspace path" description="Root directory for file browsing">
                <input type="text" value=${settings.workspacePath || ''}
                    placeholder="/workspace"
                    onInput=${(event: Event) => onChange('workspacePath', inputValue(event))} />
            <//>
            <${SettingRow} label="Show hidden files" description="Display dotfiles in the explorer">
                <input type="checkbox" checked=${settings.showHidden === true}
                    onChange=${(event: Event) => onChange('showHidden', inputChecked(event))} />
            <//>
        </div>
    `;
}

function PermissionsTab() {
    const [patterns, setPatterns] = useState([] as string[]);
    const [newPattern, setNewPattern] = useState('');
    const [loading, setLoading] = useState(true);

    const loadWhitelist = useCallback(async () => {
        try {
            const resp = await fetch('/agent/whitelist');
            if (resp.ok) {
                const data = await resp.json() as WhitelistPayload;
                setPatterns(data.patterns || []);
            }
        } catch (error) { console.error('Failed to load whitelist', error); }
        setLoading(false);
    }, []);

    useEffect(() => { loadWhitelist(); }, [loadWhitelist]);

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
        } catch (error) { console.error('Failed to add pattern', error); }
    };

    const handleRemove = async (pattern: string) => {
        try {
            await fetch('/agent/whitelist', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pattern }),
            });
            loadWhitelist();
        } catch (error) { console.error('Failed to remove pattern', error); }
    };

    return html`
        <div class="settings-section">
            <h3>Tool Whitelist</h3>
            <p style="color: var(--text-secondary); font-size: var(--font-size-sm); margin-bottom: 12px;">
                Patterns that auto-approve agent tool requests without prompting.
            </p>
            <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                <input type="text" value=${newPattern}
                    onInput=${(event: Event) => setNewPattern(inputValue(event))}
                    onKeyDown=${(event: KeyboardEvent) => event.key === 'Enter' && handleAdd()}
                    placeholder="e.g. tools/read_file, bash*"
                    style="flex: 1; padding: 6px 10px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); color: var(--text-primary); font-size: var(--font-size-sm);" />
                <button onClick=${handleAdd} style="padding: 6px 12px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--accent-color); color: white; cursor: pointer; font-size: var(--font-size-sm);">Add</button>
            </div>
            ${loading && html`<div style="color: var(--text-secondary)">Loading...</div>`}
            ${!loading && patterns.length === 0 && html`<div style="color: var(--text-secondary); font-size: var(--font-size-sm)">No patterns configured. All tool requests will prompt.</div>`}
            ${(patterns as string[]).map((pattern: string) => html`
                <div class="settings-row">
                    <code style="font-size: var(--font-size-sm); color: var(--text-primary)">${pattern}</code>
                    <button onClick=${() => handleRemove(pattern)} style="border: none; background: none; color: var(--danger-color); cursor: pointer; font-size: 16px;" title="Remove">✕</button>
                </div>
            `)}
        </div>
    `;
}

function QuickActionsTab() {
    const [agents, setAgents] = useState([] as AgentRecord[]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/agents')
            .then((response) => response.json())
            .then((data: AgentRecord[] | AgentsPayload) => {
                const list = Array.isArray(data) ? data : data.agents || [];
                setAgents(list);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const triggerAction = async (agentId: string, actionId: string) => {
        try {
            await fetch(`/agent/${agentId}/action/${actionId}`, { method: 'POST' });
        } catch (error) { console.error('Action failed', error); }
    };

    return html`
        <div class="settings-section">
            <h3>Quick Actions</h3>
            <p style="color: var(--text-secondary); font-size: var(--font-size-sm); margin-bottom: 12px;">
                Custom endpoints configured in config/endpoints.json. Actions are triggered against the active agent.
            </p>
            ${loading && html`<div style="color: var(--text-secondary)">Loading...</div>`}
            ${!loading && agents.length === 0 && html`<div style="color: var(--text-secondary); font-size: var(--font-size-sm)">No agents configured.</div>`}
            ${(agents as AgentRecord[]).map((agent: AgentRecord) => html`
                <div style="margin-bottom: 12px">
                    <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px">${agent.name || agent.id}</div>
                    ${(agent.actions || []).length === 0
                        ? html`<div style="color: var(--text-secondary); font-size: var(--font-size-xs)">No actions available</div>`
                        : (agent.actions || []).map((action: AgentAction) => html`
                            <button onClick=${() => triggerAction(agent.id, action.id)}
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

const TAB_COMPONENTS: Record<TabId, (props: SettingsTabProps) => unknown> = {
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

function loadSettings(): SettingsMap {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) as SettingsMap : {};
    } catch {
        return {};
    }
}

function saveSettings(settings: SettingsMap): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
    const [activeTab, setActiveTab] = useState('general' as TabId);
    const [settings, setSettings] = useState(loadSettings);

    const handleChange = useCallback((key: string, value: SettingValue) => {
        setSettings((prev: SettingsMap) => {
            const next = { ...prev, [key]: value };
            saveSettings(next);
            // Apply immediate effects.
            if (key === 'colorScheme') {
                document.documentElement.setAttribute('data-theme', value === 'system' ? '' : String(value || ''));
            }
            if (key === 'fontSize') {
                document.documentElement.style.setProperty('--font-size-md', `${value}px`);
            }
            return next;
        });
    }, []);

    useEffect(() => {
        if (!open) return;
        const handleEsc = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [open, onClose]);

    if (!open) return null;

    const TabComponent = TAB_COMPONENTS[activeTab as TabId] || GeneralTab;

    return html`
        <div class="settings-overlay" onClick=${onClose}>
            <div class="settings-dialog" onClick=${(event: MouseEvent) => event.stopPropagation()}>
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
                        <h2>${TABS.find((tab) => tab.id === activeTab)?.label || 'Settings'}</h2>
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

export function getSettings(): SettingsMap {
    return loadSettings();
}

const OOBE_KEY = 'vibes-oobe-done';

export function FirstRunWizard({ onComplete }: FirstRunWizardProps) {
    const [agentName, setAgentName] = useState('');
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null as TestResult | null);

    if (localStorage.getItem(OOBE_KEY)) return null;

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const resp = await fetch('/health');
            if (resp.ok) {
                const data = await resp.json() as { agent?: string };
                setTestResult({ ok: true, agent: data.agent || 'connected' });
            } else {
                setTestResult({ ok: false, error: `Server returned ${resp.status}` });
            }
        } catch (error) {
            setTestResult({ ok: false, error: error instanceof Error ? error.message : String(error) });
        }
        setTesting(false);
    };

    const handleFinish = () => {
        if (agentName) {
            const settings = loadSettings();
            settings.agentName = agentName;
            saveSettings(settings);
        }
        localStorage.setItem(OOBE_KEY, '1');
        onComplete?.();
    };

    return html`
        <div class="settings-overlay">
            <div class="settings-dialog" style="max-width: 480px; height: auto; max-height: 400px;" onClick=${(event: MouseEvent) => event.stopPropagation()}>
                <div class="settings-content" style="width: 100%">
                    <div class="settings-content-header">
                        <h2>Welcome to Vibes 🌟</h2>
                    </div>
                    <div class="settings-content-body">
                        <div class="settings-section">
                            <p style="color: var(--text-secondary); margin-bottom: 16px;">Let's make sure everything is connected.</p>
                            <${SettingRow} label="Agent name" description="Give your AI assistant a name">
                                <input type="text" value=${agentName} placeholder="Agent"
                                    onInput=${(event: Event) => setAgentName(inputValue(event))} />
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
