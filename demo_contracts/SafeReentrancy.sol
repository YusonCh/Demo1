// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

/// @title SafeReentrancy
/// @notice 对应 VulnerableReentrancy 的安全版本，演示防重入模式
contract SafeReentrancy {
    mapping(address => uint256) public balances;
    bool private locked;

    modifier nonReentrant() {
        require(!locked, "ReentrancyGuard: reentrant call");
        locked = true;
        _;
        locked = false;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external nonReentrant {
        uint256 bal = balances[msg.sender];
        require(bal > 0, "No balance");

        // ✅ 遵循 Checks-Effects-Interactions：
        // 先更新状态，再进行外部调用。
        balances[msg.sender] = 0;

        (bool ok, ) = msg.sender.call{value: bal}("");
        require(ok, "Transfer failed");
    }
}

