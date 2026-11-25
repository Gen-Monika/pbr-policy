import PreconditionerProof.Cost

/-!
T1: the optimal policy class is one-dimensional.

Any execution of *any* rebuild policy, run for `T` steps, decomposes into
  * an initial segment of `s ≥ 0` steps taken without rebuilding, and
  * cycles of lengths `K₁, …, Kₘ`, each `≥ 1`,
where a cycle of length `k` costs `ρ + prefixSum n k` (one rebuild, then `k-1`
reuses). Since `ρ + prefixSum n k = k · c(k)`, the total cost is a `K_j`-weighted
average of cycle costs plus the initial segment:

    total = prefixSum n s + Σ_j K_j · c(K_j)
         ≥ (s·c(K*) − ρ) + Σ_j K_j · c(K*)
          = T · c(K*) − ρ.

So no policy beats the best fixed period by more than one rebuild charge,
uniformly in `T`, and a fixed period attains `T · c(K*)` exactly. The control
problem is therefore one-dimensional: the only object to learn is `K*`.

The slack is `ρ`, not zero, and it cannot be removed — a policy that delays its
first rebuild never pays that charge. When the schedule rebuilds at step 0 the
bound is exact (`schedule_lower_bound_exact`).
-/
namespace PreconditionerProof
open Std Lean.Grind
attribute [local instance] Semiring.natCast Ring.intCast

variable {F : Type} [Field F] [LE F] [LT F] [LawfulOrderLT F]
  [IsLinearOrder F] [OrderedRing F]

/-- Cost of one complete cycle of length `k`: one rebuild, then `k-1` reuses. -/
def cycleCost (ρ : F) (n : Nat → F) (k : Nat) : F := ρ + prefixSum n k

/-- Cost of a list of cycles. -/
def cyclesCost (ρ : F) (n : Nat → F) : List Nat → F
  | [] => 0
  | k :: t => cycleCost ρ n k + cyclesCost ρ n t

/-- Total length of a list of cycles. -/
def cyclesLength : List Nat → Nat
  | [] => 0
  | k :: t => k + cyclesLength t

/-- Total cost of a schedule: initial segment plus the listed cycles. -/
def scheduleCost (ρ : F) (n : Nat → F) (s : Nat) (ks : List Nat) : F :=
  prefixSum n s + cyclesCost ρ n ks

/-- Total number of steps a schedule occupies. -/
def scheduleLength (s : Nat) (ks : List Nat) : Nat := s + cyclesLength ks

/-- A cycle of length `k` costs exactly `k` times the average cost `c(k)`. -/
theorem cycleCost_eq (ρ : F) (n : Nat → F) (k : Nat) (hk : 0 < k) :
    cycleCost ρ n k = (k : F) * cost ρ n k := by
  have hk0 : (k : F) ≠ 0 := Preorder.ne_of_gt (nat_pos k hk)
  have hcancel : cost ρ n k * (k : F) = ρ + prefixSum n k :=
    Field.div_mul_cancel hk0
  unfold cycleCost
  grind

/-- The cumulative reuse cost of `s` steps equals `s · c(s) − ρ`. -/
theorem prefixSum_eq (ρ : F) (n : Nat → F) (s : Nat) (hs : 0 < s) :
    prefixSum n s = (s : F) * cost ρ n s - ρ := by
  have hs0 : (s : F) ≠ 0 := Preorder.ne_of_gt (nat_pos s hs)
  have hcancel : cost ρ n s * (s : F) = ρ + prefixSum n s :=
    Field.div_mul_cancel hs0
  grind

/-- **Core list lemma.** A list of positive cycles costs at least `sum·c(K*)`. -/
theorem cyclesCost_ge (ρ : F) (n : Nat → F) (K : Nat)
    (hmin : ∀ j, 0 < j → cost ρ n K ≤ cost ρ n j)
    (ks : List Nat) (hks : ∀ k ∈ ks, 0 < k) :
    (cyclesLength ks : F) * cost ρ n K ≤ cyclesCost ρ n ks := by
  induction ks with
  | nil =>
    unfold cyclesLength cyclesCost
    rw [Semiring.natCast_zero, Semiring.zero_mul]
    exact le_refl _
  | cons a t ih =>
    have ha : 0 < a := hks a (List.mem_cons_self)
    have ht : ∀ k ∈ t, 0 < k := fun k hk => hks k (List.mem_cons_of_mem a hk)
    have h1 : (a : F) * cost ρ n K ≤ cycleCost ρ n a := by
      rw [cycleCost_eq ρ n a ha]
      exact OrderedRing.mul_le_mul_of_nonneg_left (hmin a ha)
        OrderedRing.natCast_nonneg
    have h2 := ih ht
    simp only [cyclesLength, cyclesCost, Semiring.natCast_add]
    grind

/-- The initial segment costs at least `s·c(K*) − ρ`. -/
theorem prefixSum_ge_min (ρ : F) (n : Nat → F) (K : Nat)
    (hmin : ∀ j, 0 < j → cost ρ n K ≤ cost ρ n j) (hρ : 0 ≤ ρ) (s : Nat) :
    (s : F) * cost ρ n K - ρ ≤ prefixSum n s := by
  rcases Nat.eq_zero_or_pos s with h | h
  · subst h
    simp only [prefixSum, Semiring.natCast_zero, Semiring.zero_mul]
    grind
  · rw [prefixSum_eq ρ n s h]
    have hle : (s : F) * cost ρ n K ≤ (s : F) * cost ρ n s :=
      OrderedRing.mul_le_mul_of_nonneg_left (hmin s h)
        OrderedRing.natCast_nonneg
    grind

/-- **T1, lower bound.** Every schedule costs at least `T·c(K*) − ρ`. -/
theorem schedule_lower_bound (ρ : F) (n : Nat → F) (K : Nat)
    (hmin : ∀ j, 0 < j → cost ρ n K ≤ cost ρ n j) (hρ : 0 ≤ ρ)
    (s : Nat) (ks : List Nat) (hks : ∀ k ∈ ks, 0 < k) :
    (scheduleLength s ks : F) * cost ρ n K - ρ ≤ scheduleCost ρ n s ks := by
  have hs := prefixSum_ge_min ρ n K hmin hρ s
  have hl := cyclesCost_ge ρ n K hmin ks hks
  unfold scheduleCost scheduleLength
  rw [Semiring.natCast_add]
  grind

/-- **T1, exact form** when the schedule rebuilds at step 0: no slack at all. -/
theorem schedule_lower_bound_exact (ρ : F) (n : Nat → F) (K : Nat)
    (hmin : ∀ j, 0 < j → cost ρ n K ≤ cost ρ n j)
    (ks : List Nat) (hks : ∀ k ∈ ks, 0 < k) :
    (cyclesLength ks : F) * cost ρ n K ≤ scheduleCost ρ n 0 ks := by
  have hl := cyclesCost_ge ρ n K hmin ks hks
  unfold scheduleCost
  unfold prefixSum
  grind

/-- Sum of `q` copies of the same term. -/
theorem sum_replicate_F (q : Nat) (x : F) :
    (List.replicate q x).sum = (q : F) * x := by
  induction q with
  | zero => simp only [List.replicate_zero, List.sum_nil, Semiring.natCast_zero,
                       Semiring.zero_mul]
  | succ m ihm =>
    rw [List.replicate_succ, List.sum_cons, ihm, Semiring.natCast_add,
        Semiring.natCast_one]
    grind

/-- Map of a constant function over a replicate. -/
theorem map_replicate_const (q : Nat) (x : F) :
    (List.replicate q (0 : Nat)).map (fun _ => x) = List.replicate q x := by
  induction q with
  | zero => simp
  | succ m ih => simp [List.replicate_succ, ih]

/-- **T1, attainment.** `q` cycles of length `K` cost exactly `(q·K)·c(K)`. -/
theorem fixed_period_attains (ρ : F) (n : Nat → F) (K : Nat) (hK : 0 < K) (q : Nat) :
    scheduleCost ρ n 0 (List.replicate q K) = (q : F) * (K : F) * cost ρ n K := by
  unfold scheduleCost
  have hcyc : cyclesCost ρ n (List.replicate q K) = (q : F) * cycleCost ρ n K := by
    induction q with
    | zero => simp [cyclesCost, Semiring.natCast_zero, Semiring.zero_mul]
    | succ m ihm =>
      rw [List.replicate_succ, cyclesCost, ihm, Semiring.natCast_add, Semiring.natCast_one]
      grind
  rw [hcyc, cycleCost_eq ρ n K hK]
  unfold prefixSum
  grind

/-- **T1, conclusion.** No policy beats the best fixed period by more than one
rebuild charge, and running `scheduleLength 0 ks` cycles of length `K` — which
occupies exactly the same number of steps — attains the bound without slack. -/
theorem optimal_class_is_fixed_period (ρ : F) (n : Nat → F) (K : Nat) (hK : 0 < K)
    (hmin : ∀ j, 0 < j → cost ρ n K ≤ cost ρ n j) (hρ : 0 ≤ ρ)
    (s : Nat) (ks : List Nat) (hks : ∀ k ∈ ks, 0 < k) :
    (scheduleLength s ks : F) * cost ρ n K - ρ ≤ scheduleCost ρ n s ks ∧
      scheduleCost ρ n 0 (List.replicate (cyclesLength ks) K)
        = ((cyclesLength ks : Nat) : F) * (K : F) * cost ρ n K := by
  refine ⟨schedule_lower_bound ρ n K hmin hρ s ks hks, ?_⟩
  exact fixed_period_attains ρ n K hK (cyclesLength ks)

end PreconditionerProof
