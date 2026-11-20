"""Template statements bound to available metrics, never free-form physics claims."""
import math


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def interpret(results: dict) -> list[dict]:
    statements = []

    def emit(text, metric, value, threshold=None):
        statements.append({'text': text, 'metric': metric, 'value': value, 'threshold': threshold})

    for run in results.get('runs', []):
        level = run.get('level')
        if not level:
            continue
        path = f'runs[{level}]'
        convergence = run.get('convergence', {})
        change, threshold = convergence.get('drift'), convergence.get('threshold')
        if _number(change) and _number(threshold) and type(convergence.get('passed')) is bool:
            state = 'passes' if convergence['passed'] else 'fails'
            # [ASSUMPTION: display precision; review F9] Below 0.00005 relative
            # change, two-decimal percent formatting rounds a nonzero value to zero.
            display_change = f'{change * 100:.2e}%' if 0 < abs(change) < .00005 else f'{change:.2%}'
            emit(f'{level.title()} drag history {state} the iteration-drift check: {display_change} '
                 f'change between the last two 200-iteration windows (gate {threshold:.2%}).',
                 path+'.convergence.drift', change, threshold)
        reconciliation = run.get('reconciliation', {})
        if reconciliation.get('status') in ('accepted', 'diagnostic_only'):
            status = reconciliation['status']
            text = ('Surface force, moment and Cd checks match native OpenFOAM output within declared component tolerances.'
                    if status == 'accepted' else 'Native load reconciliation failed; these results remain diagnostic only.')
            emit(level.title()+': '+text, path+'.reconciliation.status', status, 'accepted')
        cd, reference = run.get('cd'), run.get('reference_cd')
        difference = run.get('reference_relative_difference')
        if _number(cd) and _number(reference) and _number(difference):
            emit(f'{level.title()} Cd {cd:.5f} differs {difference:+.2%} from the frozen '
                 f'Schiller–Naumann correlation value {reference:.5f}.',
                 path+'.reference_relative_difference', difference)
        for region in run.get('wake_reversal', {}).get('sampled_intervals_x_over_d', []):
            if len(region) == 2 and all(_number(value) for value in region):
                emit(f'{level.title()} wake-axis Ux samples are negative from x/D={region[0]:.3f} '
                     f'to {region[1]:.3f}. These are sampled locations.',
                     path+'.wake_reversal.sampled_intervals_x_over_d', region, 0)
    mesh = results.get('mesh_study', {})
    behaviour = mesh.get('behaviour')
    if behaviour == 'monotonic' and _number(mesh.get('observed_order')) and _number(mesh.get('gci_fine')):
        p, gci = mesh['observed_order'], mesh['gci_fine']
        value = {'observed_order': p, 'gci_fine': gci}
        capped = mesh.get('order_capped_gci_fine')
        if _number(capped) and _number(mesh.get('gci_order_used')):
            intro = (f'Mesh study: order-capped GCI {capped:.3%} at order {mesh["gci_order_used"]:.3f}; '
                     f'observed order {p:.3f}, observed-order GCI {gci:.3%}. ')
            value.update(order_capped_gci_fine=capped, gci_order_used=mesh['gci_order_used'])
        else:
            intro = f'Mesh study: observed order {p:.3f}; fine GCI {gci:.3%}. '
        emit(intro
             +mesh.get('qualification', 'This is a discretization sensitivity estimate, not total uncertainty.'),
             'mesh_study', value)
    elif behaviour in ('oscillatory', 'divergent'):
        emit(f'Mesh study is {behaviour}; no GCI is reported.', 'mesh_study.behaviour', behaviour)
    return statements
