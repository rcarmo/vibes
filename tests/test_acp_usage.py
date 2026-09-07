import pytest
from vibes.acp_usage import context_update, turn_usage

@pytest.mark.parametrize('bad', [True, -1, 1.5, '100', float('inf'), float('nan'), 2**54, None])
def test_invalid_context_and_token_values(bad):
    assert context_update({'used': bad, 'size': 100})['percent'] is None
    assert turn_usage({'inputTokens': bad}) is None

@pytest.mark.parametrize('cost', [None, {}, {'amount': True, 'currency': 'USD'}, {'amount': -1, 'currency': 'USD'}, {'amount': float('nan'), 'currency': 'USD'}, {'amount': 0, 'currency': 'bogus'}])
def test_invalid_cost_is_not_free(cost):
    assert context_update({'used': 0, 'size': 100, 'cost': cost})['cost'] is None

def test_cost_only_and_tokens_only_do_not_invent_context():
    assert context_update({'cost': {'amount': 0, 'currency': 'USD'}}) == {'tokens': None, 'contextWindow': None, 'percent': None, 'cost': {'amount': 0, 'currency': 'USD'}}
    assert context_update({'used': 0, 'size': 100})['percent'] == 0
    assert turn_usage({'totalTokens': 99, 'inputTokens': 0}) == {'totalTokens': 99, 'inputTokens': 0}
