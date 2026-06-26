package com.agentharness.testapp;

import java.util.Objects;

public class LeaveApplication {
    private final String id;
    private final String employeeId;
    private final int days;
    private final String reason;
    private LeaveStatus status;

    public LeaveApplication(String id, String employeeId, int days, String reason) {
        if (isBlank(id)) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (isBlank(employeeId)) {
            throw new IllegalArgumentException("employeeId must not be blank");
        }
        if (days <= 0) {
            throw new IllegalArgumentException("days must be greater than zero");
        }
        if (isBlank(reason)) {
            throw new IllegalArgumentException("reason must not be blank");
        }
        this.id = id;
        this.employeeId = employeeId;
        this.days = days;
        this.reason = reason;
        this.status = LeaveStatus.DRAFT;
    }

    public String getId() {
        return id;
    }

    public String getEmployeeId() {
        return employeeId;
    }

    public int getDays() {
        return days;
    }

    public String getReason() {
        return reason;
    }

    public LeaveStatus getStatus() {
        return status;
    }

    void setStatus(LeaveStatus status) {
        this.status = Objects.requireNonNull(status, "status must not be null");
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}

