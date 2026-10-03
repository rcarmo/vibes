"""Read-only configuration provenance; configured does not mean executable."""


def backend_diagnostics(config):
    mode = config.default_agent.lower()
    result = {'backend': mode, 'selection': 'startup-only', 'execution_verified': False}
    if mode == 'copilot-ffi':
        result['transport'] = 'native-ffi'
        result['skills'] = [{'source': str(path), 'state': 'configured'} for path in getattr(config, 'copilot_skill_directories', [])[:16]]
        result['tools'] = [{'name': str(name), 'state': 'configured'} for name in getattr(config, 'copilot_available_tools', [])[:64]]
        result['mcp'] = [{'name': str(name), 'state': 'configured'} for name in list(getattr(config, 'copilot_mcp_servers', {}))[:32]]
    result['memory'] = {'sources': list(getattr(config, 'memory_paths', []))[:16], 'diagnostics': list(getattr(config, 'memory_diagnostics', []))[:16]}
    return result
