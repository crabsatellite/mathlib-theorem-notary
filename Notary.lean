/-
Copyright (c) 2026 Alex Chengyu Li. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Alex Chengyu Li
-/
import Lean

/-!
# Public theorem-component provenance

Credit is metadata, never an axiom or a proof rule. The external build verifier
validates the signed component before generating a module using `notary_credit`.
`#notary_info` displays that record together with the actual declaration type.
It is a provenance viewer, not a substitute for signature or kernel checking.
-/

open Lean Elab Command

namespace TheoremNotary

initialize records : SimplePersistentEnvExtension (Name × String) (NameMap String) ←
  registerSimplePersistentEnvExtension {
    name := `TheoremNotary.records
    addEntryFn := fun state (name, record) => state.insert name record
    addImportedFn := fun entries => Id.run do
      let mut state := {}
      for group in entries do
        for (name, record) in group do
          state := state.insert name record
      return state
  }

syntax (name := creditCmd) "notary_credit " ident " := " str : command

@[command_elab creditCmd] def elabCredit : CommandElab := fun stx => do
  match stx with
  | `(notary_credit $decl:ident := $record:str) =>
    let name ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo decl
    let env ← getEnv
    unless (env.find? name).isSome do throwError "Unknown component endpoint"
    if ((records.getState env).find? name).isSome then
      throwError "Duplicate notary metadata for {name}"
    modifyEnv fun env => records.addEntry env (name, record.getString)
  | _ => throwUnsupportedSyntax

syntax (name := infoCmd) "#notary_info " ident : command

@[command_elab infoCmd] def elabInfo : CommandElab := fun stx => do
  match stx with
  | `(#notary_info $decl:ident) =>
    let name ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo decl
    let env ← getEnv
    let some ci := env.find? name | throwError "Unknown component endpoint"
    let some record := (records.getState env).find? name |
      throwError "No theorem-component provenance registered for {name}"
    logInfo m!"Theorem component: {name}\nActual Lean type: {ci.type}\n\
      Display metadata only; admission is determined by the external verifier.\n{record}"
  | _ => throwUnsupportedSyntax

/-- Structured declaration selection: one repository may export many theorems. -/
syntax (name := inspectCmd) "#notary_inspect " ident : command

@[command_elab inspectCmd] def elabInspect : CommandElab := fun stx => do
  match stx with
  | `(#notary_inspect $decl:ident) =>
    let name ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo decl
    let env ← getEnv
    let some (.thmInfo ci) := env.checked.get.find? name |
      throwError "Certificate export requires an actual theorem declaration"
    let axioms ← Lean.collectAxioms name
    let data := Json.mkObj [
      ("declaration", toJson name.toString),
      ("type_expr", toJson (reprStr ci.type)),
      ("level_params", toJson (ci.levelParams.map Name.toString)),
      ("axioms", toJson (axioms.map Name.toString))]
    logInfo m!"NOTARY_DECLARATION {data.compress}"
  | _ => throwUnsupportedSyntax

end TheoremNotary
