import PreconditionerProof.Cost

/-!
T5: the optimal period is monotone in the rebuild cost ratio.

Write `c(k; ρ) = (ρ + S(k)) / k`. For `k₁ < k₂` the difference

    c(k₂; ρ) − c(k₁; ρ) = ρ·(1/k₂ − 1/k₁) + (S(k₂)/k₂ − S(k₁)/k₁)

is **affine in `ρ` with negative slope**, because `1/k₂ − 1/k₁ < 0`. Hence the
set of `ρ` at which the longer period `k₂` beats `k₁` is an up-set: once it wins,
it keeps winning as `ρ` grows. Consequences:

* `advantage_monotone` — if `k₂` is at least as good as `k₁` at `ρ₁`, it is at
  least as good at every `ρ₂ ≥ ρ₁`.
* `Kstar_monotone` — any selection rule returning the *largest* minimizer over
  `{1,…,N}` is nondecreasing in `ρ`.

The data agree: on Tosi C3 `K*` runs 2 → 6 → 8 → 17 as `ρ` runs 1 → 2 → 5 → 10,
and on C5 it runs 2 → 11 → 17 → 27. Cross-case comparisons that look
non-monotone vary `n`, not `ρ`, and are not constrained by this theorem.

The "largest minimizer" convention is part of the statement, not a detail: on a
plateau the smallest-index convention would make `K*` jump down spuriously.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- `c(k₁) ≤ c(k₂)` implies the cross-multiplied inequality. -/
theorem cost_le_cross (ρ : F) (n : Nat → F) (k1 k2 : Nat)
    (h1 : 0 < k1) (h2 : 0 < k2)
    (h : cost ρ n k1 ≤ cost ρ n k2) :
    (k2 : F) * (ρ + prefixSum n k1) ≤ (k1 : F) * (ρ + prefixSum n k2) := by
  have hk1 : (0 : F) < (k1 : F) := nat_pos k1 h1
  have hk2 : (0 : F) < (k2 : F) := nat_pos k2 h2
  have hc1 : cost ρ n k1 * (k1 : F) = ρ + prefixSum n k1 :=
    Field.div_mul_cancel (Preorder.ne_of_gt hk1)
  have hc2 : cost ρ n k2 * (k2 : F) = ρ + prefixSum n k2 :=
    Field.div_mul_cancel (Preorder.ne_of_gt hk2)
  have hs1 : cost ρ n k1 * (k1 : F) * (k2 : F) = (ρ + prefixSum n k1) * (k2 : F) := by grind
  have hs2 : cost ρ n k2 * (k2 : F) * (k1 : F) = (ρ + prefixSum n k2) * (k1 : F) := by grind
  have hm : cost ρ n k1 * (k1 : F) * (k2 : F) ≤ cost ρ n k2 * (k1 : F) * (k2 : F) := by
    have e1 : cost ρ n k1 * (k1 : F) * (k2 : F)
        = cost ρ n k1 * ((k1 : F) * (k2 : F)) := by grind
    have e2 : cost ρ n k2 * (k1 : F) * (k2 : F)
        = cost ρ n k2 * ((k1 : F) * (k2 : F)) := by grind
    rw [e1, e2]
    exact OrderedRing.mul_le_mul_of_nonneg_right h
      (le_of_lt (OrderedRing.mul_pos hk1 hk2))
  have e3 : cost ρ n k2 * (k1 : F) * (k2 : F)
      = cost ρ n k2 * (k2 : F) * (k1 : F) := by grind
  grind

/-- The cross-multiplied inequality implies `c(k₂) ≤ c(k₁)`. -/
theorem cross_cost_le (ρ : F) (n : Nat → F) (k1 k2 : Nat)
    (h1 : 0 < k1) (h2 : 0 < k2)
    (h : (k1 : F) * (ρ + prefixSum n k2) ≤ (k2 : F) * (ρ + prefixSum n k1)) :
    cost ρ n k2 ≤ cost ρ n k1 := by
  have hk1 : (0 : F) < (k1 : F) := nat_pos k1 h1
  have hk2 : (0 : F) < (k2 : F) := nat_pos k2 h2
  have hp : (0 : F) < (k1 : F) * (k2 : F) := OrderedRing.mul_pos hk1 hk2
  have hc1 : cost ρ n k1 * (k1 : F) = ρ + prefixSum n k1 :=
    Field.div_mul_cancel (Preorder.ne_of_gt hk1)
  have hc2 : cost ρ n k2 * (k2 : F) = ρ + prefixSum n k2 :=
    Field.div_mul_cancel (Preorder.ne_of_gt hk2)
  have key : cost ρ n k2 * ((k1 : F) * (k2 : F))
      ≤ cost ρ n k1 * ((k1 : F) * (k2 : F)) := by
    have e1 : cost ρ n k2 * ((k1 : F) * (k2 : F))
        = (ρ + prefixSum n k2) * (k1 : F) := by grind
    have e2 : cost ρ n k1 * ((k1 : F) * (k2 : F))
        = (ρ + prefixSum n k1) * (k2 : F) := by grind
    rw [e1, e2]
    grind
  exact (Field.IsOrdered.mul_le_mul_iff_of_pos_right hp).mp key

/-- **T5, core.** A longer period's advantage never decreases in `ρ`. -/
theorem advantage_monotone (n : Nat → F) (k1 k2 : Nat)
    (h1 : 0 < k1) (h2 : 0 < k2) (hlt : k1 < k2)
    (ρ1 ρ2 : F) (hr : ρ1 ≤ ρ2)
    (h : cost ρ1 n k2 ≤ cost ρ1 n k1) : cost ρ2 n k2 ≤ cost ρ2 n k1 := by
  have hk1 : (0 : F) < (k1 : F) := nat_pos k1 h1
  have hk2 : (0 : F) < (k2 : F) := nat_pos k2 h2
  -- cross-multiplied form at ρ1
  have hx : (k1 : F) * (ρ1 + prefixSum n k2) ≤ (k2 : F) * (ρ1 + prefixSum n k1) :=
    cost_le_cross ρ1 n k2 k1 h2 h1 h
  -- the coefficient of ρ is k1 − k2 ≤ 0, so raising ρ only helps k2
  have hcoef : (k1 : F) - (k2 : F) ≤ 0 := by
    have hle : (k1 : F) ≤ (k2 : F) :=
      OrderedRing.natCast_le_natCast_of_le k1 k2 (le_of_lt hlt)
    grind
  have hstep : ρ2 * ((k1 : F) - (k2 : F)) ≤ ρ1 * ((k1 : F) - (k2 : F)) := by
    by_cases hzero : (k1 : F) - (k2 : F) = 0
    · rw [hzero]; grind
    · have hneg : (k1 : F) - (k2 : F) < 0 := by grind
      exact OrderedRing.mul_le_mul_of_nonpos_right hr (le_of_lt hneg)
  have hx2 : (k1 : F) * (ρ2 + prefixSum n k2) ≤ (k2 : F) * (ρ2 + prefixSum n k1) := by
    grind
  exact cross_cost_le ρ2 n k1 k2 h1 h2 hx2

/-- **T5, main.** The largest minimizer over `{1,…,N}` is nondecreasing in `ρ`. -/
theorem Kstar_monotone (n : Nat → F) (N : Nat) (Kstar : F → Nat)
    (hmin : ∀ ρ, ∀ j, 0 < j → j ≤ N → cost ρ n (Kstar ρ) ≤ cost ρ n j)
    (hmax : ∀ ρ, ∀ j, 0 < j → j ≤ N → cost ρ n j = cost ρ n (Kstar ρ) → j ≤ Kstar ρ)
    (hpos : ∀ ρ, 0 < Kstar ρ)
    (hbound : ∀ ρ, Kstar ρ ≤ N)
    (ρ1 ρ2 : F) (hr : ρ1 ≤ ρ2) : Kstar ρ1 ≤ Kstar ρ2 := by
  by_cases hle : Kstar ρ1 ≤ Kstar ρ2
  · exact hle
  · have hlt : Kstar ρ2 < Kstar ρ1 := by omega
    -- at ρ1, the minimizer Kstar ρ1 is no worse than the longer period Kstar ρ2
    have h1 : cost ρ1 n (Kstar ρ1) ≤ cost ρ1 n (Kstar ρ2) :=
      hmin ρ1 (Kstar ρ2) (hpos ρ2) (hbound ρ2)
    -- T5's core then keeps that order at ρ2
    have h2 : cost ρ2 n (Kstar ρ1) ≤ cost ρ2 n (Kstar ρ2) :=
      advantage_monotone n (Kstar ρ2) (Kstar ρ1) (hpos ρ2) (hpos ρ1) hlt ρ1 ρ2 hr h1
    -- both are minimizers at ρ2, so maximality of Kstar ρ2 gives the contradiction
    have hle2 : cost ρ2 n (Kstar ρ2) ≤ cost ρ2 n (Kstar ρ1) :=
      hmin ρ2 (Kstar ρ1) (hpos ρ1) (hbound ρ1)
    have heq : cost ρ2 n (Kstar ρ1) = cost ρ2 n (Kstar ρ2) := le_antisymm h2 hle2
    have := hmax ρ2 (Kstar ρ1) (hpos ρ1) (hbound ρ1) heq
    omega

end PreconditionerProof
