from codetrust.diff_parser import parse_unified_diff


def test_parses_added_and_removed_lines() -> None:
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,2 +1,2 @@
-old = True
+new = True
 keep = True
"""

    files = parse_unified_diff(diff)

    assert len(files) == 1
    assert files[0].path == "a.py"
    assert files[0].removed[0].line == 1
    assert files[0].removed[0].text == "old = True"
    assert files[0].added[0].line == 1
    assert files[0].added[0].text == "new = True"


def test_parses_new_file() -> None:
    diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+one = 1
+two = 2
"""

    files = parse_unified_diff(diff)

    assert files[0].path == "new.py"
    assert [line.line for line in files[0].added] == [1, 2]
