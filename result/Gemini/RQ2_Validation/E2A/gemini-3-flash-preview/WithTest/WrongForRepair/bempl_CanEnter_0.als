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
  some e: Employee | some disj k1, k2: p.owns & e.~authorized | k1.opened_by = r
}

fact {
  no Employee.owns
}

// Should help create tests.
assert no_thief_in_seclab {
  all p : Person | CanEnter[p, secure_lab] implies p in Researcher
}
check no_thief_in_seclab
