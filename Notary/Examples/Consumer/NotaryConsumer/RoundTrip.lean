import NotaryExample.Trees

namespace NotaryConsumer
open NotaryExample

def roundTrip (tree : Tree α) := tree.mirror.mirror

theorem roundTrip_correct (tree : Tree α) : roundTrip tree = tree :=
  Tree.mirror_twice tree

theorem roundTrip_leaves (tree : Tree α) : (roundTrip tree).leaves = tree.leaves :=
  (Tree.leaves_mirror tree.mirror).trans (Tree.leaves_mirror tree)

end NotaryConsumer
