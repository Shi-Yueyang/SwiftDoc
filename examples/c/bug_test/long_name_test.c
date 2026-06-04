/*
 * Regression test: long function names should wrap to multiple lines
 * instead of being truncated with "...".
 *
 * Run: swift-doc generate examples/c/bug_test/long_name_test.c --ai off
 */

int global_counter;

/* A function with a very long name that would overflow a single card line */
void very_long_function_name_that_wraps_across_multiple_lines(
    int* read_only_param,
    int* write_only_param,
    int* mixed_param)
{
    *write_only_param = global_counter + *read_only_param + *mixed_param;
    global_counter += 1;
    *mixed_param *= 2;

    /* Test: (DIS)(temp) should NOT be recognized as a function call */
    int temp = *read_only_param;
    int c = (int)(temp);

    /* These ARE real function calls */
    very_long_function_name_that_wraps_across_multiple_lines(0, 0, 0);
}
