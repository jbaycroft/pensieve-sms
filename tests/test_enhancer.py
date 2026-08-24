import importlib
import pytest


def _reload(monkeypatch, backend='gemini'):
    monkeypatch.setenv('LLM_BACKEND', backend)
    monkeypatch.setenv('ENHANCE_MOCK', '0')
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
    monkeypatch.setenv('OLLAMA_MODEL', 'qwen2.5:1.5b')
    import app.enhancer as mod
    importlib.reload(mod)
    return mod


# ENHANCE_MOCK bypass

def test_mock_enhance_returns_raw(monkeypatch):
    monkeypatch.setenv('ENHANCE_MOCK', '1')
    import app.enhancer as mod; importlib.reload(mod)
    assert mod.enhance('fix the pump') == 'fix the pump'
    monkeypatch.setenv('ENHANCE_MOCK', '0'); importlib.reload(mod)

def test_mock_infer_returns_general(monkeypatch):
    monkeypatch.setenv('ENHANCE_MOCK', '1')
    import app.enhancer as mod; importlib.reload(mod)
    assert mod.infer_domain('anything') == 'general'
    monkeypatch.setenv('ENHANCE_MOCK', '0'); importlib.reload(mod)


# Gemini primary

def test_gemini_primary_called(monkeypatch):
    mod = _reload(monkeypatch, 'gemini')
    calls = []
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: (calls.append('g') or 'Schedule irrigation run'))
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: (_ for _ in ()).throw(AssertionError('should not reach ollama')))
    assert mod.enhance('do the irrigation') == 'Schedule irrigation run'
    assert calls == ['g']

def test_gemini_falls_back_to_ollama(monkeypatch):
    mod = _reload(monkeypatch, 'gemini')
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: 'Check pH levels')
    assert mod.enhance('ph levels') == 'Check pH levels'

def test_both_backends_fail_returns_raw(monkeypatch):
    mod = _reload(monkeypatch, 'gemini')
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: None)
    assert mod.enhance('original text') == 'original text'


# Ollama primary

def test_ollama_primary_called(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    calls = []
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: (calls.append('o') or 'Refill nutrient reservoir'))
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: (_ for _ in ()).throw(AssertionError('should not reach gemini')))
    assert mod.enhance('refill nutrients') == 'Refill nutrient reservoir'
    assert calls == ['o']

def test_ollama_falls_back_to_gemini(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: None)
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: 'Calibrate EC meter')
    assert mod.enhance('calibrate ec') == 'Calibrate EC meter'

def test_infer_domain_valid_response(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: 'hydroponics')
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    assert mod.infer_domain('check the nutrient pump') == 'hydroponics'

def test_infer_domain_garbage_returns_general(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: 'I cannot classify this.')
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    assert mod.infer_domain('some task') == 'general'

def test_infer_domain_none_returns_general(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: None)
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    assert mod.infer_domain('task') == 'general'

def test_enhance_truncated_to_120(monkeypatch):
    mod = _reload(monkeypatch, 'ollama')
    monkeypatch.setattr(mod, '_call_ollama', lambda p, c: 'x' * 200)
    monkeypatch.setattr(mod, '_call_gemini', lambda p, c: None)
    assert len(mod.enhance('something')) == 120

def test_check_ollama_available_false_when_down(monkeypatch):
    import urllib.request
    mod = _reload(monkeypatch, 'ollama')
    def _raise(*a, **kw): raise ConnectionRefusedError('not running')
    monkeypatch.setattr(urllib.request, 'urlopen', _raise)
    assert mod._check_ollama_available() is False

def test_invalid_backend_raises_assertion(monkeypatch):
    monkeypatch.setenv('LLM_BACKEND', 'bad_value')
    import app.enhancer as mod
    with pytest.raises(AssertionError):
        importlib.reload(mod)
    monkeypatch.setenv('LLM_BACKEND', 'gemini')
    importlib.reload(mod)
