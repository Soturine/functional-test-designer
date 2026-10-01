#!/usr/bin/env python3
"""Local files for a MANUAL Azure DevOps Test Case import (CSV), built from the `/ftd-azure`
package. Nothing here authenticates or connects: the user imports the files in Azure DevOps.

Azure's Test Case import creates a work item for every row group with a blank ID and updates
the work item whose ID a row group carries. The files are therefore split by intent, and
update mode never turns a case it cannot match by stable FTD identity into a blank-ID row.
"""

from __future__ import annotations

from typing import Any


def suite_order_markdown(suites: list[dict[str, Any]]) -> str:
    """The Suites to create by hand, in the order the Azure tree should read, plus the reverse
    order for a Test Plan that places each new sibling Suite above the existing ones."""
    names = [suite["suite_name"] for suite in suites]
    lines = [
        "# Azure Test Suite order",
        "",
        "Create these static Suites under the Test Plan (or your chosen root Suite) with exactly these "
        "names. The names carry no numeric prefixes; the order comes from how they are created.",
        "",
        "## Desired display order",
        "",
        *(f"{n}. {name}" for n, name in enumerate(names, 1)),
        "",
        "## Manual creation order",
        "",
        "If Azure DevOps places each newly created sibling Suite above the existing ones, create them "
        "in this reverse order so the tree reads top to bottom as above. If new Suites are appended at "
        "the bottom instead, create them in the display order. Check after creating the first two.",
        "",
        *(f"{n}. {name}" for n, name in enumerate(reversed(names), 1)),
        "",
    ]
    return "\n".join(lines)
