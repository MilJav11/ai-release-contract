from __future__ import annotations

import asyncio
import json

from mcp import Client

from ai_release_contract.mcp_server import mcp


async def main() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

        names = sorted(tool.name for tool in tools.tools)
        print("TOOLS:", ", ".join(names))

        expected = {
            "check_release",
            "compare_metrics",
            "explain_blockers",
        }
        assert set(names) == expected

        result = await client.call_tool(
            "check_release",
            {
                "baseline_path": "examples/baseline.json",
                "candidate_path": "examples/bad_candidate.json",
                "policy_path": "examples/policy.yaml",
            },
        )

        assert not result.is_error
        assert result.structured_content is not None

        print(
            "CHECK_RELEASE:",
            json.dumps(result.structured_content, indent=2),
        )

        assert result.structured_content["verdict"] == "BLOCK"

        blockers = await client.call_tool(
            "explain_blockers",
            {
                "baseline_path": "examples/baseline.json",
                "candidate_path": "examples/bad_candidate.json",
                "policy_path": "examples/policy.yaml",
            },
        )

        assert not blockers.is_error
        assert blockers.structured_content is not None

        print(
            "BLOCKING_METRICS:",
            ", ".join(blockers.structured_content["blocking_metrics"]),
        )


if __name__ == "__main__":
    asyncio.run(main())
