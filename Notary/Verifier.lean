import Lean.Replay
import Lean.Util.FoldConsts

/-!
Independent data-only proof inspection. Imported extensions and native plugins
are never initialized. This is a Lean-kernel checker, not a second kernel.
The surrounding runner pins all files and owns the request and output paths.
-/
open Lean

namespace TheoremNotary.Verifier

def field (j : Json) (name : String) : IO Json :=
  IO.ofExcept (j.getObjVal? name)

def strings (j : Json) : IO (Array String) :=
  IO.ofExcept <| fromJson? j

partial def reachable (env : Environment) (todo : List Name)
    (seen : NameSet := {}) (axioms : Array Name := #[]) : IO (NameSet × Array Name) := do
  match todo with
  | [] => return (seen, axioms)
  | name :: rest =>
    if seen.contains name then return ← reachable env rest seen axioms
    let some ci := env.find? name | throw <| IO.userError s!"Uncovered constant: {name}"
    if ci.isUnsafe || ci.isPartial then
      throw <| IO.userError s!"Unsafe or partial proof dependency: {name}"
    let axioms := match ci with | .axiomInfo _ => axioms.push name | _ => axioms
    return ← reachable env (ci.getUsedConstantsAsSet.toList ++ rest) (seen.insert name) axioms

def signature (ci : ConstantInfo) : Json := Json.mkObj [
  ("declaration", toJson ci.name.toString),
  ("type_expr", toJson (reprStr ci.type)),
  ("level_params", toJson (ci.levelParams.map Name.toString))]

unsafe def check (request : Json) : IO Json := do
  let roots ← strings (← field request "modules")
  let selected ← strings (← field request "declarations")
  let allowed ← strings (← field request "allowed_axioms")
  for ax in allowed do
    unless #["propext", "Classical.choice", "Quot.sound"].contains ax do
      throw <| IO.userError s!"Axiom is outside the fixed kernel-only profile: {ax}"
  let replay ← IO.ofExcept <| (← field request "replay").getBool?
  let objects ← IO.ofExcept <| (← field request "objects").getStr?
  let officialPath ← getBuiltinSearchPath (← findSysroot)
  searchPathRef.set officialPath
  let base ← importModules #[{ module := `Init }] {} (loadExts := false)
  -- Publisher paths are introduced only after this trusted checker is running.
  searchPathRef.set ((System.FilePath.mk objects) :: officialPath)
  let imports := roots.map fun x => ({ module := x.toName } : Import)
  -- Default private level includes all available exported/server/private data.
  let env ← importModules imports {} (trustLevel := 0) (plugins := #[]) (loadExts := false)
  let checked ← if replay then (← mkEmptyEnvironment).replay env.constants.map₁ else pure env
  let mut declarations := #[]
  for name in selected do
    let some ci@(.thmInfo _) := env.find? name.toName |
      throw <| IO.userError s!"Selected export is not a theorem in the proof data: {name}"
    let some replayed := checked.toKernelEnv.find? name.toName |
      throw <| IO.userError s!"Selected theorem absent after kernel replay: {name}"
    unless ci.type == replayed.type && ci.levelParams == replayed.levelParams do
      throw <| IO.userError s!"Replay changed the declaration type: {name}"
    let (closure, axs) ← reachable env [name.toName]
    for ax in axs do
      unless allowed.contains ax.toString do
        throw <| IO.userError s!"Disallowed axiom: {ax}"
      let some actual := env.find? ax | throw <| IO.userError "Missing axiom"
      let some official := base.find? ax | throw <| IO.userError "Axiom absent from official foundation"
      unless actual.type == official.type && actual.levelParams == official.levelParams do
        throw <| IO.userError s!"Axiom type differs from official foundation: {ax}"
    declarations := declarations.push <| Json.mkObj [
      ("interface", signature ci),
      ("axioms", toJson ((axs.map Name.toString).qsort (· < ·))),
      ("closure_size", toJson closure.size),
      ("referenced_theorems", toJson <| (closure.toArray.filterMap fun n =>
        if n == name.toName then none else
          match env.find? n with | some (.thmInfo _) => some n.toString | _ => none).qsort (· < ·))]
  let mut modules := #[]
  for name in env.header.moduleNames do
    let file ← findOLean name
    let mut parts := #[file.toString]
    for level in #[OLeanLevel.server, OLeanLevel.private] do
      let part := level.adjustFileName file
      if ← part.pathExists then parts := parts.push part.toString
    modules := modules.push <| Json.mkObj [
      ("module", toJson name.toString), ("parts", toJson parts)]
  return Json.mkObj [
    ("schema", toJson "theorem-notary/check-result/v1"),
    ("kernel_replayed", toJson replay),
    ("extensions_initialized", toJson false),
    ("modules", toJson modules), ("declarations", toJson declarations)]

end TheoremNotary.Verifier

unsafe def main (args : List String) : IO UInt32 := do
  try
    let [requestPath, outputPath] := args |
      throw <| IO.userError "Usage: Verifier.lean request.json result.json"
    initSearchPath (← findSysroot)
    let request ← IO.ofExcept <| Json.parse (← IO.FS.readFile requestPath)
    let result ← TheoremNotary.Verifier.check request
    IO.FS.writeFile outputPath (result.compress ++ "\n")
    return (0 : UInt32)
  catch error =>
    IO.eprintln s!"notary checker rejected: {error}"
    return (1 : UInt32)
