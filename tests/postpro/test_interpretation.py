from physimesh.postpro.interpretation import interpret


def test_missing_metrics_emit_no_sentences():
    assert interpret({}) == []
    assert interpret({'runs': [{'level': 'fine'}], 'mesh_study': {}}) == []


def test_sentences_bind_exact_metrics_and_thresholds():
    result = {'runs': [{'level': 'fine', 'cd': 1.12, 'reference_cd': 1.09173,
                        'reference_relative_difference': .02589,
                        'convergence': {'drift': .002, 'threshold': .005, 'passed': True}}],
              'mesh_study': {'behaviour': 'monotonic', 'observed_order': 4.3, 'gci_fine': .0011,
                             'qualification': 'asymptotic range not demonstrated'}}
    sentences = interpret(result)
    drift = next(item for item in sentences if item['metric'].endswith('convergence.drift'))
    assert drift['value'] == .002 and drift['threshold'] == .005
    assert '0.20%' in drift['text'] and '0.50%' in drift['text']
    assert any('asymptotic range not demonstrated' in item['text'] for item in sentences)
    assert any(item['value'] == .02589 for item in sentences)


def test_oscillatory_mesh_has_no_gci_sentence():
    sentences = interpret({'mesh_study': {'behaviour': 'oscillatory'}})
    assert len(sentences) == 1 and 'no GCI' in sentences[0]['text']


def test_order_capped_estimate_is_primary_and_tiny_drift_is_not_printed_as_zero():
    sentences = interpret({'runs': [{'level': 'fine', 'convergence': {
        'drift': 3e-10, 'threshold': .005, 'passed': True}}],
        'mesh_study': {'behaviour': 'monotonic', 'observed_order': 4.3,
                      'gci_fine': .0011, 'order_capped_gci_fine': .00408,
                      'gci_order_used': 2, 'nominal_order_cap': 2}})
    assert '3.00e-08%' in sentences[0]['text']
    assert 'order-capped GCI 0.408%' in sentences[1]['text']
    assert 'observed-order GCI 0.110%' in sentences[1]['text']
    assert sentences[1]['value']['order_capped_gci_fine'] == .00408
