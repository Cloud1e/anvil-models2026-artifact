one sig DLL {
  header: lone Node
}

sig Node {
  pre, nxt: lone Node,
  elem: Int
}

// All nodes are reachable from the header node.
fact Reachable {
  Node = DLL.header.*nxt
}

// Part (a)
fact Acyclic {
  // The list has no directed cycle along nxt, i.e., no node is
  // reachable from itself following one or more traversals along nxt.
  all n: Node | n !in n.^nxt
}

// Part (b)
pred UniqueElem() {
  // Unique nodes contain unique elements.
  no disj n1, n2: Node | n1.elem = n2.elem
}

// Part (c)
pred Sorted() {
  // The list is sorted in ascending order (<=) along nxt.
  all n: Node | some n.nxt => n.elem <= n.nxt.elem
}

// Part (d)
pred ConsistentPreAndNxt() {
  all n: Node | n in n.nxt.pre and n in n.pre.nxt
}

pred RepOk() {
  UniqueElem
  Sorted
  ConsistentPreAndNxt
}

run RepOk for 3
