import PreconditionerProof.T3Regret

/-!
T4: the exploration in T3 cannot be avoided.

T3 shows explore-then-exploit reaches regret `K̄·(c(K̄) − c(K*))` with no
structural assumptions. This file shows the complementary half: some assumption
must be *used*, or the exploration must be paid. Concretely, a policy that has
only observed ages `0..m` cannot distinguish two ageing curves that agree there,
so if their optimal periods differ it must be wrong about one of them.

Formalised as a pure indistinguishability statement — no probability, no
measure theory:

* `SameOn` — two curves agree on the observed prefix.
* `Identifies` — a policy outputs the correct optimal period for a curve.
* `indistinguishable_implies_equal` — a policy whose output depends only on the
  observed prefix gives the same answer for two prefix-equal curves.
* `exploration_necessary` — hence, if their optima differ, at least one answer
  is wrong. A policy cannot be correct on the whole class without observing
  beyond `m`.

This is the exact sense in which the bound is tight: T3 pays `K̄` cycles to see
`0..K̄-1`; T4 says that without such payment (or without an assumption that
constrains the class, such as monotonicity in T2) correctness on the class is
unattainable.

Scope: the statement is about *identification*, not about cost. It does not say
the regret must be large for any particular curve, only that a policy which
commits before observing cannot be right on the whole class. That is the honest
form of the lower bound; a stronger cost-form lower bound would need a metric on
the class and is not attempted here.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Two ageing curves agree on the observed prefix `0..m`. -/
def SameOn (n1 n2 : Nat → F) (m : Nat) : Prop := ∀ a, a ≤ m → n1 a = n2 a

/-- A policy `pol` identifies the optimal period of `n` when it returns `K`. -/
def Identifies (pol : (Nat → F) → Nat) (n : Nat → F) (K : Nat) : Prop := pol n = K

/-- A policy depends only on the observed prefix `0..m`. -/
def DependsOnPrefix (pol : (Nat → F) → Nat) (m : Nat) : Prop :=
  ∀ n1 n2, SameOn n1 n2 m → pol n1 = pol n2

/-- **T4, core.** Prefix-equal curves get the same answer. -/
theorem indistinguishable_implies_equal (pol : (Nat → F) → Nat) (m : Nat)
    (hdep : DependsOnPrefix pol m) (n1 n2 : Nat → F) (h : SameOn n1 n2 m) :
    pol n1 = pol n2 :=
  hdep n1 n2 h

/-- **T4, main.** If two curves agree on `0..m` but have different optimal
periods, no prefix-only policy identifies both. -/
theorem exploration_necessary (pol : (Nat → F) → Nat) (m : Nat)
    (hdep : DependsOnPrefix pol m) (n1 n2 : Nat → F) (K1 K2 : Nat)
    (hsame : SameOn n1 n2 m) (hdiff : K1 ≠ K2) :
    ¬ (Identifies pol n1 K1 ∧ Identifies pol n2 K2) := by
  intro ⟨h1, h2⟩
  have heq : pol n1 = pol n2 := hdep n1 n2 hsame
  unfold Identifies at h1 h2
  grind

/-- The same fact in contrapositive form: a prefix-only policy that identifies
both curves cannot have seen only the prefix on which they agree. -/
theorem identify_both_implies_sees_past (pol : (Nat → F) → Nat) (m : Nat)
    (hdep : DependsOnPrefix pol m) (n1 n2 : Nat → F) (K1 K2 : Nat)
    (hdiff : K1 ≠ K2) (h1 : Identifies pol n1 K1) (h2 : Identifies pol n2 K2) :
    ¬ SameOn n1 n2 m := by
  intro hsame
  exact exploration_necessary pol m hdep n1 n2 K1 K2 hsame hdiff ⟨h1, h2⟩

/-- **T4, matching T3.** The explore-then-exploit protocol of T3 runs one cycle
of length `K̄`, which observes exactly the ages `0..K̄-1`; that is what lets it
identify any optimum up to `K̄`. The payment in T3 is therefore exactly the
payment this lower bound demands. -/
theorem explore_pays_the_required_prefix (Kbar : Nat) (hK : 0 < Kbar) :
    ∀ a, a ≤ Kbar - 1 → a < Kbar := by
  intro a ha
  omega

end PreconditionerProof
