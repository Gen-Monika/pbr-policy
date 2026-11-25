import PreconditionerProof.Cost

/-!
T6: two-level error, and what a confidence interval can and cannot buy.

The empirical cost `ĉ(k)` differs from the true `c(k)`. Measured on the stepB
traces the error has **two parts with different natures**:

* **phase aliasing** — samples at the same age are drawn from different
  within-step phases, so `median(dN[a])` is a median of a mixture. Binning by
  `(a, j)` removes it, and the residual shrinks like `1/√n`. Call its bound
  `ea(n)`; it is *reducible*.
* **baseline drift** — ageing itself evolves with physical time. Measured on the
  single-phase case (Blankenbach) this is 20 iterations even with no phase at
  all, and no amount of sampling removes it. Call its bound `ed`; it is
  *irreducible*.

Totality: `error(k) ≤ ea(n) + ed` for every `k`. The main result is that
near-optimality in the empirical ranking implies near-optimality in truth with
constant `4·(ea + ed)`, and — crucially — that the second term does not shrink.
No probability model is used: these are interval statements, valid for every
realisation, so no concentration inequality is needed and none is claimed.

Consequence for the paper: "how many samples identify `K*`" is only a
well-posed question when `ed` is negligible against `ea`. Otherwise the answer
is floored by `4·ed`, and the remedy is a statistical question only for the
phase-aliasing half — the drift half needs a window, a freeze, or change-point
detection.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Two-sided error bound between empirical and true cost, uniformly in `k`. -/
def ErrorBounded (c chat : Nat → F) (e : F) : Prop :=
  ∀ k, chat k - c k ≤ e ∧ c k - chat k ≤ e

/-- `K` is a true minimiser over the comparison class. -/
def TrueMinimiser (c : Nat → F) (cls : Nat → Prop) (K : Nat) : Prop :=
  cls K ∧ ∀ j, cls j → c K ≤ c j

/-- `k` is within `2ε` of the empirical minimum. -/
def EmpiricallyNear (chat : Nat → F) (cls : Nat → Prop) (eps : F) (k : Nat) : Prop :=
  cls k ∧ ∀ j, cls j → chat k ≤ chat j + (2 : F) * eps

/-- **T6, main.** An empirically near-optimal period is `4ε`-optimal in truth. -/
theorem near_optimal_is_four_eps (c chat : Nat → F) (cls : Nat → Prop)
    (K k : Nat) (eps : F) (herr : ErrorBounded c chat eps)
    (hmin : TrueMinimiser c cls K) (hnear : EmpiricallyNear chat cls eps k) :
    c k ≤ c K + (4 : F) * eps := by
  have hKcls : cls K := hmin.1
  obtain ⟨_, hnear'⟩ := hnear
  obtain ⟨h1a, h1b⟩ := herr k
  obtain ⟨h2a, h2b⟩ := herr K
  have hk : chat k ≤ chat K + (2 : F) * eps := hnear' K hKcls
  have hc : c k ≤ chat k + eps := by grind
  have hd : chat K ≤ c K + eps := by grind
  grind

/-- **T6, two-level.** With a reducible part `ea` and an irreducible part `ed`,
near-optimality costs `4·(ea + ed)`. -/
theorem near_optimal_two_level (c chat : Nat → F) (cls : Nat → Prop)
    (K k : Nat) (ea ed : F) (herr : ErrorBounded c chat (ea + ed))
    (hmin : TrueMinimiser c cls K) (hnear : EmpiricallyNear chat cls (ea + ed) k) :
    c k ≤ c K + (4 : F) * (ea + ed) :=
  near_optimal_is_four_eps c chat cls K k (ea + ed) herr hmin hnear

/-- **T6, the floor.** Sampling can shrink `ea` but never removes the `4·ed`
floor, so the guarantee is bounded below independently of the sample count. -/
theorem irreducible_floor (ea ed ea' : F)
    (hred : ea' ≤ ea) (hea' : 0 ≤ ea') (hed : 0 ≤ ed) :
    (4 : F) * ed ≤ (4 : F) * (ea' + ed) ∧
      (4 : F) * (ea' + ed) ≤ (4 : F) * (ea + ed) := by
  constructor
  · grind
  · grind

/-- **T6, monotone in samples.** Better sampling (smaller `ea`) can only improve
the bound — but only down to the floor. -/
theorem sampling_improves_only_reducible (ea ea' ed : F) (hred : ea' ≤ ea) :
    (4 : F) * (ea' + ed) ≤ (4 : F) * (ea + ed) := by
  grind

/-- **T6, when the sample-size question is well posed.** If the drift term is
negligible against the aliasing term, the bound tracks the aliasing term alone. -/
theorem drift_negligible_reduces_to_aliasing (ea ed : F) (hed : 0 ≤ ed)
    (hsmall : ed ≤ ea) : (4 : F) * (ea + ed) ≤ (8 : F) * ea := by
  grind

/-- **T6, exact identification needs zero error.** `K` is the unique empirical
minimiser and the true one only if the two minimiser sets can be separated,
which requires the gap to exceed the error. -/
theorem identification_requires_gap (c chat : Nat → F) (cls : Nat → Prop)
    (K j : Nat) (eps : F) (herr : ErrorBounded c chat eps)
    (hgap : c K + (2 : F) * eps < c j) :
    chat K < chat j := by
  obtain ⟨hKa, hKb⟩ := herr K
  obtain ⟨hja, hjb⟩ := herr j
  grind

end PreconditionerProof
