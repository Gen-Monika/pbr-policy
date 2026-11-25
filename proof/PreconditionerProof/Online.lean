import PreconditionerProof.Cost

/-!
Proposition 1(iii), with an explicit noiseless sampling model.

At cycle start, m records exact observations at ages 1,...,m. Samples persist
across rebuilds. If age a is reached, ages 1,...,a-1 have been reused, hence the
known prefix is max m (a-1). A rebuild at a does NOT observe the reuse cost n(a).
The fixed rebuild charge and baseline are exact. There is no extra minimum
sample-count requirement in this ideal model.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Convexity restricted to ages >= 1: consecutive slopes there do not decrease. -/
def DiscreteConvexFromOne (n : Nat → F) : Prop :=
  ∀ i, n (i + 2) + (n (i + 2) - n (i + 1)) ≤ n (i + 3)

/-- Prediction at the first unobserved age m+1. -/
def nextPrediction (n : Nat → F) : Nat → F
  | 0 => n 0
  | 1 => n 1
  | i + 2 => n (i + 2) + (n (i + 2) - n (i + 1))

/-- On a reachable decision, either a is known or a=m+1. -/
def predict (n : Nat → F) (m a : Nat) : F :=
  if a ≤ m then n a else nextPrediction n m

def knownAt (m a : Nat) : Nat := Nat.max m (a - 1)

def currentPrediction (n : Nat → F) (m a : Nat) : F :=
  predict n (knownAt m a) a

def Decision (ρ : F) (n : Nat → F) (m a : Nat) : Prop :=
  cost ρ n a < currentPrediction n m a

/-- Reached ages are tested in order; L is the first rebuild decision. -/
def CycleEnds (ρ : F) (n : Nat → F) (m L : Nat) : Prop :=
  0 < L ∧ Decision ρ n m L ∧
    ∀ a, 0 < a → a < L → ¬ Decision ρ n m a

theorem next_prediction_lower (n : Nat → F) (hm : Nondecreasing n) (m : Nat) :
    n m ≤ nextPrediction n m := by
  cases m with
  | zero => simp [nextPrediction, le_refl]
  | succ m =>
    cases m with
    | zero => simp [nextPrediction, le_refl]
    | succ i =>
      have := hm (i + 1) (i + 2) (by omega)
      simp only [nextPrediction]
      grind

omit [LT F] [LawfulOrderLT F] [IsLinearOrder F] [OrderedRing F] in
theorem next_prediction_upper (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (m : Nat) :
    nextPrediction n m ≤ n (m + 1) := by
  cases m with
  | zero => simpa [nextPrediction] using hm 0 1 (by omega)
  | succ m =>
    cases m with
    | zero => simpa [nextPrediction] using hm 1 2 (by omega)
    | succ i => simpa [nextPrediction, Nat.add_assoc] using hc i

omit [LT F] [LawfulOrderLT F] [OrderedRing F] in
theorem current_prediction_upper (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (m a : Nat) (ha : 0 < a) :
    currentPrediction n m a ≤ n a := by
  unfold currentPrediction predict
  split
  · exact le_refl _
  · rename_i hunknown
    have hprefix : a - 1 ≤ knownAt m a := Nat.le_max_right m (a - 1)
    have he : knownAt m a + 1 = a := by unfold knownAt at *; omega
    have hbound := next_prediction_upper n hm hc (knownAt m a)
    simpa [he] using hbound

theorem current_prediction_ge_baseline (n : Nat → F) (hm : Nondecreasing n)
    (m a : Nat) : n 0 ≤ currentPrediction n m a := by
  unfold currentPrediction predict
  split
  · exact hm 0 a (Nat.zero_le a)
  · have h0 := hm 0 (knownAt m a) (Nat.zero_le _)
    have h1 := next_prediction_lower n hm (knownAt m a)
    exact le_trans h0 h1

/-- The max(0,delta) in equation (6) agrees with this absolute-cost predictor. -/
theorem online_rule_iff_decision (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (m a : Nat) :
    (cost ρ n a < n 0 + clipped (currentPrediction n m a - n 0)) ↔
      Decision ρ n m a := by
  have hbase := current_prediction_ge_baseline n hm m a
  have he : n 0 + clipped (currentPrediction n m a - n 0) = currentPrediction n m a := by
    unfold clipped
    split <;> grind
  rw [he]
  rfl

theorem prediction_at_succ_ge_previous (n : Nat → F) (hm : Nondecreasing n)
    (m K : Nat) : n K ≤ currentPrediction n m (K + 1) := by
  unfold currentPrediction predict knownAt
  simp only [Nat.add_sub_cancel]
  split
  · exact hm K (K + 1) (by omega)
  · rename_i hunknown
    have hk : K ≤ Nat.max m K := Nat.le_max_right m K
    have he : Nat.max m K = K := by omega
    rw [he]
    exact next_prediction_lower n hm K

theorem never_rebuild_early (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m a : Nat) (ha : 0 < a) (hak : a < K) : ¬ Decision ρ n m a := by
  have hu := current_prediction_upper n hm hc m a ha
  have hb := hf.2.2 a ha hak
  unfold Decision
  grind

theorem rebuild_by_optimal_plus_one (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hf : FirstTrigger ρ n K) (m : Nat) :
    Decision ρ n m (K + 1) := by
  have hs := next_cost_lt_current_solve ρ n K hf.1 hf.2.1
  have hp := prediction_at_succ_ge_previous n hm m K
  exact Preorder.lt_of_lt_of_le hs hp

/-- A genuine first stopping age exists, so later run theorems are not vacuous. -/
theorem cycle_exists (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m : Nat) : ∃ L, CycleEnds ρ n m L := by
  classical
  by_cases ht : Decision ρ n m K
  · exact ⟨K, hf.1, ht, fun a ha hak => never_rebuild_early ρ n hm hc K hf m a ha hak⟩
  · refine ⟨K + 1, by omega, rebuild_by_optimal_plus_one ρ n hm K hf m, ?_⟩
    intro a ha hak
    by_cases he : a < K
    · exact never_rebuild_early ρ n hm hc K hf m a ha he
    · have : a = K := by omega
      subst a
      exact ht

theorem cycle_bounds (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m L : Nat) (he : CycleEnds ρ n m L) : L = K ∨ L = K + 1 := by
  obtain ⟨hL, ht, hb⟩ := he
  have hlow : ¬ L < K := by
    intro h
    exact never_rebuild_early ρ n hm hc K hf m L hL h ht
  have hhigh : ¬ K + 1 < L := by
    intro h
    exact hb (K + 1) (by omega) h (rebuild_by_optimal_plus_one ρ n hm K hf m)
  omega

omit [LE F] [LawfulOrderLT F] [IsLinearOrder F] [OrderedRing F] in
theorem cycle_ends_unique (ρ : F) (n : Nat → F) (m L M : Nat)
    (hL : CycleEnds ρ n m L) (hM : CycleEnds ρ n m M) : L = M := by
  have hnL : ¬ L < M := fun h => hM.2.2 L hL.1 h hL.2.1
  have hnM : ¬ M < L := fun h => hL.2.2 M hM.1 h hM.2.1
  omega

omit [LE F] [LawfulOrderLT F] [IsLinearOrder F] [OrderedRing F] in
/-- Corrects the paper's direct-stop branch: the SAME prediction persists.
It is not necessary to have observed age K when rebuilding at K. -/
theorem optimal_trigger_preserved (ρ : F) (n : Nat → F) (m K : Nat)
    (ht : Decision ρ n m K) : Decision ρ n (knownAt m K) K := by
  have he : knownAt (knownAt m K) K = knownAt m K := by
    simp [knownAt, Nat.max_assoc]
  change cost ρ n K < predict n (knownAt (knownAt m K) K) K
  rw [he]
  exact ht

omit [LawfulOrderLT F] [IsLinearOrder F] [OrderedRing F] in
theorem optimal_trigger_when_known (ρ : F) (n : Nat → F) (K : Nat)
    (hf : FirstTrigger ρ n K) (m : Nat) (hknown : K ≤ m) : Decision ρ n m K := by
  have hk : K ≤ knownAt m K := Nat.le_trans hknown (Nat.le_max_left m (K - 1))
  unfold Decision currentPrediction predict
  rw [ite_eq_left hk]
  exact hf.2.1

theorem stable_after_one_cycle (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m L : Nat) (he : CycleEnds ρ n m L) : Decision ρ n (knownAt m L) K := by
  cases cycle_bounds ρ n hm hc K hf m L he with
  | inl h =>
    subst L
    exact optimal_trigger_preserved ρ n m K he.2.1
  | inr h =>
    subst L
    apply optimal_trigger_when_known ρ n K hf
    simpa [knownAt] using Nat.le_max_right m K

theorem cycle_length_of_stable (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m L : Nat) (hs : Decision ρ n m K) (he : CycleEnds ρ n m L) : L = K := by
  have hk : CycleEnds ρ n m K :=
    ⟨hf.1, hs, fun a ha hak => never_rebuild_early ρ n hm hc K hf m a ha hak⟩
  exact cycle_ends_unique ρ n m L K he hk

/-- Proposition 1(iii), for every execution of the explicitly defined policy.
Index 0 denotes the first cycle. The update deliberately retains only L-1. -/
theorem all_later_cycles_optimal (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K)
    (memory length : Nat → Nat)
    (hrun : ∀ t, CycleEnds ρ n (memory t) (length t))
    (hupdate : ∀ t, memory (t + 1) = knownAt (memory t) (length t)) :
    (length 0 = K ∨ length 0 = K + 1) ∧ ∀ t, length (t + 1) = K := by
  constructor
  · exact cycle_bounds ρ n hm hc K hf (memory 0) (length 0) (hrun 0)
  · intro t
    have hs := stable_after_one_cycle ρ n hm hc K hf (memory t) (length t) (hrun t)
    have hs' : Decision ρ n (memory (t + 1)) K := by
      rw [hupdate]
      exact hs
    exact cycle_length_of_stable ρ n hm hc K hf (memory (t + 1)) (length (t + 1)) hs' (hrun _)

/-- Infinite executions exist for every exact initial observation prefix. -/
theorem execution_exists (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n) (K : Nat) (hf : FirstTrigger ρ n K) (m₀ : Nat) :
    ∃ memory length : Nat → Nat,
      memory 0 = m₀ ∧
      (∀ t, CycleEnds ρ n (memory t) (length t)) ∧
      (∀ t, memory (t + 1) = knownAt (memory t) (length t)) := by
  classical
  let chooseLength : Nat → Nat := fun m => Classical.choose (cycle_exists ρ n hm hc K hf m)
  have hchoose (m : Nat) : CycleEnds ρ n m (chooseLength m) :=
    Classical.choose_spec (cycle_exists ρ n hm hc K hf m)
  let memory : Nat → Nat := Nat.rec m₀ (fun _ m => knownAt m (chooseLength m))
  let length : Nat → Nat := fun t => chooseLength (memory t)
  refine ⟨memory, length, rfl, ?_, ?_⟩
  · intro t
    exact hchoose (memory t)
  · intro t
    rfl

/-- A single theorem combining finite-crossing existence, global optimality,
and the claimed first-cycle and all-subsequent-cycle conclusions. -/
theorem stationary_policy_correct (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (hc : DiscreteConvexFromOne n)
    (hex : ∃ a, 0 < a ∧ cost ρ n a < n a) :
    ∃ K, FirstTrigger ρ n K ∧ LargestMinimizer ρ n K ∧
      (∀ m, ∃ L, CycleEnds ρ n m L) ∧
      (∀ memory length : Nat → Nat,
        (∀ t, CycleEnds ρ n (memory t) (length t)) →
        (∀ t, memory (t + 1) = knownAt (memory t) (length t)) →
        (length 0 = K ∨ length 0 = K + 1) ∧ ∀ t, length (t + 1) = K) := by
  obtain ⟨K, hf⟩ := first_trigger_exists ρ n hex
  exact ⟨K, hf, first_trigger_is_largest_minimizer ρ n hm K hf,
    cycle_exists ρ n hm hc K hf, all_later_cycles_optimal ρ n hm hc K hf⟩

end PreconditionerProof
