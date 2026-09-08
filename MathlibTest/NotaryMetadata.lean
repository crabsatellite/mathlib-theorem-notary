/-
Copyright (c) 2026 Alex Chengyu Li. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Alex Chengyu Li
-/
import Notary

theorem notary_metadata_fixture (n : Nat) : n = n := rfl

notary_credit notary_metadata_fixture :=
  "Provider: fixture provider. This record adds no mathematical premise."

#notary_info notary_metadata_fixture
#print axioms notary_metadata_fixture
