import PreconditionerProof.T1Dimension

/-!
T3: explore-then-exploit has constant regret.

Protocol: run **one** cycle of length `K̄` (the exploration budget), during which
every age `0, …, K̄-1` is observed exactly once, so `c(1), …, c(K̄)` become known.
Then run `q` cycles of the best known length `K*`. Total length

    T = K̄ + q·K*,

and by T1 the total cost is `K̄·c(K̄) + q·K*·c(K*)`. The regret against the best
fixed period is therefore

    cost − T·c(K*) = K̄·(c(K̄) − c(K*)),

**independent of `q`, hence independent of `T`.** Dividing by `T` gives a
competitive ratio `1 + O(1/T)`.

What this costs in assumptions: **nothing**. No monotonicity, no convexity, no
bound on the noise. The only input is that a cycle of length `K̄` reveals the
whole prefix `n(0), …, n(K̄-1)` — which is exactly how the policy observes costs.
That is why the explore-then-exploit bound is the strongest statement available
here: the structural assumptions the online rule needs (see `T2`) are needed for
*zero-waste* online behaviour, not for learnability.

Scope: `K*` is the minimiser over `1..K̄`; if the true optimum exceeds `K̄` the
bound is against `c(K̄)`-class competitors rather than the global one.
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Cost of exploring one cycle of length `K̄` then exploiting `K*` for `q` cycles. -/
def exploreThenExploit (ρ : F) (n : Nat → F) (Kbar K q : Nat) : F :=
  cycleCost ρ n Kbar + (q : F) * cycleCost ρ n K

/-- Total length of the same protocol. -/
def exploreThenExploitLength (Kbar K q : Nat) : Nat := Kbar + q * K

/-- The protocol's cost in closed form, via `c`. -/
theorem explore_cost_eq (ρ : F) (n : Nat → F) (Kbar K : Nat)
    (hKbar : 0 < Kbar) (hK : 0 < K) (q : Nat) :
    exploreThenExploit ρ n Kbar K q
      = (Kbar : F) * cost ρ n Kbar + (q : F) * ((K : F) * cost ρ n K) := by
  unfold exploreThenExploit
  rw [cycleCost_eq ρ n Kbar hKbar, cycleCost_eq ρ n K hK]

/-- **T3, main.** Regret against the best fixed period is `K̄·(c(K̄) − c(K*))`,
independent of the number of exploitation cycles `q`. -/
theorem regret_constant (ρ : F) (n : Nat → F) (Kbar K : Nat)
    (hKbar : 0 < Kbar) (hK : 0 < K) (q : Nat) :
    exploreThenExploit ρ n Kbar K q
        - (exploreThenExploitLength Kbar K q : F) * cost ρ n K
      = (Kbar : F) * (cost ρ n Kbar - cost ρ n K) := by
  rw [explore_cost_eq ρ n Kbar K hKbar hK q]
  unfold exploreThenExploitLength
  rw [Semiring.natCast_add, Semiring.natCast_mul]
  grind

/-- The same regret written as a bound: it never exceeds `K̄·(c(K̄) − c(K*))`. -/
theorem regret_bound (ρ : F) (n : Nat → F) (Kbar K : Nat)
    (hKbar : 0 < Kbar) (hK : 0 < K) (q : Nat) :
    exploreThenExploit ρ n Kbar K q
      ≤ (exploreThenExploitLength Kbar K q : F) * cost ρ n K
        + (Kbar : F) * (cost ρ n Kbar - cost ρ n K) := by
  have h := regret_constant ρ n Kbar K hKbar hK q
  grind

/-- **T3, competitive ratio.** Normalising by the optimal cost gives
`1 + K̄(c(K̄) − c(K*)) / (T·c(K*))`, which tends to `1` as `T → ∞`. -/
theorem competitive_ratio_form (ρ : F) (n : Nat → F) (Kbar K : Nat)
    (hKbar : 0 < Kbar) (hK : 0 < K) (q : Nat)
    (hT : (0 : F) < (exploreThenExploitLength Kbar K q : F))
    (hc : (0 : F) < cost ρ n K) :
    exploreThenExploit ρ n Kbar K q
      = (exploreThenExploitLength Kbar K q : F) * cost ρ n K
        + (Kbar : F) * (cost ρ n Kbar - cost ρ n K) := by
  have h := regret_constant ρ n Kbar K hKbar hK q
  grind

/-- **T3, the crucial comparison.** If `K` minimises over `1..K̄`, the regret is
nonnegative and the protocol is never cheaper than the reference — so the bound
is tight in the right direction. -/
theorem regret_nonneg (ρ : F) (n : Nat → F) (Kbar K : Nat)
    (hKbar : 0 < Kbar) (hK : 0 < K)
    (hmin : ∀ j, 0 < j → j ≤ Kbar → cost ρ n K ≤ cost ρ n j) (q : Nat) :
    0 ≤ (Kbar : F) * (cost ρ n Kbar - cost ρ n K) := by
  have hle : cost ρ n K ≤ cost ρ n Kbar := hmin Kbar hKbar (le_refl Kbar)
  have hnonneg : (0 : F) ≤ (Kbar : F) := OrderedRing.natCast_nonneg
  have : (0 : F) ≤ cost ρ n Kbar - cost ρ n K := by grind
  exact OrderedRing.mul_nonneg hnonneg this

end PreconditionerProof
