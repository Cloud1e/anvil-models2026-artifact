sig Class {
  ext: lone Class
}

one sig Object extends Class {}

pred ObjectNoExt() {
  all c: Class | Object !in (c.ext + c.ext.ext + c.ext.ext.ext)
}

pred Acyclic() {
  // No class is a sub-class of itself (transitively).
  all c: Class | c !in c.^ext
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
