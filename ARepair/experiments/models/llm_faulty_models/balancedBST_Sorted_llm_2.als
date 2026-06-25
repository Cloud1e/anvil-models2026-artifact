one sig BinaryTree {
  root: lone Node
}

sig Node {
  left, right: lone Node,
  elem: Int
}

// All nodes are in the tree.
fact Reachable {
  Node = BinaryTree.root.*(left + right)
}

// Part (a)
fact Acyclic {
  all n : Node {
    // There are no directed cycles, i.e., a node is not reachable
    // from itself along one or more traversals of left or right.
    n !in n.^(left + right)

    // A node cannot have more than one parent.
    lone n.~(left + right) 

    // A node cannot have another node as both its left child and
    // right child.
    no n.left & n.right
  }
}

// Part (b) — faulty Sorted predicate from realbugs/balancedBST2.als.
pred Sorted() {
  all n: Node | some n.left => n.left.elem < n.elem
  all n: Node | some n.right => n.right.elem > n.elem
}

// Part (c.1)
pred HasAtMostOneChild(n: Node) {
  // Node n has at most one child.
  no n.left || no n.right
}

// Part (c.2)
fun Depth(n: Node): one Int {
  // The number of nodes from the tree's root to n.
  #{n.*~(left + right)}
}

// Part (c.3)
pred Balanced() {
  all n1, n2: Node {
    // If n1 has at most one child and n2 has at most one child,
    // then the depths of n1 and n2 differ by at most 1.
    (HasAtMostOneChild[n1] && HasAtMostOneChild[n2]) =>
    (let diff = minus[Depth[n1], Depth[n2]] | -1 <= diff && diff <= 1)
  }
}

pred RepOk() {
  Sorted
  Balanced
}

run RepOk for 5

