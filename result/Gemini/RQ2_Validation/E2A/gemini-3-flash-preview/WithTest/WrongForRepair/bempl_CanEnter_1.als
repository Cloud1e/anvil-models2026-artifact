sig Room {}
one sig secure_lab extends Room {}

abstract sig Person {
  owns : set Key
}
sig Employee extends Person {}
sig Researcher extends Person {}

sig Key {
  authorized: one Employee,
  opened_by: one Room
}

pred CanEnter(p: Person, r:Room) {
  some k1: p.owns, k2: p.owns | k1.opened_by = r and k1.authorized = k2.authorized and k1 != k2
}

fact {
  no Employee.owns
}

// Should help create tests.
assert no_thief_in_seclab {
  all p : Person | CanEnter[p, secure_lab] implies p in Researcher
}
check no_thief_in_seclab
