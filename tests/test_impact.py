from codetrust.diff_parser import parse_unified_diff
from codetrust.impact import map_impact


def test_maps_business_and_technical_impact() -> None:
    diff = """diff --git a/payments/api/openapi.yaml b/payments/api/openapi.yaml
--- a/payments/api/openapi.yaml
+++ b/payments/api/openapi.yaml
@@ -1 +1 @@
-old: value
+async_payment: value
"""

    areas = map_impact(parse_unified_diff(diff))
    names = {area.name for area in areas}

    assert {"Payments", "API contracts", "Async runtime"} <= names
