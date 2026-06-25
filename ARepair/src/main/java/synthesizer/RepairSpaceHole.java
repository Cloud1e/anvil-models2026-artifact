package synthesizer;

import java.util.List;

/** One hole line in repair-space export (location + fragment candidates). */
public final class RepairSpaceHole {
  public final String holeLocation;
  public final int size;
  public final List<String> fragments;

  public RepairSpaceHole(String holeLocation, int size, List<String> fragments) {
    this.holeLocation = holeLocation;
    this.size = size;
    this.fragments = fragments;
  }
}
