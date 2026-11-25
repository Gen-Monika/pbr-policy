import PreconditionerProof.Cost

/-!
T7: the baseline drift `μ(t)` cancels exactly in within-time age differences.

Model the observed iteration count of a reuse unit as

    N(t, a) = μ(t) + g(a) + noise,

where `μ(t)` is the drift of the solve cost caused by the physical time (mesh
evolution, material state, nonlinear convergence profile) and `g(a)` is the
preconditioner ageing term. The policy's increment estimator works with age
differences at a *fixed* time:

    Δ(t, a) = N(t, a) − N(t, 0) = g(a) − g(0) + (noise).

**`μ(t)` disappears identically.** Consequently:

* `within_diff_cancels_drift` — the within-time age difference is independent of
  `μ`, so any estimator built only from within-time differences is immune to
  baseline drift of *arbitrary* magnitude, not merely bounded drift.
* `cross_time_contains_drift` — the complementary statement: comparing the same
  age across two different times leaves `μ(t₁) − μ(t₂)` in the difference. This
  is the only channel through which drift can enter.
* `cross_time_difference_cancels` — subtracting two within-time age differences
  at different times also cancels `μ`, since each term already lost it.

Scope: exact arithmetic under an additive model. An interaction term
`h(t, a)` between drift and age is excluded by construction; if it is present
the decomposition fails and this theorem does not apply.

Consequence for the paper: the 1.2%–6.5% online learning cost should be
attributable to the *cross-time* components of the policy (the running average
`c̄` accumulates across a cycle, and the baseline level `ℓ` is read from an
earlier rebuild), not to `μ` itself. That is a checkable prediction on the
existing traces rather than a claim.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Additive drift + ageing model. -/
def DriftAgeModel (N : Nat → Nat → F) (μ g : Nat → F) : Prop :=
  ∀ t a, N t a = μ t + g a

/-- **T7, core.** A within-time age difference is exactly the ageing difference. -/
theorem within_diff_cancels_drift (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (t a b : Nat) :
    N t a - N t b = g a - g b := by
  rw [hmodel t a, hmodel t b]
  grind

/-- The increment used by the estimator, written out. -/
theorem increment_eq (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (t a : Nat) :
    N t a - N t 0 = g a - g 0 :=
  within_diff_cancels_drift N μ g hmodel t a 0

/-- **T7, complementary.** Across times, `μ` survives in the difference. -/
theorem cross_time_contains_drift (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (t1 t2 a : Nat) :
    N t1 a - N t2 a = μ t1 - μ t2 := by
  rw [hmodel t1 a, hmodel t2 a]
  grind

/-- Two within-time differences at different times are equal, so comparing them
introduces no drift either. -/
theorem cross_time_difference_cancels (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (t1 t2 a b : Nat) :
    (N t1 a - N t1 b) - (N t2 a - N t2 b) = 0 := by
  rw [hmodel t1 a, hmodel t1 b, hmodel t2 a, hmodel t2 b]
  grind

/-- **T7, drift enters only through cross-time terms.** Decompose any comparison
of two observations into its within-time part and its drift part; the within-time
part is drift-free and the remainder is exactly the `μ` difference. -/
theorem decomposition (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (t1 t2 a b : Nat) :
    N t1 a - N t2 b = (g a - g b) + (μ t1 - μ t2) := by
  rw [hmodel t1 a, hmodel t2 b]
  grind

/-- With the drift bounded by `M`, a cross-time comparison errs by at most `2M`,
while the within-time comparison errs by `0`. -/
theorem drift_bound (N : Nat → Nat → F) (μ g : Nat → F)
    (hmodel : DriftAgeModel N μ g) (M : F)
    (μlo : ∀ t, -M ≤ μ t) (μhi : ∀ t, μ t ≤ M) (t1 t2 a : Nat) :
    N t1 a - N t2 a ≤ (2 : F) * M ∧ -((2 : F) * M) ≤ N t1 a - N t2 a := by
  have h := cross_time_contains_drift N μ g hmodel t1 t2 a
  have h1 := μhi t1
  have h2 := μlo t2
  rw [h]
  grind

end PreconditionerProof
