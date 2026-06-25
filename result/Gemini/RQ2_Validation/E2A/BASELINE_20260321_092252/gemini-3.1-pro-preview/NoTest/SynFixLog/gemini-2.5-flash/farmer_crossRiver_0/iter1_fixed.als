module farmer

open util/ordering[State] as ord

abstract sig Object { eats: set Object }
one sig Farmer, Fox, Chicken, Grain extends Object {}

fact eating { eats = Fox->Chicken + Chicken->Grain }

sig State {
   near: set Object,
   far: set Object
}

fact initialState {
   let s0 = ord/first |
     s0.near = Object && no s0.far
}

pred crossRiver [from, from', to, to': set Object] {
   some cross: set Object {
      cross = from - from' and
      Farmer in cross and
      #cross <= 2 and
      to' = to + cross and
      from' = from - cross and
      no x, y: from' { x->y in eats }
   }
})
}

fact stateTransition {
  all s: State, s': ord/next[s] {
    Farmer in s.near =>
      crossRiver[s.near, s'.near, s.far, s'.far] else
      crossRiver[s.far, s'.far, s.near, s'.near]
  }
}

pred solvePuzzle {
     ord/last.far = Object
}

run solvePuzzle for 8 State expect 1

assert NoQuantumObjects {
   no s : State | some x : Object | x in s.near and x in s.far
}

check NoQuantumObjects for 8 State expect 0
