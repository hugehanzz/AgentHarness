package com.agentharness.testapp;

import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class LeaveService {
    private static final Map<LeaveStatus, Set<LeaveStatus>> ALLOWED_TRANSITIONS = new HashMap<LeaveStatus, Set<LeaveStatus>>();

    static {
        ALLOWED_TRANSITIONS.put(LeaveStatus.DRAFT, EnumSet.of(LeaveStatus.SUBMITTED));
        ALLOWED_TRANSITIONS.put(LeaveStatus.SUBMITTED, EnumSet.of(LeaveStatus.MANAGER_APPROVED, LeaveStatus.REJECTED));
        ALLOWED_TRANSITIONS.put(LeaveStatus.MANAGER_APPROVED, EnumSet.of(LeaveStatus.HR_APPROVED, LeaveStatus.REJECTED));
        ALLOWED_TRANSITIONS.put(LeaveStatus.HR_APPROVED, EnumSet.of(LeaveStatus.ARCHIVED));
        ALLOWED_TRANSITIONS.put(LeaveStatus.REJECTED, EnumSet.of(LeaveStatus.ARCHIVED));
        ALLOWED_TRANSITIONS.put(LeaveStatus.ARCHIVED, EnumSet.noneOf(LeaveStatus.class));
    }

    public LeaveApplication create(String id, String employeeId, int days, String reason) {
        return new LeaveApplication(id, employeeId, days, reason);
    }

    public void submit(LeaveApplication application) {
        transition(application, LeaveStatus.SUBMITTED);
    }

    public void approveByManager(LeaveApplication application) {
        transition(application, LeaveStatus.MANAGER_APPROVED);
    }

    public void approveByHr(LeaveApplication application) {
        transition(application, LeaveStatus.HR_APPROVED);
    }

    public void reject(LeaveApplication application) {
        transition(application, LeaveStatus.REJECTED);
    }

    public void archive(LeaveApplication application) {
        transition(application, LeaveStatus.ARCHIVED);
    }

    private void transition(LeaveApplication application, LeaveStatus nextStatus) {
        if (application == null) {
            throw new IllegalArgumentException("application must not be null");
        }
        LeaveStatus currentStatus = application.getStatus();
        Set<LeaveStatus> allowedStatuses = ALLOWED_TRANSITIONS.get(currentStatus);
        if (allowedStatuses == null || !allowedStatuses.contains(nextStatus)) {
            throw new InvalidLeaveTransitionException(currentStatus, nextStatus);
        }
        application.setStatus(nextStatus);
    }
}

