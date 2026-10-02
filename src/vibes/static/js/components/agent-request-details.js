// Normalise ACP/Pi tool calls and native Copilot permission unions for display.
// Display only: never infer approval or modify the response option IDs.
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const text = value => typeof value === 'string' && value.trim() ? value : null;
const pretty = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
const firstText = (...values) => values.map(text).find(Boolean) || null;

export function agentRequestDetails(request) {
    const call = object(request?.tool_call);
    let input = object(call.rawInput);
    if (typeof call.rawInput === 'string') {
        try { input = object(JSON.parse(call.rawInput)); } catch { /* legacy plain text */ }
    }
    const native = typeof input.kind === 'string' && ['custom-tool', 'mcp', 'read', 'write', 'shell', 'url'].includes(input.kind);
    const args = object(input.args);
    let title = firstText(call.title) || 'Agent request';
    let explanation = firstText(call.description, input.description, input.explanation);
    let fields = [];
    let command = firstText(input.fullCommandText, input.full_command_text, input.command, args.command, Array.isArray(input.commands) ? input.commands[0] : null);
    const diff = firstText(input.diff, args.diff);
    const paths = [input.fileName, input.path, input.filePath, args.path, args.filePath,
        ...(Array.isArray(call.locations) ? call.locations.map(loc => loc?.path) : []),
        ...(Array.isArray(input.paths) ? input.paths : []),
        ...(Array.isArray(input.possiblePaths) ? input.possiblePaths : [])].filter(text);
    const warnings = [text(input.warning)];
    if (input.requestSandboxBypass === true) warnings.push(firstText(input.requestSandboxBypassReason) || 'This command requests permission to bypass sandbox restrictions.');
    if (input.hasWriteFileRedirection === true) warnings.push('This command redirects output to a file.');
    if (native) {
        const name = firstText(input.toolName, input.tool_name);
        const kindTitles = { read: 'Read file', write: 'Write file', shell: 'Run command', url: 'Access URL' };
        title = kindTitles[input.kind] || (name ? `Run ${name}` : 'Tool permission');
        explanation = firstText(input.intention, input.toolDescription, input.description);
        if (name === 'vibes_plan') {
            title = args.action === 'read' ? 'Read conversation plan' : 'Update conversation plan';
            explanation = args.action === 'read' ? 'Read the shared plan for this conversation.' : 'Change the shared plan for this conversation.';
        } else if (name === 'vibes_attach_file') {
            title = 'Attach file';
            explanation = 'Publish this workspace file in the current conversation.';
        }
        const omit = new Set(['path', 'filePath', 'command', 'diff']);
        if (name === 'vibes_plan') omit.add('action');
        fields = Object.entries(args).filter(([key]) => !omit.has(key)).map(([key, value]) => ({ label: key, value: pretty(value) }));
        if (text(input.serverName)) fields.unshift({ label: 'MCP server', value: input.serverName });
        if (text(input.url)) fields.unshift({ label: 'URL', value: input.url });
        if (text(input.resolvedWorkingDirectory)) fields.unshift({ label: 'Working directory', value: input.resolvedWorkingDirectory });
        if (!command && Array.isArray(input.commands)) command = input.commands.filter(text).join('\n') || null;
    }
    return { title, explanation, command, diff, paths: [...new Set(paths)], fields, warnings: warnings.filter(Boolean),
        technical: native ? JSON.stringify(input, null, 2) : null };
}
