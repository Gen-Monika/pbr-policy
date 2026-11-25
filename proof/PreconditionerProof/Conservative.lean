import PreconditionerProof.Online

/-!
Proposition 1(iii) under **conservative extrapolation**.

`Online.lean` uses a linear secant predictor (`nextPrediction`) and needs
`DiscreteConvexFromOne` to guarantee that it does not overestimate the true cost
(`current_prediction_upper`). The conservative predictor replaces an unobserved
age by the cost of the largest known age. By `Nondecreasing` alone this never
overestimates, so the first-cycle bound and the locking conclusion survive with
monotonicity only: `DiscreteConvexFromOne` is not used anywhere below.

Observation model as in `Online.lean`: at cycle start the exact prefix `1,...,m`
is known; samples persist across rebuilds; a rebuild at `a` does not observe the
reuse cost `n a`; `ρ` is exact.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Conservative predictor: an unknown age inherits the largest known age's cost. -/
def conservativePredict (n : Nat → F) (m a : Nat) : F :=
  if a ≤ m then n a else n m

/-- Decision rule under conservative extrapolation. -/
def ConservativeDecision (ρ : F) (n : Nat → F) (m a : Nat) : Prop :=
  cost ρ n a < conservativePredict n (knownAt m a) a

/-- Cycle delimited by the conservative rule. -/
def ConservativeCycleEnds (ρ : F) (n : Nat → F) (m L : Nat) : Prop :=
  0 < L ∧ ConservativeDecision ρ n m L ∧
    ∀ a, 0 < a → a < L → ¬ ConservativeDecision ρ n m a

/-- An unobserved positive age sits exactly one past the known prefix. -/
theorem conservative_unknown_eq (m a : Nat) (h : ¬ a ≤ knownAt m a) :
    knownAt m a = a - 1 := by
  have hlt : knownAt m a < a := Nat.lt_of_not_le h
  have hb : knownAt m a ≤ a - 1 := Nat.le_pred_of_lt hlt
  have h1 : a - 1 ≤ knownAt m a := Nat.le_max_right m (a - 1)
  exact Nat.le_antisymm hb h1

/-- **Key lemma**: no overestimation, from monotonicity alone. -/
theorem conservative_prediction_le (n : Nat → F) (hm : Nondecreasing n)
    (m a : Nat) (ha : 0 < a) :
    conservativePredict n (knownAt m a) a ≤ n a := by
  unfold conservativePredict
  by_cases h : a ≤ knownAt m a
  · rw [if_pos h]
    exact le_refl _
  · rw [if_neg h, conservative_unknown_eq m a h]
    exact hm (a - 1) a (by omega)

/-- Hence the policy never rebuilds before the true first trigger. -/
theorem conservative_never_rebuild_early (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hf : FirstTrigger ρ n K) (m a : Nat) (ha : 0 < a) (hak : a < K) :
    ¬ ConservativeDecision ρ n m a := by
  have hu := conservative_prediction_le n hm m a ha
  have hb := hf.2.2 a ha hak
  have hcmp : conservativePredict n (knownAt m a) a ≤ cost ρ n a := le_trans hu hb
  exact fun hcon => absurd hcon (not_lt.mpr hcmp)

/-- Prediction at `K+1` is at least `n K`, because `K` is then known. -/
theorem conservative_predict_at_succ (n : Nat → F) (hm : Nondecreasing n) (m K : Nat) :
    n K ≤ conservativePredict n (knownAt m (K + 1)) (K + 1) := by
  unfold conservativePredict
  by_cases h : K + 1 ≤ knownAt m (K + 1)
  · rw [if_pos h]
    exact hm K (K + 1) (by omega)
  · rw [if_neg h]
    have he : knownAt m (K + 1) = Nat.max m K := by unfold knownAt; simp
    rw [he]
    exact hm K (Nat.max m K) (Nat.le_max_right m K)

theorem conservative_rebuild_by_optimal_plus_one (ρ : F) (n : Nat → F)
    (hm : Nondecreasing n) (K : Nat) (hf : FirstTrigger ρ n K) (m : Nat) :
    ConservativeDecision ρ n m (K + 1) := by
  have hs := next_cost_lt_current_solve ρ n K hf.1 hf.2.1
  have hp := conservative_predict_at_succ n hm m K
  exact Preorder.lt_of_lt_of_le hs hp

/-- A conservative cycle always ends at `K` or `K+1`. -/
theorem conservative_cycle_bounds (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hf : FirstTrigger ρ n K) (m L : Nat)
    (he : ConservativeCycleEnds ρ n m L) : L = K ∨ L = K + 1 := by
  obtain ⟨hL, ht, hb⟩ := he
  have hlow : ¬ L < K := by
    intro h
    exact conservative_never_rebuild_early ρ n hm K hf m L hL h ht
  have hhigh : ¬ K + 1 < L := by
    intro h
    exact hb (K + 1) (by omega) h
      (conservative_rebuild_by_optimal_plus_one ρ n hm K hf m)
  omega

theorem conservative_cycle_ends_unique (ρ : F) (n : Nat → F)
    (m L M : Nat) (hL : ConservativeCycleEnds ρ n m L)
    (hM : ConservativeCycleEnds ρ n m M) : L = M := by
  have hnL : ¬ L < M := fun h => hM.2.2 L hL.1 h hL.2.1
  have hnM : ¬ M < L := fun h => hL.2.2 M hM.1 h hM.2.1
  omega

/-- The conservative prediction at a fixed age is invariant under prefix growth. -/
theorem conservative_predict_stable (n : Nat → F) (m K : Nat) :
    conservativePredict n (knownAt (knownAt m K) K) K
      = conservativePredict n (knownAt m K) K := by
  have he : knownAt (knownAt m K) K = knownAt m K := by
    simp [knownAt, Nat.max_assoc]
  rw [he]

/-- A decision at `K` survives the cycle that ended at `K`. -/
theorem conservative_trigger_preserved (ρ : F) (n : Nat → F) (m K : Nat)
    (ht : ConservativeDecision ρ n m K) :
    ConservativeDecision ρ n (knownAt m K) K := by
  unfold ConservativeDecision at *
  rw [conservative_predict_stable n m K]
  exact ht

/-- Once `K` lies in the known prefix, the rule fires at `K`. -/
theorem conservative_trigger_when_known (ρ : F) (n : Nat → F) (K : Nat)
    (hf : FirstTrigger ρ n K) (m : Nat) (hknown : K ≤ m) :
    ConservativeDecision ρ n m K := by
  have hk : K ≤ knownAt m K := le_trans hknown (Nat.le_max_left m (K - 1))
  unfold ConservativeDecision conservativePredict
  rw [ite_eq_left hk]
  exact hf.2.1

/-- After one cycle the rule fires at `K`, so later cycles have length `K`. -/
theorem conservative_stable_after_one_cycle (ρ : F) (n : Nat → F)
    (hm : Nondecreasing n) (K : Nat) (hf : FirstTrigger ρ n K)
    (m L : Nat) (he : ConservativeCycleEnds ρ n m L) :
    ConservativeDecision ρ n (knownAt m L) K := by
  rcases conservative_cycle_bounds ρ n hm K hf m L he with h | h
  · rw [h] at he ⊢
    exact conservative_trigger_preserved ρ n m K he.2.1
  · rw [h]
    have he2 : knownAt m (K + 1) = Nat.max m K := by unfold knownAt; simp
    rw [he2]
    exact conservative_trigger_when_known ρ n K hf (Nat.max m K) (Nat.le_max_right m K)

/-- **Main theorem**: Proposition 1(iii) with monotonicity only, no convexity. -/
theorem conservative_all_later_cycles_optimal (ρ : F) (n : Nat → F)
    (hm : Nondecreasing n) (K : Nat) (hf : FirstTrigger ρ n K)
    (memory length : Nat → Nat)
    (hrun : ∀ t, ConservativeCycleEnds ρ n (memory t) (length t))
    (hupdate : ∀ t, memory (t + 1) = knownAt (memory t) (length t)) :
    (length 0 = K ∨ length 0 = K + 1) ∧ ∀ t, length (t + 1) = K := by
  constructor
  · exact conservative_cycle_bounds ρ n hm K hf (memory 0) (length 0) (hrun 0)
  · intro t
    have hs := conservative_stable_after_one_cycle ρ n hm K hf (memory t) (length t)
      (hrun t)
    have hs' : ConservativeDecision ρ n (memory (t + 1)) K := by
      rw [hupdate]; exact hs
    have hK : ConservativeCycleEnds ρ n (memory (t + 1)) K :=
      ⟨hf.1, hs', fun a ha hak =>
        conservative_never_rebuild_early ρ n hm K hf (memory (t + 1)) a ha hak⟩
    exact conservative_cycle_ends_unique ρ n (memory (t + 1)) (length (t + 1)) K
      (hrun (t + 1)) hK

/-- Infinite conservative executions exist, so the main theorem is not vacuous. -/
theorem conservative_cycle_exists (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hf : FirstTrigger ρ n K) (m : Nat) :
    ∃ L, ConservativeCycleEnds ρ n m L := by
  by_cases ht : ConservativeDecision ρ n m K
  · exact ⟨K, hf.1, ht, fun a ha hak =>
      conservative_never_rebuild_early ρ n hm K hf m a ha hak⟩
  · refine ⟨K + 1, by omega,
      conservative_rebuild_by_optimal_plus_one ρ n hm K hf m, ?_⟩
    intro a ha hak
    by_cases he : a < K
    · exact conservative_never_rebuild_early ρ n hm K hf m a ha he
    · have : a = K := by omega
      subst this
      exact ht

end PreconditionerProof
