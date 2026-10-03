"""Read-only configuration provenance; configured does not mean executable."""


def _labels(values, limit):
    return [value for value in values[:limit]
            if isinstance(value, str) and value.strip() and len(value) <= 512
            and not any(ord(char) < 32 or ord(char) == 127 for char in value)]


def backend_diagnostics(config):
    mode = config.default_agent.lower()
    result = {'backend': mode, 'selection': 'startup-only', 'execution_verified': False}
    if mode == 'copilot-ffi':
        result['transport'] = 'native-ffi'
        result['skills'] = [{'source': str(path), 'state': 'configured'} for path in _labels(getattr(config, 'copilot_skill_directories', []), 16)]
        result['tools'] = [{'name': str(name), 'state': 'configured'} for name in _labels(getattr(config, 'copilot_available_tools', []), 64)]
        result['mcp'] = [{'name': str(name), 'state': 'configured'} for name in _labels(list(getattr(config, 'copilot_mcp_servers', {})), 32)]
    result['memory'] = {'sources': _labels(list(getattr(config, 'memory_paths', [])), 16), 'diagnostics': list(getattr(config, 'memory_diagnostics', []))[:16]}
    return result
