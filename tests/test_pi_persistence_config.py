from vibes.config import _default_pi_agent_command


def test_pi_default_allows_session_file_confirmation():
    command = _default_pi_agent_command()
    assert '--mode rpc' in command
    assert '--no-session' not in command
    assert 'pi-vibes-tools.ts' in command
