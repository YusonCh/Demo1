// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

/// @title VulnerableReentrancy
/// @notice 用于 Demo 的经典重入漏洞合约（类似 EtherStore）
contract VulnerableReentrancy {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 bal = balances[msg.sender];
        require(bal > 0, "No balance");

        // ❌ 典型的 Checks-Effects-Interactions 违反：
        // 先转账，再更新余额，攻击者可在回调中重入 withdraw。
        (bool ok, ) = msg.sender.call{value: bal}("");
        require(ok, "Transfer failed");

        balances[msg.sender] = 0;
    }
}

