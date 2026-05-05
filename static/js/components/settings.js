import { html, useCallback, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';

/**
 * Settings dialog — a tabbed modal for all app configuration.
 */

const TABS = [
    { id: 'general', label: 'General', icon: '⚙️' },
    { id: 'appearance', label: 'Appearance', icon: '🎨' },
    { id: 'models', label: 'Models', icon: '🤖' },
    { id: 'editor', label: 'Editor', icon: '✏️' },
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
            <h3>Agent Provider</h3>
            <${SettingRow} label="Default agent" description="Agent to use for new conversations">
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

const TAB_COMPONENTS = {
    general: GeneralTab,
    appearance: AppearanceTab,
    models: ModelsTab,
    editor: EditorTab,
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
