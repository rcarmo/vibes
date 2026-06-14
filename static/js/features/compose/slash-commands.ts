export interface SlashCommand {
    name: string;
    description: string;
}

/**
 * Base slash command set; merged/replaced with dynamic commands from the server on connect.
 */
export const DEFAULT_SLASH_COMMANDS: SlashCommand[] = [
    { name: '/model', description: 'Show or change the active model' },
    { name: '/model list', description: 'List available models' },
    { name: '/thinking', description: 'Show or change thinking level' },
    { name: '/restart', description: 'Reset agent session' },
    { name: '/abort', description: 'Cancel current request' },
    { name: '/steer', description: 'Send mid-turn steering guidance' },
    { name: '/user-name', description: 'Show or set your display name' },
    { name: '/user-avatar', description: 'Show or set your avatar URL' },
    { name: '/user-github', description: 'Set name/avatar from GitHub profile' },
    { name: '/commands', description: 'List all slash commands' },
    { name: '/clear', description: 'Clear the timeline display' },
    { name: '/shell', description: 'Run a shell command (30s timeout)' },
    { name: '/bash', description: 'Alias for /shell' },
];

export function normalizeSlashCommands(data: unknown): SlashCommand[] {
    const commands = Array.isArray(data)
        ? data
        : (Array.isArray((data as { commands?: unknown[] } | null)?.commands)
            ? (data as { commands: unknown[] }).commands
            : []);

    return commands
        .map((cmd) => {
            if (!cmd || typeof cmd !== 'object') return null;
            const item = cmd as { name?: unknown; description?: unknown };
            const name = typeof item.name === 'string' ? item.name.trim() : '';
            if (!name) return null;
            return {
                name,
                description: typeof item.description === 'string' ? item.description : '',
            };
        })
        .filter((cmd): cmd is SlashCommand => Boolean(cmd));
}
