sig Class {
  ext: lone Class
}

one sig Object extends Class {}

pred ObjectNoExt() {
  // Object does not extend any class.
  no Object.ext
}

pred Acyclic() {
  all x, y: Class | x -> y in ext implies x != y
}

pred AllExtObject() {
  // Each class other than Object is a sub-class of Object.
  all c: Class - Object | c in Object.^~ext
}

pred ClassHierarchy() {
  ObjectNoExt
  Acyclic
  AllExtObject
}

run ClassHierarchy for 3
