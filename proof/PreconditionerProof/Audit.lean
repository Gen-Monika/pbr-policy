import PreconditionerProof.T4LowerBound
import PreconditionerProof.T6Confidence
import PreconditionerProof.T3Regret
import PreconditionerProof.T7Drift
import PreconditionerProof.T5Monotone
import PreconditionerProof.T1Dimension
import PreconditionerProof.PhaseCorrected
import PreconditionerProof.Conservative
import PreconditionerProof.Counterexamples
import Lean

/-! Reject placeholders and unexpected axioms transitively in every project
theorem. These three are Lean's standard logical foundations, not assumptions
added for this paper. In particular, sorryAx and native-evaluation axioms fail. -/
open Lean in
run_cmd do
  let env ← getEnv
  let allowed : Array Name := #[``propext, ``Classical.choice, ``Quot.sound]
  let mut count : Nat := 0
  for (name, info) in env.constants.toList do
    if name.toString.startsWith "PreconditionerProof." && info.isTheorem then
      count := count + 1
      let axioms ← collectAxioms name
      for ax in axioms do
        unless allowed.contains ax do
          throwError "Unexpected axiom {ax} in {name}"
  if count == 0 then
    throwError "No project theorems found; audit cannot pass vacuously."
  logInfo m!"Axiom audit passed: {count} project theorems; only propext, Classical.choice, Quot.sound allowed."

#print axioms PreconditionerProof.cost_difference
#print axioms PreconditionerProof.first_trigger_is_largest_minimizer
#print axioms PreconditionerProof.stationary_policy_correct
#print axioms PreconditionerProof.execution_exists
#print axioms PreconditionerProof.Counterexamples.no_trigger_but_every_finite_cycle_optimal
#print axioms PreconditionerProof.Counterexamples.direct_stop_observation_gap
#print axioms PreconditionerProof.Counterexamples.direct_branch_example
#print axioms PreconditionerProof.conservative_prediction_le
#print axioms PreconditionerProof.conservative_all_later_cycles_optimal
#print axioms PreconditionerProof.conservative_cycle_exists
#print axioms PreconditionerProof.phase_diff_exact_shape
#print axioms PreconditionerProof.corrected_monotone
#print axioms PreconditionerProof.corrected_monotone_within_noise
#print axioms PreconditionerProof.drift_breaks_monotone
#print axioms PreconditionerProof.schedule_lower_bound
#print axioms PreconditionerProof.schedule_lower_bound_exact
#print axioms PreconditionerProof.fixed_period_attains
#print axioms PreconditionerProof.optimal_class_is_fixed_period
#print axioms PreconditionerProof.advantage_monotone
#print axioms PreconditionerProof.Kstar_monotone
#print axioms PreconditionerProof.within_diff_cancels_drift
#print axioms PreconditionerProof.cross_time_contains_drift
#print axioms PreconditionerProof.drift_bound
#print axioms PreconditionerProof.regret_constant
#print axioms PreconditionerProof.regret_bound
#print axioms PreconditionerProof.regret_nonneg
#print axioms PreconditionerProof.near_optimal_is_four_eps
#print axioms PreconditionerProof.near_optimal_two_level
#print axioms PreconditionerProof.irreducible_floor
#print axioms PreconditionerProof.sampling_improves_only_reducible
#print axioms PreconditionerProof.indistinguishable_implies_equal
#print axioms PreconditionerProof.exploration_necessary
#print axioms PreconditionerProof.identify_both_implies_sees_past
