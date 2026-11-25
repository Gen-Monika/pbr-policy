"""Summarize the predeclared paired metrics; never select or alter the policy."""
from pathlib import Path
import json, statistics

R = Path('/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex')
data = json.loads((R / 'analysis.json').read_text())
median = statistics.median

def distribution(values):
    return {'median': median(values), 'min': min(values), 'max': max(values), 'values': values}

results = {}
for case in ['C1', 'C3', 'C4', 'C5', 'Blankenbach', 'MOOSE']:
    pairs = []
    for round_ in range(1, 6 if case == 'MOOSE' else 4):
        old = data['runs'].get(f'full/{case}/r{round_}_old')
        new = data['runs'].get(f'full/{case}/r{round_}_index')
        if not old or not new:
            continue
        samples = sorted(old['rho_samples'] + new['rho_samples'])
        assert samples
        rho = samples[len(samples) // 2]
        def counts(v):
            return v.get('cost_counts', v)
        def cost(v):
            c = counts(v)
            return c['iterations'] + rho * c['rebuilds']
        fixed = data['fixed'][case]
        best_name = min(fixed, key=lambda name: cost(fixed[name]))
        avg_best_name = min(fixed, key=lambda name: cost(fixed[name]) / fixed[name]['solves'])
        best = cost(fixed[best_name])
        avg_best = cost(fixed[avg_best_name]) / fixed[avg_best_name]['solves']
        overlap = min(old['end_epoch'], new['end_epoch']) - max(old['start_epoch'], new['start_epoch'])
        assert overlap > 0, 'Pair did not run concurrently'
        if case != 'MOOSE':
            assert old['final_step_time'] == new['final_step_time'], 'Different physical endpoints'
            assert all(v['final_step_time'] == counts(old)['final_step_time'] for v in fixed.values()), 'Fixed cost endpoint mismatch'
            assert counts(old)['final_step_time'] == counts(new)['final_step_time']
        row = {
            'round': round_, 'rho_common': rho,
            'best_fixed': best_name, 'best_fixed_cost': best,
            'best_fixed_per_solve': avg_best_name,
            'old_cost': cost(old), 'index_cost': cost(new),
            'old_over_best': cost(old) / best, 'index_over_best': cost(new) / best,
            'index_over_old_cost': cost(new) / cost(old),
            'old_per_solve_over_best': cost(old) / counts(old)['solves'] / avg_best,
            'index_per_solve_over_best': cost(new) / counts(new)['solves'] / avg_best,
            'solver_wall_index_over_old': new['solver_wall'] / old['solver_wall'],
            'external_wall_index_over_old': new['wall_seconds'] / old['wall_seconds'],
            'old_rebuilds': counts(old)['rebuilds'], 'index_rebuilds': counts(new)['rebuilds'],
            'old_iterations': counts(old)['iterations'], 'index_iterations': counts(new)['iterations'],
            'old_solves': counts(old)['solves'], 'index_solves': counts(new)['solves'],
            'full_old_counts': {k:old[k] for k in ['solves','iterations','rebuilds']},
            'full_index_counts': {k:new[k] for k in ['solves','iterations','rebuilds']},
            'cost_window': old.get('cost_window', old.get('final_step_time')),
            'decisions_identical': old['decision_sequence'] == new['decision_sequence'],
            'concurrent_overlap_seconds': overlap,
            'index_q_by_phase': new.get('q_by_phase'),
            'index_unknown_phase_rows': new.get('unknown_phase_rows'),
            'index_negative_model_rows': new.get('negative_model_rows'),
            'failure_lines': {'old': old['failure_lines'], 'index': new['failure_lines']},
            'rc': [old['rc'], new['rc']], 'guards': [old['guard'], new['guard']],
        }
        pairs.append(row)
    if not pairs:
        continue
    numeric = ['rho_common', 'old_over_best', 'index_over_best', 'index_over_old_cost',
               'old_per_solve_over_best', 'index_per_solve_over_best',
               'solver_wall_index_over_old', 'external_wall_index_over_old',
               'old_rebuilds', 'index_rebuilds', 'old_iterations', 'index_iterations',
               'old_solves', 'index_solves']
    summary = {k: distribution([p[k] for p in pairs]) for k in numeric}
    summary['best_fixed'] = [p['best_fixed'] for p in pairs]
    summary['completed_pairs'] = len(pairs)
    results[case] = {'summary': summary, 'pairs': pairs}

output = {'analysis_plan': json.loads((R / 'metrics_plan.json').read_text()), 'cases': results}
correction=R/'analysis_correction.json'
if correction.exists():output['endpoint_accounting_correction']=json.loads(correction.read_text())
(R / 'paired_summary.json').write_text(json.dumps(output, indent=2))
for case, value in results.items():
    s = value['summary']
    print(case, 'pairs', s['completed_pairs'], 'rho', round(s['rho_common']['median'], 3),
          'cost/best', round(s['old_over_best']['median'], 4), round(s['index_over_best']['median'], 4),
          'builds', s['old_rebuilds']['values'], s['index_rebuilds']['values'],
          'solver wall', [round(v, 4) for v in s['solver_wall_index_over_old']['values']],
          'fixed', s['best_fixed'])
