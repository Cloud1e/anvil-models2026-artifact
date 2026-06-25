import edu.mit.csail.sdg.alloy4.A4Reporter;
import edu.mit.csail.sdg.parser.CompModule;
import edu.mit.csail.sdg.parser.CompUtil;
import edu.mit.csail.sdg.translator.A4Options;
import edu.mit.csail.sdg.translator.A4Solution;
import edu.mit.csail.sdg.translator.TranslateAlloyToKodkod;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Optional RQ3 validation path: run ARepair-style test suite commands against a candidate model.
 * <p>
 * This class is separate from {@link Example} on purpose so that the original {@code Example}
 * entry points (including {@code --check-one}) stay identical to prior thesis work.
 * <p>
 * Usage: {@code java -cp "target/classes:target/lib/*:lib/alloy.jar" Rq3ParallelTestSuiteOracle <model.als> <test_suite.als>}
 * <p>
 * Prints the same {@link CodeType} names as {@link Example#AlloyProcess} for consistency in downstream scripts:
 * {@code CORRECT_CODE} if every {@code run testName ... expect M} matches; {@code SYNTAX_ERROR} on parse/runtime failure;
 * {@code DIFF_OUTPUT} otherwise.
 */
public class Rq3ParallelTestSuiteOracle {

    /** Last parser/runtime message when returning SYNTAX_ERROR (mirrors Example's behavior for --check-one). */
    private static String lastSyntaxErrorMessage = null;

    static CodeType classifyCandidateWithTestSuite(String modelContent, String testSuiteContent, boolean verbose) {
        lastSyntaxErrorMessage = null;
        String cleanedTestSuite = testSuiteContent;
        if (modelContent.contains("open util/")) {
            String[] lines = testSuiteContent.split("\\r?\\n");
            StringBuilder cleaned = new StringBuilder();
            for (String line : lines) {
                String trimmed = line.trim();
                if (!trimmed.startsWith("open util/") && !trimmed.startsWith("module ")) {
                    cleaned.append(line).append("\n");
                }
            }
            cleanedTestSuite = cleaned.toString();
        }
        final String combined = modelContent.trim() + "\n\n" + cleanedTestSuite.trim() + "\n";

        Map<String, Integer> testExpectMap = new LinkedHashMap<>();
        for (String rawLine : testSuiteContent.split("\\r?\\n")) {
            String line = rawLine.trim();
            if (line.startsWith("run ") && line.contains("expect ")) {
                int expectPos = line.indexOf("expect ");
                int forPos = line.indexOf(" for");
                if (expectPos > 0 && forPos > 0) {
                    String testName = line.substring(4, forPos).trim();
                    String expectStr = line.substring(expectPos + 7).trim();
                    int expectedResult = expectStr.equals("1") ? 1 : 0;
                    testExpectMap.put(testName, expectedResult);
                }
            }
        }

        CompModule world;
        try {
            world = CompUtil.parseEverything_fromString(new A4Reporter(), combined);
        } catch (Exception e) {
            lastSyntaxErrorMessage = e.getMessage() != null ? e.getMessage() : e.toString();
            if (verbose) {
                e.printStackTrace();
            }
            return CodeType.SYNTAX_ERROR;
        }

        if (testExpectMap.isEmpty()) {
            return CodeType.CORRECT_CODE;
        }

        boolean allTestsPass = true;
        int testsRun = 0;
        A4Options opt = new A4Options();

        try {
            List<edu.mit.csail.sdg.ast.Command> commands = world.getAllCommands();
            for (edu.mit.csail.sdg.ast.Command cmd : commands) {
                String cmdLabel = (cmd.label == null) ? "" : cmd.label.trim();
                Integer expectedResult = testExpectMap.get(cmdLabel);
                if (expectedResult == null) {
                    continue;
                }
                A4Solution solution = TranslateAlloyToKodkod.execute_command(
                        null, world.getAllReachableSigs(), cmd, opt);
                int actualResult = solution.satisfiable() ? 1 : 0;
                testsRun++;
                if (actualResult != expectedResult) {
                    allTestsPass = false;
                    if (verbose) {
                        System.out.println("Test failed: " + cmdLabel + " expected " + expectedResult + " but got " + actualResult);
                    }
                }
            }
            if (testsRun == 0) {
                allTestsPass = false;
                if (verbose) {
                    System.out.println("Warning: Found " + testExpectMap.size() + " tests but ran 0");
                }
            }
        } catch (Exception e) {
            allTestsPass = false;
            lastSyntaxErrorMessage = e.getMessage() != null ? e.getMessage() : e.toString();
            if (verbose) {
                e.printStackTrace();
            }
            return CodeType.SYNTAX_ERROR;
        }

        return allTestsPass ? CodeType.CORRECT_CODE : CodeType.DIFF_OUTPUT;
    }

    public static void main(String[] args) throws Exception {
        if (args == null || args.length < 2) {
            System.err.println("Usage: Rq3ParallelTestSuiteOracle <model.als> <test_suite.als>");
            System.exit(2);
        }
        String modelPath = args[0].trim();
        String testPath = args[1].trim();
        String modelContent = new String(Files.readAllBytes(Paths.get(modelPath)), StandardCharsets.UTF_8);
        String testContent = new String(Files.readAllBytes(Paths.get(testPath)), StandardCharsets.UTF_8);
        CodeType t = classifyCandidateWithTestSuite(modelContent, testContent, false);
        System.out.println(t);
        if (t == CodeType.SYNTAX_ERROR && lastSyntaxErrorMessage != null) {
            System.out.println(lastSyntaxErrorMessage);
        }
    }
}
