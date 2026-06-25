sig Element {}

one sig Array {
  // Maps indexes to elements of Element.
  i2e: Int -> Element,
  // Represents the length of the array.
  length: Int
}

// Assume all objects are in the array.
fact Reachable {
  Element = Array.i2e[Int]
}

// Part (a)
fact InBound {
  // All indexes should be greater than or equal to 0 and less than
  // the array length.
  all idx: Array.i2e.Element | idx >= 0 && idx < Array.length
  // Array length should be greater than or equal to 0.
  Array.length >= 0
}

// Part (b)
pred NoConflict() {
  no disj idx1, idx2: Int, e: Element | (idx1 != idx2 && Array.i2e[idx1] = e && Array.i2e[idx2] = e)
}

run NoConflict for 3 