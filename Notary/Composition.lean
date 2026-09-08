import Init

/-!
Unbounded composition in an explicit abstract acceptance model.
`stepSound` is the kernel/local-checker soundness and exact-binding assumption;
this file does not prove the implementation of Lean or the filesystem correct.
-/
namespace TheoremNotary.Composition

inductive Accepted {Claim : Type} (foundation : Claim → Prop)
    (checked : Claim → Prop) (requires : Claim → List Claim) : Claim → Prop where
  | foundation {c} : foundation c → Accepted foundation checked requires c
  | derived {c} : checked c →
      (∀ d ∈ requires c, Accepted foundation checked requires d) →
      Accepted foundation checked requires c

/-- Any finite dependency derivation is sound, independently of its depth. -/
theorem composition_sound {Claim : Type} {foundation checked meaning : Claim → Prop}
    {requires : Claim → List Claim}
    (baseSound : ∀ c, foundation c → meaning c)
    (stepSound : ∀ c, checked c → (∀ d ∈ requires c, meaning d) → meaning c)
    {root : Claim} (accepted : Accepted foundation checked requires root) : meaning root := by
  induction accepted with
  | foundation h => exact baseSound _ h
  | derived h _ ih => exact stepSound _ h ih

def MathematicalAcceptance {Claim Credit : Type} (accepted : Claim → Prop)
    (claim : Claim) (_credit : Credit) : Prop := accepted claim

theorem credit_independent {Claim Credit : Type} (accepted : Claim → Prop)
    (claim : Claim) (a b : Credit) :
    MathematicalAcceptance accepted claim a ↔ MathematicalAcceptance accepted claim b := Iff.rfl

/-- Protocol admission additionally requires a valid credit, without changing the proof predicate. -/
theorem replace_valid_credit {Claim Credit : Type} (accepted : Claim → Prop)
    (validCredit : Credit → Prop) (claim : Claim) (a b : Credit)
    (ha : validCredit a) (hb : validCredit b) :
    (accepted claim ∧ validCredit a) ↔ (accepted claim ∧ validCredit b) :=
  ⟨fun h => ⟨h.1, hb⟩, fun h => ⟨h.1, ha⟩⟩

end TheoremNotary.Composition

#print axioms TheoremNotary.Composition.composition_sound
#print axioms TheoremNotary.Composition.credit_independent
#print axioms TheoremNotary.Composition.replace_valid_credit
