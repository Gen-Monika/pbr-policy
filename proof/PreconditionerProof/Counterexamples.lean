import PreconditionerProof.Online

/-! Exact, kernel-checked boundary cases. These accompany the universal proofs;
finite examples are not used as substitutes for them. -/
namespace PreconditionerProof.Counterexamples
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

/-- rho=1, n(0)=1, n(a)=2 for a>=1. -/
def plateau : Nat → Rat
  | 0 => 1
  | _ + 1 => 2

theorem plateau_nondecreasing : Nondecreasing plateau := by
  intro a b hab
  cases a with
  | zero => cases b <;> simp only [plateau] <;> decide
  | succ a =>
    cases b with
    | zero => omega
    | succ b => change (2 : Rat) ≤ 2; decide

theorem plateau_convex : DiscreteConvexFromOne plateau := by
  intro i
  simp only [plateau]
  decide +kernel

theorem plateau_prefix (j : Nat) : prefixSum plateau (j + 1) = 2 * (j : Rat) + 1 := by
  induction j with
  | zero => simp [prefixSum, plateau]
  | succ j ih =>
    rw [prefixSum, ih]
    simp only [plateau, Semiring.natCast_add, Semiring.natCast_one]
    grind

theorem plateau_cost (k : Nat) (hk : 0 < k) : cost 1 plateau k = 2 := by
  cases k with
  | zero => omega
  | succ j =>
    have hp := nat_pos (F := Rat) (j + 1) (by omega)
    have hz : ((j + 1 : Nat) : Rat) ≠ 0 := Preorder.ne_of_gt hp
    simp only [cost, plateau_prefix]
    grind

/-- The paper's "no finite optimal cycle" parenthesis is false even with rho>0.
Here no age triggers, but EVERY positive finite cycle length is optimal. -/
theorem no_trigger_but_every_finite_cycle_optimal :
    (∀ a, 0 < a → ¬ cost 1 plateau a < plateau a) ∧
    (∀ k, 0 < k → ∀ j, 0 < j → cost 1 plateau k ≤ cost 1 plateau j) := by
  constructor
  · intro a ha
    rw [plateau_cost a ha]
    cases a with
    | zero => omega
    | succ a => change ¬ (2 : Rat) < 2; decide
  · intro k hk j hj
    rw [plateau_cost k hk, plateau_cost j hj]
    decide

def linear (a : Nat) : Rat := (a : Rat) + 1

theorem linear_nondecreasing : Nondecreasing linear := by
  intro a b hab
  have := OrderedRing.natCast_le_natCast_of_le (R := Rat) a b hab
  unfold linear
  grind

theorem linear_convex : DiscreteConvexFromOne linear := by
  intro i
  unfold linear
  grind

theorem linear_rho4_first : FirstTrigger (4 : Rat) linear 3 := by
  refine ⟨by decide, by decide +kernel, ?_⟩
  intro a ha hak
  have he : a = 1 ∨ a = 2 := by omega
  cases he with
  | inl h => subst a; decide +kernel
  | inr h => subst a; decide +kernel

theorem linear_rho4_largest : LargestMinimizer (4 : Rat) linear 3 :=
  first_trigger_is_largest_minimizer 4 linear linear_nondecreasing 3 linear_rho4_first

theorem linear_rho4_direct_stop : CycleEnds (4 : Rat) linear 0 3 := by
  refine ⟨by decide, ?_, ?_⟩
  · unfold Decision
    decide +kernel
  · intro a ha hak
    have he : a = 1 ∨ a = 2 := by omega
    cases he with
    | inl h => subst a; unfold Decision; decide +kernel
    | inr h => subst a; unfold Decision; decide +kernel

/-- At the optimal first stop K=3, only ages 1 and 2 have been observed. -/
theorem direct_stop_observation_gap :
    LargestMinimizer (4 : Rat) linear 3 ∧ CycleEnds (4 : Rat) linear 0 3 ∧
      knownAt 0 3 = 2 ∧ ¬ 3 ≤ knownAt 0 3 :=
  ⟨linear_rho4_largest, linear_rho4_direct_stop, by decide, by decide⟩

/-- A bounded executable scanner for examples only; the universal theorem above
has no finite search bound and proves every cycle, not just these examples. -/
def scan (ρ : Rat) (n : Nat → Rat) (m : Nat) : Nat → Nat → Option Nat
  | 0, _ => none
  | fuel + 1, a =>
    if cost ρ n a < currentPrediction n m a then some a else scan ρ n m fuel (a + 1)

def simulate (ρ : Rat) (n : Nat → Rat) (fuel : Nat) : Nat → Nat → List (Nat × Nat)
  | _, 0 => []
  | m, cycles + 1 =>
    match scan ρ n m fuel 1 with
    | none => []
    | some L => (m, L) :: simulate ρ n fuel (knownAt m L) cycles

def jumpAtOne : Nat → Rat
  | 0 => 1
  | _ + 1 => 10

theorem direct_branch_example : simulate 4 linear 8 0 4 = [(0,3),(2,3),(2,3),(2,3)] := by decide +kernel
theorem delayed_branch_example : simulate 2 linear 8 0 4 = [(0,3),(2,2),(2,2),(2,2)] := by decide +kernel
theorem optimal_age_one_example : simulate 1 jumpAtOne 8 0 4 = [(0,2),(1,1),(1,1),(1,1)] := by decide +kernel
theorem strict_plateau_endpoint_example :
    cost 3 linear 2 = cost 3 linear 3 ∧
    simulate 3 linear 8 0 4 = [(0,3),(2,3),(2,3),(2,3)] := by decide +kernel

end PreconditionerProof.Counterexamples
