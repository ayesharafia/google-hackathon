import copy
import importlib.util
import itertools
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dependency_plan', ROOT / 'src/physimesh/drone/dependency_plan.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
plan = module.dependency_plan


def port(name='value', unit='N', frame='beam_axis'):
    return {'name': name, 'unit': unit, 'frame': frame}


def model(name, inputs=None):
    return {'id': name, 'inputs': [] if inputs is None else inputs, 'outputs': [port()]}


def connection(source, target, input_name='value'):
    return {'from_model': source, 'from_port': 'value', 'to_model': target, 'to_port': input_name}


def chain():
    return {'models': [model('A'), model('B', [port()]), model('C', [port()])],
            'connections': [connection('A', 'B'), connection('B', 'C')]}


TARGET = [{'model': 'C', 'port': 'value'}]


def assert_failure(result, reason):
    assert reason in result['reasons']
    assert result['status'] != 'PLAN_PROPOSED'
    assert result['order'] == [] and result['targets'] == []
    assert result['evidence_level'] == 'unverified'
    assert result['execution_authorized'] is False


def test_success_no_mutation_and_fresh_result():
    graph = chain()
    before = copy.deepcopy(graph)
    result = plan(graph, TARGET)
    assert result == {'status': 'PLAN_PROPOSED', 'reasons': [], 'order': ['A', 'B', 'C'],
                      'targets': TARGET, 'evidence_level': 'unverified', 'execution_authorized': False}
    result['targets'][0]['model'] = 'changed'
    result['order'].clear()
    assert graph == before and TARGET == [{'model': 'C', 'port': 'value'}]
    assert plan(graph, TARGET)['order'] == ['A', 'B', 'C']


@pytest.mark.parametrize('value', [None, [], 1, True, '', {}, {'models': [], 'connections': [], 'extra': 1}])
def test_malformed_graph(value):
    assert_failure(plan(value, TARGET), 'INVALID_GRAPH')


@pytest.mark.parametrize('value', [None, [], 1, True, '', [{}], [{'model': [], 'port': 'value'}],
                                   [{'model': 'C', 'port': 'bad'}], TARGET * 2])
def test_malformed_targets(value):
    assert_failure(plan(chain(), value), 'INVALID_TARGETS')


@pytest.mark.parametrize('mutate', [
    lambda g: g['models'].append(model('A')),
    lambda g: g['models'][0].update(id='a.b'),
    lambda g: g['models'][0].update(id='A' * 81),
    lambda g: g['models'][0].update(outputs=[port(), port()]),
    lambda g: g['models'][0].update(outputs=[port(unit='')]),
    lambda g: g['models'][0].update(outputs=[port(frame=True)]),
    lambda g: g['models'][0].update(extra=True),
    lambda g: g['connections'].append(connection('A', 'B')),
    lambda g: g['connections'].append(connection('A', 'missing')),
    lambda g: g['connections'][0].update(from_port=[]),
    lambda g: g['connections'][0].update(extra=True),
    lambda g: g['models'][0].update(inputs=()),
])
def test_malformed_declarations(mutate):
    graph = chain()
    mutate(graph)
    assert_failure(plan(graph, TARGET), 'INVALID_GRAPH')


@pytest.mark.parametrize('key,other,reason', [('unit', 'mm', 'UNIT_MISMATCH'),
                                           ('frame', 'aircraft_body', 'FRAME_MISMATCH')])
def test_exact_interfaces_not_inferred(key, other, reason):
    graph = chain()
    graph['models'][1]['inputs'][0][key] = other
    assert_failure(plan(graph, TARGET), reason)


def test_missing_needed_input_and_unneeded_disconnected_allowed():
    graph = chain()
    graph['models'].append(model('Unused', [port()]))
    assert plan(graph, TARGET)['status'] == 'PLAN_PROPOSED'
    graph['connections'].pop()
    assert_failure(plan(graph, TARGET), 'MISSING_REQUIRED_INPUT')


def test_no_guessed_external_inputs_or_execution():
    graph = {'models': [model('C', [port()])], 'connections': []}
    assert_failure(plan(graph, TARGET), 'MISSING_REQUIRED_INPUT')


def test_unused_bad_interface_is_still_rejected():
    graph = chain()
    graph['models'] += [model('D'), model('E', [port(unit='kg')])]
    graph['connections'].append(connection('D', 'E'))
    assert_failure(plan(graph, TARGET), 'UNIT_MISMATCH')


def test_required_cycle_refused_and_unused_cycle_ignored():
    graph = chain()
    graph['models'] += [model('D', [port()]), model('E', [port()])]
    graph['connections'] += [connection('D', 'E'), connection('E', 'D')]
    assert plan(graph, TARGET)['order'] == ['A', 'B', 'C']
    assert_failure(plan(graph, [{'model': 'D', 'port': 'value'}]), 'EXPLICIT_COUPLING_STRATEGY_REQUIRED')


def test_self_cycle_refused():
    graph = {'models': [model('C', [port()])], 'connections': [connection('C', 'C')]}
    assert_failure(plan(graph, TARGET), 'EXPLICIT_COUPLING_STRATEGY_REQUIRED')


def test_all_declaration_orders_and_target_order_are_canonical():
    graph = chain()
    graph['models'].append(model('D'))
    targets = TARGET + [{'model': 'D', 'port': 'value'}]
    expected = plan(graph, targets)
    for models in itertools.permutations(graph['models']):
        for edges in itertools.permutations(graph['connections']):
            for selected in [targets, list(reversed(targets))]:
                assert plan({'models': list(models), 'connections': list(edges)}, selected) == expected


def test_fan_in_two_ports_same_source_not_double_indegree():
    graph = {'models': [model('A'), model('C', [port('left'), port('right')])],
             'connections': [connection('A', 'C', 'left'), connection('A', 'C', 'right')]}
    assert plan(graph, TARGET)['order'] == ['A', 'C']


def test_limits_and_subclasses():
    class Record(dict):
        pass
    class Sequence(list):
        pass
    for graph in [Record(chain()), {'models': Sequence(chain()['models']), 'connections': []},
                  {'models': [model('A')] * 129, 'connections': []},
                  {'models': [], 'connections': [connection('A', 'B')] * 4097}]:
        assert_failure(plan(graph, TARGET), 'INVALID_GRAPH')


def test_seeded_500_random_dags_against_exhaustive_lexical_oracle():
    randomizer = random.Random(3301)
    for _ in range(500):
        names = list('ABCDEFG')[:randomizer.randint(1, 7)]
        graph = {'models': [], 'connections': []}
        dependencies = {}
        for index, name in enumerate(names):
            deps = {earlier for earlier in names[:index] if randomizer.random() < .35}
            dependencies[name] = deps
            graph['models'].append(model(name, [port('from_' + d) for d in sorted(deps)]))
            graph['connections'] += [connection(d, name, 'from_' + d) for d in sorted(deps)]
        targets = [{'model': name, 'port': 'value'} for name in randomizer.sample(names, randomizer.randint(1, len(names)))]
        needed = {t['model'] for t in targets}
        while True:
            expanded = needed | {d for n in needed for d in dependencies[n]}
            if expanded == needed:
                break
            needed = expanded
        valid = []
        for order in itertools.permutations(sorted(needed)):
            positions = {name: i for i, name in enumerate(order)}
            if all(positions[d] < positions[n] for n in needed for d in dependencies[n]):
                valid.append(order)
        expected = list(min(valid))
        randomizer.shuffle(graph['models'])
        randomizer.shuffle(graph['connections'])
        assert plan(graph, targets)['order'] == expected
