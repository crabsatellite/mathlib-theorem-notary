import Init

namespace NotaryExample

inductive Tree (α : Type u) where
  | leaf : α → Tree α
  | branch : Tree α → Tree α → Tree α

def Tree.mirror : Tree α → Tree α
  | .leaf a => .leaf a
  | .branch left right => .branch right.mirror left.mirror

def Tree.leaves : Tree α → Nat
  | .leaf _ => 1
  | .branch left right => left.leaves + right.leaves

theorem Tree.mirror_twice (tree : Tree α) : tree.mirror.mirror = tree := by
  induction tree with
  | leaf a => rfl
  | branch left right ihLeft ihRight =>
    exact (congrArg (fun t => Tree.branch t right.mirror.mirror) ihLeft).trans
      (congrArg (Tree.branch left) ihRight)

theorem Tree.leaves_mirror (tree : Tree α) : tree.mirror.leaves = tree.leaves := by
  induction tree with
  | leaf a => rfl
  | branch left right ihLeft ihRight =>
    exact ((congrArg (fun n => n + left.mirror.leaves) ihRight).trans
      (congrArg (Nat.add right.leaves) ihLeft)).trans (Nat.add_comm _ _)

end NotaryExample
