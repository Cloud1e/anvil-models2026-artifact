package synthesizer;

import static parser.etc.Context.logger;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.List;

/**
 * Appends one JSON line per {@link Synthesizer#synthesize} invocation (machine-readable repair
 * space), for downstream tools instead of scraping {@code [DEBUG]} log lines.
 */
public final class RepairSpaceJsonlWriter {

  private RepairSpaceJsonlWriter() {}

  public static void appendLine(
      String exportPath,
      List<String> affectedParagraphNames,
      List<String> affectedTests,
      List<Long> searchSpaces,
      List<Integer> combinationsTried,
      List<RepairSpaceHole> holes) {
    if (exportPath == null || exportPath.isEmpty()) {
      return;
    }
    String json =
        toJsonObject(
            affectedParagraphNames,
            affectedTests,
            searchSpaces,
            combinationsTried,
            holes);
    Path p = Paths.get(exportPath);
    try {
      Files.createDirectories(p.getParent());
      Files.write(
          p,
          (json + System.lineSeparator()).getBytes(StandardCharsets.UTF_8),
          StandardOpenOption.CREATE,
          StandardOpenOption.APPEND);
    } catch (IOException e) {
      logger.info("Could not append repair-space JSONL: " + e.getMessage());
    }
  }

  private static String toJsonObject(
      List<String> affectedParagraphNames,
      List<String> affectedTests,
      List<Long> searchSpaces,
      List<Integer> combinationsTried,
      List<RepairSpaceHole> holes) {
    StringBuilder sb = new StringBuilder(512);
    sb.append('{');
    sb.append("\"affected_paragraph_names\":").append(toJsonStrList(affectedParagraphNames));
    sb.append(',');
    sb.append("\"affected_tests\":").append(toJsonStrList(affectedTests));
    sb.append(',');
    sb.append("\"search_spaces\":").append(toJsonLongList(searchSpaces));
    sb.append(',');
    sb.append("\"fix_failed_tried\":").append(toJsonIntList(combinationsTried));
    sb.append(',');
    sb.append("\"holes\":").append(toJsonHoles(holes));
    sb.append('}');
    return sb.toString();
  }

  private static String toJsonHoles(List<RepairSpaceHole> holes) {
    StringBuilder sb = new StringBuilder();
    sb.append('[');
    for (int i = 0; i < holes.size(); i++) {
      if (i > 0) {
        sb.append(',');
      }
      RepairSpaceHole h = holes.get(i);
      sb.append('{');
      sb.append("\"hole\":").append(jsonQuote(h.holeLocation));
      sb.append(',');
      sb.append("\"size\":").append(h.size);
      sb.append(',');
      sb.append("\"fragments\":").append(toJsonStrList(h.fragments));
      sb.append('}');
    }
    sb.append(']');
    return sb.toString();
  }

  private static String toJsonStrList(List<String> xs) {
    StringBuilder sb = new StringBuilder();
    sb.append('[');
    for (int i = 0; i < xs.size(); i++) {
      if (i > 0) {
        sb.append(',');
      }
      sb.append(jsonQuote(xs.get(i)));
    }
    sb.append(']');
    return sb.toString();
  }

  private static String toJsonLongList(List<Long> xs) {
    StringBuilder sb = new StringBuilder();
    sb.append('[');
    for (int i = 0; i < xs.size(); i++) {
      if (i > 0) {
        sb.append(',');
      }
      sb.append(xs.get(i));
    }
    sb.append(']');
    return sb.toString();
  }

  private static String toJsonIntList(List<Integer> xs) {
    StringBuilder sb = new StringBuilder();
    sb.append('[');
    for (int i = 0; i < xs.size(); i++) {
      if (i > 0) {
        sb.append(',');
      }
      sb.append(xs.get(i));
    }
    sb.append(']');
    return sb.toString();
  }

  static String jsonQuote(String s) {
    if (s == null) {
      return "\"\"";
    }
    StringBuilder sb = new StringBuilder(s.length() + 8);
    sb.append('"');
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      switch (c) {
        case '\\':
          sb.append("\\\\");
          break;
        case '"':
          sb.append("\\\"");
          break;
        case '\n':
          sb.append("\\n");
          break;
        case '\r':
          sb.append("\\r");
          break;
        case '\t':
          sb.append("\\t");
          break;
        default:
          sb.append(c);
      }
    }
    sb.append('"');
    return sb.toString();
  }
}
