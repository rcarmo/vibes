import { describe, expect, test } from 'bun:test';
import {
  canReadTextFiles,
  canSetThinking,
  canSwitchModels,
  canUseTerminalServices,
  canWriteTextFiles,
  describeProvider,
  getAvailableProviders,
  getProviderById,
  normalizeProviders,
  providerCapabilitySummary,
  resolveActiveProviderId,
  selectableBackendId,
} from '../../static/js/features/backends/provider-utils.ts';

const providers = [
  { id: 'pi', label: 'Pi', available: true, active: false, transport: 'pi-rpc', ready: true, capabilities: { model_switch: true, thinking_levels: ['low'] } },
  { id: 'codex', label: 'Codex', available: false, status: 'missing_binary', transport: 'acp', capabilities: { tool_events: true } },
  { id: 'copilot', label: 'Copilot', available: true, status: 'ready', transport: 'acp', capabilities: { permission_requests: true, fs_read_text_file: true, fs_write_text_file: false, terminal_services: false }, session_metadata: { modes: ['default', 'plan'], config_options: [{ id: 'mode' }] } },
];

describe('provider utilities', () => {
  test('normalizes provider payloads', () => {
    expect(normalizeProviders({ providers })).toHaveLength(2);
    expect(normalizeProviders(null)).toEqual([]);
  });

  test('resolves active provider with previous id preference', () => {
    expect(resolveActiveProviderId({ providers, active: 'pi' }, 'codex')).toBe('codex');
    expect(resolveActiveProviderId({ providers, active: 'pi' })).toBe('pi');
    expect(resolveActiveProviderId({ providers: [{ id: 'pi', available: true }] })).toBe('pi');
  });

  test('finds and filters providers', () => {
    expect(getProviderById(providers, 'pi')?.label).toBe('Pi');
    expect(getProviderById(providers, 'missing')).toBeNull();
    expect(getAvailableProviders(providers).map((provider) => provider.id)).toEqual(['pi']);
  });

  test('summarizes capabilities and selection', () => {
    expect(canSwitchModels(providers[0])).toBe(true);
    expect(canSetThinking(providers[0])).toBe(true);
    expect(providerCapabilitySummary(providers[0])).toEqual(['models', 'thinking']);
    expect(providerCapabilitySummary(providers[2])).toEqual(['permissions', 'read-only fs', 'modes', 'config']);
    expect(canReadTextFiles(providers[2])).toBe(true);
    expect(canWriteTextFiles(providers[2])).toBe(false);
    expect(canUseTerminalServices(providers[2])).toBe(false);
    expect(selectableBackendId(providers[0])).toBe('pi');
    expect(selectableBackendId(providers[1], 'pi')).toBe('pi');
    expect(describeProvider(providers[1])).toContain('missing_binary');
  });
});
