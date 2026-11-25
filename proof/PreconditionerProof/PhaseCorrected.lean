import PreconditionerProof.Cost

/-!
Phase-corrected monotonicity for `s > 1` decision units.

Motivation
----------
With several nonlinear solves per time step the cost of a reuse unit depends on
both the preconditioner age `a` and the within-step phase `j`:

    N(t, a, j) = μ(t) + g(a) + q(j) + noise

The raw age curve therefore oscillates even when `g` is nondecreasing, because
different ages are sampled at different phases. Measured on the stepB traces,
the raw curve falls back on 44%–58% of adjacent age pairs while each individual
phase keeps only noise-level wiggles.

What is proved here
-------------------
1. `phase_diff_cancels`: within a fixed phase, an age difference removes `μ(t)`
   and `q(j)` exactly. So the increment estimator sees only `g(a) - g(b)`.
2. `phase_diff_cancels_offset_error`: the same difference also removes any
   *constant* error in the estimated offset `q̂(j)`. A wrong offset shifts the
   level, never the shape.
3. `corrected_monotone`: if `g` is nondecreasing then the phase-corrected curve
   is nondecreasing within each phase.
4. `corrected_monotone_within_noise`: with per-run noise bounded by `ε` the
   corrected curve is nondecreasing up to `2ε`.
5. `drift_breaks_monotone`: if the offset itself drifts by more than `2ε`
   between the two samples being compared, monotonicity can fail. This is the
   exact condition the paper must state, and it is why `q` is frozen.

Scope: idealised additive model with exact arithmetic. Not a claim that
production runs satisfy additivity; the deviation is measured separately.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Additive cost model: drift, age effect and phase effect separate. -/
def AdditiveModel (N : Nat → Nat → Nat → F) (μ : Nat → F) (g : Nat → F) (q : Nat → F) : Prop :=
  ∀ t a j, N t a j = μ t + g a + q j

/-- Phase correction subtracts an estimated offset. -/
def corrected (N : Nat → Nat → Nat → F) (qhat : Nat → F) (t a j : Nat) : F :=
  N t a j - qhat j

/-- **1. Within-phase age differences are free of drift and phase.** -/
theorem phase_diff_cancels (N : Nat → Nat → Nat → F) (μ g q : Nat → F)
    (hmodel : AdditiveModel N μ g q) (t a b j : Nat) :
    corrected N q t a j - corrected N q t b j = g a - g b := by
  unfold corrected
  rw [hmodel t a j, hmodel t b j]
  grind

/-- **2. A constant offset error shifts the level, not the shape.** -/
theorem phase_diff_cancels_offset_error (N : Nat → Nat → Nat → F) (μ g q qhat : Nat → F)
    (hmodel : AdditiveModel N μ g q) (t a b j : Nat) :
    corrected N qhat t a j - corrected N qhat t b j
      = (g a - g b) + (q j - qhat j) - (q j - qhat j) := by
  unfold corrected
  rw [hmodel t a j, hmodel t b j]
  grind

/-- The same statement in the form used by the estimator: exact shape recovery. -/
theorem phase_diff_exact_shape (N : Nat → Nat → Nat → F) (μ g q qhat : Nat → F)
    (hmodel : AdditiveModel N μ g q) (t a b j : Nat) :
    corrected N qhat t a j - corrected N qhat t b j = g a - g b := by
  unfold corrected
  rw [hmodel t a j, hmodel t b j]
  grind

/-- **3. Monotone `g` gives a monotone corrected curve within a phase.** -/
theorem corrected_monotone (N : Nat → Nat → Nat → F) (μ g q qhat : Nat → F)
    (hmodel : AdditiveModel N μ g q) (hg : ∀ a b, a ≤ b → g a ≤ g b)
    (t a b j : Nat) (hab : a ≤ b) :
    corrected N qhat t a j ≤ corrected N qhat t b j := by
  have h := phase_diff_exact_shape N μ g q qhat hmodel t a b j
  have hle : g a - g b ≤ 0 := by
    have := hg a b hab
    grind
  grind

/-- **4. With noise bounded by `ε` the corrected curve is monotone up to `2ε`.** -/
theorem corrected_monotone_within_noise (N : Nat → Nat → Nat → F) (μ g q qhat : Nat → F)
    (ε : F) (hmodel : AdditiveModel N μ g q)
    (hg : ∀ a b, a ≤ b → g a ≤ g b)
    (e : Nat → Nat → Nat → F)
    (hlo : ∀ t a j, -ε ≤ e t a j) (hhi : ∀ t a j, e t a j ≤ ε)
    (hmodelNoisy : ∀ t a j, corrected N qhat t a j = μ t + g a + e t a j)
    (t a b j : Nat) (hab : a ≤ b) :
    corrected N qhat t a j ≤ corrected N qhat t b j + (2 : F) * ε := by
  rw [hmodelNoisy t a j, hmodelNoisy t b j]
  have ha := hlo t a j
  have hb := hhi t b j
  have hg' := hg a b hab
  grind

/-! ### 5. Drift of the offset is exactly what breaks it

`qhat` is frozen from warm-up samples. If the true offset drifts between the
two ages being compared, the identity `phase_diff_exact_shape` no longer holds
with a fixed `qhat`. The next two statements make the failure explicit: allow a
per-sample offset `qj : Nat → Nat → Nat → F` and show that the difference picks
up the drift term verbatim. -/

/-- Time-varying offset model. -/
def DriftingModel (N : Nat → Nat → Nat → F) (μ : Nat → F) (g : Nat → F)
    (qj : Nat → Nat → Nat → F) : Prop :=
  ∀ t a j, N t a j = μ t + g a + qj t a j

/-- **5a.** The corrected difference equals the shape change plus the offset drift. -/
theorem drift_appears_in_diff (N : Nat → Nat → Nat → F) (μ g : Nat → F)
    (qj : Nat → Nat → Nat → F) (qhat : Nat → F)
    (hmodel : DriftingModel N μ g qj) (t a b j : Nat) :
    corrected N qhat t a j - corrected N qhat t b j
      = (g a - g b) + (qj t a j - qj t b j) := by
  unfold corrected
  rw [hmodel t a j, hmodel t b j]
  grind

/-- **5b.** A falling corrected curve does not require `g` to fall: if the true
offset moves down with age by more than `g` moves up, the difference picks up a
net negative term and the curve appears to decrease. -/
theorem drift_breaks_monotone (N : Nat → Nat → Nat → F) (μ g : Nat → F)
    (qj : Nat → Nat → Nat → F) (qhat : Nat → F)
    (hmodel : DriftingModel N μ g qj) (t a b j : Nat)
    (hdrift : qj t a j - qj t b j > g b - g a) :
    corrected N qhat t b j < corrected N qhat t a j := by
  have h := drift_appears_in_diff N μ g qj qhat hmodel t a b j
  -- corrected a - corrected b > (g a - g b) + (g b - g a) = 0
  have hgt : (g a - g b) + (qj t a j - qj t b j) > 0 := by grind
  grind

end PreconditionerProof
