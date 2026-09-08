import NotaryConsumer.RoundTrip

namespace NotaryApplication
open NotaryExample NotaryConsumer

def mirroredPayload (tree : Tree α) := (roundTrip tree).mirror

theorem mirroredPayload_correct (tree : Tree α) : mirroredPayload tree = tree.mirror :=
  congrArg Tree.mirror (roundTrip_correct tree)

def frameSize (tree : Tree α) := (roundTrip tree).leaves + 4

theorem frameSize_correct (tree : Tree α) : frameSize tree = tree.leaves + 4 :=
  congrArg (fun n => n + 4) (roundTrip_leaves tree)

end NotaryApplication
