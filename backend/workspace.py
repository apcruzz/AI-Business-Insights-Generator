"""Small display preferences only. Authentication and dataset ownership are checked by DatasetCache."""
import json


def validate_state(state):
    allowed = {'filters', 'chartIds', 'kpiIds', 'chartTypes', 'page', 'previewView', 'previewChartIndex',
               'sidebarCollapsed', 'conversationState', 'answerMode'}
    if not isinstance(state, dict) or set(state) - allowed or len(json.dumps(state).encode()) > 16384:
        raise ValueError('Invalid workspace settings.')
    for name in ('filters', 'chartTypes'):
        value = state.get(name, {})
        if not isinstance(value, dict) or len(value) > 100 or any(
            not isinstance(k, str) or len(k) > 100 or not isinstance(v, str) or len(v) > 1000 for k, v in value.items()
        ):
            raise ValueError('Invalid workspace settings.')
    if set(state.get('filters', {})) - {'from', 'to', 'category', 'product', 'weekday', 'period'}:
        raise ValueError('Invalid workspace filters.')
    for name, limit in (('chartIds', 3), ('kpiIds', 40)):
        value = state.get(name, [])
        if not isinstance(value, list) or len(value) > limit or any(not isinstance(v, str) or len(v) > 100 for v in value):
            raise ValueError('Invalid workspace settings.')
    for name, choices in {'page': ('overview', 'detail'), 'previewView': ('charts', 'highlights', 'assistant'),
                          'conversationState': ('open', 'maximized', 'minimized', 'closed')}.items():
        if name in state and state[name] not in choices:
            raise ValueError('Invalid workspace settings.')
    if 'sidebarCollapsed' in state and type(state['sidebarCollapsed']) is not bool:
        raise ValueError('Invalid workspace settings.')
    if 'previewChartIndex' in state and (type(state['previewChartIndex']) is not int or not 0 <= state['previewChartIndex'] <= 2):
        raise ValueError('Invalid workspace settings.')
    if not isinstance(state.get('answerMode', ''), str) or len(state.get('answerMode', '')) > 250:
        raise ValueError('Invalid workspace answer mode.')
    return state
