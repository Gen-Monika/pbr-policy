import Std
import Init.Grind.Ordered.Field

/-!
Section 4.4, Proposition 1(i)-(ii).
All costs are elements of an arbitrary linearly ordered field. No completeness,
floating-point arithmetic, or numerical testing is used in these theorems.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Sum of the first k solve costs, with ages 0,...,k-1. -/
def prefixSum (n : Nat → F) : Nat → F
  | 0 => 0
  | k + 1 => prefixSum n k + n k

/-- Equation (7). Mathematical assertions about cost use k >= 1. -/
def cost (ρ : F) (n : Nat → F) (k : Nat) : F :=
  (ρ + prefixSum n k) / (k : F)

def Nondecreasing (n : Nat → F) : Prop :=
  ∀ a b, a ≤ b → n a ≤ n b

/-- The first positive age at which the exact-cost policy rebuilds. -/
def FirstTrigger (ρ : F) (n : Nat → F) (K : Nat) : Prop :=
  0 < K ∧ cost ρ n K < n K ∧
    ∀ a, 0 < a → a < K → n a ≤ cost ρ n a

/-- Largest global minimizer among positive integer cycle lengths. -/
def LargestMinimizer (ρ : F) (n : Nat → F) (K : Nat) : Prop :=
  0 < K ∧ (∀ j, 0 < j → cost ρ n K ≤ cost ρ n j) ∧
    ∀ j, 0 < j → cost ρ n j = cost ρ n K → j ≤ K

theorem nat_pos (a : Nat) (ha : 0 < a) : (0 : F) < (a : F) :=
  OrderedRing.pos_natCast_of_pos a ha

/-- Equation (8), including the necessary positive-age condition. -/
theorem cost_difference (ρ : F) (n : Nat → F) (a : Nat) (ha : 0 < a) :
    cost ρ n (a + 1) - cost ρ n a =
      (n a - cost ρ n a) / ((a : F) + 1) := by
  have hp := nat_pos (F := F) a ha
  have hn : (a : F) ≠ 0 := Preorder.ne_of_gt hp
  have hn' : (a : F) + 1 ≠ 0 := by grind
  simp only [cost, prefixSum, Semiring.natCast_add, Semiring.natCast_one]
  grind

theorem trigger_iff_cost_increases (ρ : F) (n : Nat → F) (a : Nat) (ha : 0 < a) :
    cost ρ n a < n a ↔ cost ρ n a < cost ρ n (a + 1) := by
  have hdiff := cost_difference ρ n a ha
  have hp := nat_pos (F := F) a ha
  have hd : (0 : F) < (a : F) + 1 := by grind
  have hz := Field.IsOrdered.lt_mul_inv_iff_mul_lt (0 : F) (n a - cost ρ n a) hd
  rw [← Field.div_eq_mul_inv] at hz
  simp only [Semiring.zero_mul] at hz
  grind

theorem no_trigger_iff_cost_nonincreases (ρ : F) (n : Nat → F)
    (a : Nat) (ha : 0 < a) :
    n a ≤ cost ρ n a ↔ cost ρ n (a + 1) ≤ cost ρ n a := by
  have := trigger_iff_cost_increases ρ n a ha
  grind

omit [LE F] [LT F] [LawfulOrderLT F] [IsLinearOrder F] [OrderedRing F] in
/-- Exact incremental accounting gives the same running average as equation (7). -/
theorem running_average_eq_cost (ρ : F) (n : Nat → F) (total : Nat → F)
    (hzero : total 0 = ρ)
    (hstep : ∀ a, total (a + 1) = total a + n a) (a : Nat) :
    total a / (a : F) = cost ρ n a := by
  have htotal : ∀ k, total k = ρ + prefixSum n k := by
    intro k
    induction k with
    | zero => simp [prefixSum, hzero, Semiring.add_zero]
    | succ k ih => rw [hstep, ih]; simp [prefixSum, Semiring.add_assoc]
  rw [htotal, cost]

/-- Implements max(0,delta) explicitly without requiring an extra Max instance. -/
noncomputable def clipped (x : F) : F := by
  classical
  exact if x < 0 then 0 else x

theorem exact_prediction (n : Nat → F) (hm : Nondecreasing n) (a : Nat) :
    n 0 + clipped (n a - n 0) = n a := by
  have := hm 0 a (Nat.zero_le a)
  unfold clipped
  split <;> grind

/-- After a strict trigger, the new average is still below the last solve cost. -/
theorem next_cost_lt_current_solve (ρ : F) (n : Nat → F) (a : Nat)
    (ha : 0 < a) (ht : cost ρ n a < n a) :
    cost ρ n (a + 1) < n a := by
  have hp := nat_pos (F := F) a ha
  have hq := nat_pos (F := F) (a + 1) (by omega)
  have hcancel : cost ρ n a * (a : F) = ρ + prefixSum n a :=
    Field.div_mul_cancel (Preorder.ne_of_gt hp)
  have hmul := OrderedRing.mul_lt_mul_of_pos_right ht hp
  unfold cost
  rw [Field.div_eq_mul_inv]
  apply (Field.IsOrdered.mul_inv_lt_iff_lt_mul _ _ hq).mpr
  simp only [prefixSum, Semiring.natCast_add, Semiring.natCast_one]
  grind

theorem trigger_persists (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (a : Nat) (ha : 0 < a) (ht : cost ρ n a < n a) :
    cost ρ n (a + 1) < n (a + 1) := by
  have hnext := next_cost_lt_current_solve ρ n a ha ht
  have hn := hm a (a + 1) (by omega)
  grind

theorem trigger_persists_add (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hK : 0 < K) (ht : cost ρ n K < n K) (d : Nat) :
    cost ρ n (K + d) < n (K + d) := by
  induction d with
  | zero => simpa using ht
  | succ d ih =>
    simpa [Nat.add_assoc] using trigger_persists ρ n hm (K + d) (by omega) ih

theorem cost_strictly_above_after (ρ : F) (n : Nat → F) (hm : Nondecreasing n)
    (K : Nat) (hK : 0 < K) (ht : cost ρ n K < n K) (d : Nat) :
    cost ρ n K < cost ρ n (K + d + 1) := by
  induction d with
  | zero => simpa using (trigger_iff_cost_increases ρ n K hK).mp ht
  | succ d ih =>
    have ht' := trigger_persists_add ρ n hm K hK ht (d + 1)
    have hs := (trigger_iff_cost_increases ρ n (K + (d + 1)) (by omega)).mp ht'
    have hi : cost ρ n K < cost ρ n (K + (d + 1)) := by simpa [Nat.add_assoc] using ih
    exact Preorder.lt_trans hi hs

omit [Field F] [LT F] [LawfulOrderLT F] [OrderedRing F] in
theorem descending_chain (f : Nat → F) (l r : Nat) (hlr : l ≤ r)
    (hs : ∀ i, l ≤ i → i < r → f (i + 1) ≤ f i) : f r ≤ f l := by
  induction r generalizing l with
  | zero =>
    have he : l = 0 := by omega
    subst l
    exact le_refl _
  | succ r ih =>
    by_cases he : l = r + 1
    · subst l; exact le_refl _
    · have hl : l ≤ r := by omega
      have hlast := hs r hl (by omega)
      have hprev := ih l hl (by intro i hli hir; exact hs i hli (by omega))
      exact le_trans hlast hprev

/-- Proposition 1(ii), including the right endpoint of a minimizing plateau. -/
theorem first_trigger_is_largest_minimizer (ρ : F) (n : Nat → F)
    (hm : Nondecreasing n) (K : Nat) (hfirst : FirstTrigger ρ n K) :
    LargestMinimizer ρ n K := by
  obtain ⟨hK, ht, hbefore⟩ := hfirst
  have hafter : ∀ j, K < j → cost ρ n K < cost ρ n j := by
    intro j hj
    have he : j = K + (j - K - 1) + 1 := by omega
    rw [he]
    exact cost_strictly_above_after ρ n hm K hK ht _
  refine ⟨hK, ?_, ?_⟩
  · intro j hj
    by_cases hle : j ≤ K
    · apply descending_chain (cost ρ n) j K hle
      intro i hji hiK
      exact (no_trigger_iff_cost_nonincreases ρ n i (by omega)).mp
        (hbefore i (by omega) hiK)
    · have := hafter j (by omega); grind
  · intro j _ he
    by_cases hn : j ≤ K
    · exact hn
    · have := hafter j (by omega)
      grind

/-- Well-ordering, proved here to keep the project independent of mathlib. -/
theorem exists_first_nat (P : Nat → Prop) (hex : ∃ a, P a) :
    ∃ K, P K ∧ ∀ a, a < K → ¬ P a := by
  classical
  obtain ⟨a, ha⟩ := hex
  induction a using Nat.strongRecOn with
  | ind a ih =>
    by_cases hs : ∃ b, b < a ∧ P b
    · obtain ⟨b, hba, hb⟩ := hs
      exact ih b hba hb
    · exact ⟨a, ha, by grind⟩

theorem first_trigger_exists (ρ : F) (n : Nat → F)
    (hex : ∃ a, 0 < a ∧ cost ρ n a < n a) : ∃ K, FirstTrigger ρ n K := by
  obtain ⟨K, ⟨hK, ht⟩, hmin⟩ := exists_first_nat
    (fun a => 0 < a ∧ cost ρ n a < n a) hex
  refine ⟨K, hK, ht, ?_⟩
  intro a ha hak
  have := hmin a hak
  grind

/-- Correct replacement for the paper's parenthetical claim. The absence of a
strict crossing rules out a LARGEST finite minimizer, not all finite minimizers. -/
theorem no_trigger_no_largest_minimizer (ρ : F) (n : Nat → F)
    (hn : ∀ a, 0 < a → n a ≤ cost ρ n a) (K : Nat) :
    ¬ LargestMinimizer ρ n K := by
  intro hmin
  obtain ⟨hK, hglobal, hlargest⟩ := hmin
  have hdown := (no_trigger_iff_cost_nonincreases ρ n K hK).mp (hn K hK)
  have hup := hglobal (K + 1) (by omega)
  have he : cost ρ n (K + 1) = cost ρ n K := le_antisymm hdown hup
  have := hlargest (K + 1) (by omega) he
  omega

end PreconditionerProof
