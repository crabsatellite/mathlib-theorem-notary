import Lean.Replay
import Lean.Util.FoldConsts
import Lean.Util.ForEachExpr

/-!
Independent data-only proof inspection. Imported extensions and native plugins
are never initialized. This is a Lean-kernel checker, not a second kernel.
The surrounding runner pins all files and owns the request and output paths.
-/
open Lean

namespace TheoremNotary.Verifier

deriving instance BEq for QuotKind
deriving instance BEq for QuotVal, InductiveVal

def field (j : Json) (name : String) : IO Json :=
  IO.ofExcept (j.getObjVal? name)

def strings (j : Json) : IO (Array String) :=
  IO.ofExcept <| fromJson? j

def exprDependencies (e : Expr) : NameSet := runST fun σ => do
  let names : ST.Ref σ NameSet ← ST.mkRef {}
  e.forEach (ω := σ) (m := ST σ) fun node => do
    match node with
    | .const n _ | .proj n _ _ => names.modify fun s => s.insert n
    | _ => pure ()
  return ← names.get

def proofDependencies (ci : ConstantInfo) : NameSet := Id.run do
  let mut names := exprDependencies ci.type
  if let some value := ci.value? (allowOpaque := true) then
    names := names ++ exprDependencies value
  match ci with
  | .inductInfo v => names := names ++ .ofList (v.all ++ v.ctors)
  | .ctorInfo v => names := names.insert v.induct
  | .recInfo v =>
    names := names ++ .ofList v.all
    for rule in v.rules do
      names := (names.insert rule.ctor) ++ exprDependencies rule.rhs
  | .quotInfo _ => names := names.insert `Eq
  | _ => pure ()
  return names

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
    return ← reachable env ((proofDependencies ci).toList ++ rest) (seen.insert name) axioms

def signature (ci : ConstantInfo) : Json := Json.mkObj [
  ("declaration", toJson ci.name.toString),
  ("type_expr", toJson (reprStr ci.type)),
  ("level_params", toJson (ci.levelParams.map Name.toString))]

def sameOriginal (a b : ConstantInfo) : Bool :=
  match a, b with
  | .axiomInfo x, .axiomInfo y => x == y
  | .defnInfo x, .defnInfo y => x == y
  | .thmInfo x, .thmInfo y => x == y
  | .opaqueInfo x, .opaqueInfo y => x == y
  | .quotInfo x, .quotInfo y => x == y
  | .inductInfo x, .inductInfo y => x == y
  | .ctorInfo x, .ctorInfo y => x == y
  | .recInfo x, .recInfo y => x == y
  | _, _ => false

def checkOriginalDeclarations (env : Environment) (supplied : Array String) :
    IO (Std.HashMap Name (Array String)) := do
  let mut seen : Std.HashMap Name (ConstantInfo × Bool) := {}
  let mut origins : Std.HashMap Name (Array String) := {}
  for data in env.header.moduleData, moduleName in env.header.moduleNames do
    let own := supplied.contains moduleName.toString
    unless data.constNames.size == data.constants.size do
      throw <| IO.userError s!"Malformed original declaration inventory: {moduleName}"
    for name in data.constNames, ci in data.constants do
      unless name == ci.name do
        throw <| IO.userError s!"Original declaration name mismatch: {moduleName}"
      let mut fromSupplied := own
      if let some (previous, previousOwn) := seen[name]? then
        fromSupplied := own || previousOwn
        if fromSupplied && !sameOriginal previous ci then
          throw <| IO.userError s!"Conflicting original declaration: {name}"
      seen := seen.insert name (ci, fromSupplied)
      origins := origins.insert name ((origins[name]?.getD #[]).push moduleName.toString)
  return origins

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
  -- Import merging may replace a theorem body with a same-type proof. Retain the
  -- original records so one component cannot discharge another's missing proof.
  let origins ← checkOriginalDeclarations env roots
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
    let mut requiredOrigins : Std.HashSet (Array String) := {}
    for dependency in closure do
      let some owners := origins[dependency]? |
        throw <| IO.userError s!"Missing original module origin: {dependency}"
      requiredOrigins := requiredOrigins.insert (owners.qsort (· < ·))
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
      ("dependency_module_alternatives", toJson <| requiredOrigins.toArray.qsort
        (fun a b => a.toList < b.toList)),
      ("referenced_theorems", toJson <| (closure.toArray.filterMap fun n =>
        if n == name.toName then none else
          match env.find? n with | some (.thmInfo _) => some n.toString | _ => none).qsort (· < ·))]
  let mut modules := #[]
  for name in env.header.moduleNames, data in env.header.moduleData do
    let file ← findOLean name
    let mut parts := #[file.toString]
    for level in #[OLeanLevel.server, OLeanLevel.private] do
      let part := level.adjustFileName file
      if ← part.pathExists then parts := parts.push part.toString
    modules := modules.push <| Json.mkObj [
      ("module", toJson name.toString), ("parts", toJson parts),
      ("imports", toJson (data.imports.map (·.module.toString)))]
  return Json.mkObj [
    ("schema", toJson "theorem-notary/check-result/v1"),
    ("kernel_replayed", toJson replay),
    ("original_declarations_checked", toJson true),
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
