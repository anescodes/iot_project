// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract UserRegistry {
    struct User {
        string cki;
        bool exists;
    }

    mapping(string => User) private users;
    string[] public userList;

    event UserRegistered(string userId, string cki);

    function registerUser(string memory _userId, string memory _cki) public {
        // التحقق من وجود المستخدم مسبقاً
        if (!users[_userId].exists) {
            users[_userId] = User(_cki, true);
            userList.push(_userId);
            emit UserRegistered(_userId, _cki);
        }
    }

    function getUserCKI(string memory _userId) public view returns (string memory) {
        require(users[_userId].exists, "User not found");
        return users[_userId].cki;
    }

    function isUserRegistered(string memory _userId) public view returns (bool) {
        return users[_userId].exists;
    }
}