sig Class {
  ext: lone Class
}

one sig Object extends Class {}

pred ObjectNoExt() {
  // Object does not extend any class.
  no Object.ext
}

pred Acyclic() {
  // No class is a sub-class of itself (transitively).
  all c: Class | c !in c.^ext
}

pred AllExtObject() {
  all x: Class | x != Object implies x in Object.^ext
}

pred ClassHierarchy() {
  ObjectNoExt
  Acyclic
  AllExtObject
}

run ClassHierarchy for 3
