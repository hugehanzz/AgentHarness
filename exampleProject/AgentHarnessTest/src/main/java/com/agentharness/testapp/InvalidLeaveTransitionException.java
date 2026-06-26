package com.agentharness.testapp;

public class InvalidLeaveTransitionException extends RuntimeException {
    public InvalidLeaveTransitionException(LeaveStatus from, LeaveStatus to) {
        super("Invalid leave transition: " + from + " -> " + to);
    }
}

