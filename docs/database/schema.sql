CREATE DATABASE IF NOT EXISTS agentharness
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE agentharness;

create table agentsession
(
    id                  int auto_increment
        primary key,
    provider_type       varchar(80)                          not null,
    workspace_path      varchar(1000)                        not null,
    external_session_id varchar(120)                         null,
    task_count          int                                  not null,
    status              enum ('ACTIVE', 'ROTATED', 'FAILED') not null,
    created_at          datetime                             not null,
    updated_at          datetime                             not null,
    rotated_at          datetime                             null
);

create index ix_agentsession_status
    on agentsession (status);

create table agentworker
(
    id                int auto_increment
        primary key,
    worker_key        varchar(50)                   not null,
    name              varchar(120)                  not null,
    role              varchar(80)                   not null,
    provider_type     varchar(80)                   not null,
    status            varchar(20) default 'OFFLINE' not null,
    last_heartbeat_at datetime                      null,
    constraint uq_agentworker_worker_key
        unique (worker_key)
);

create index ix_agentworker_status
    on agentworker (status);

create table task
(
    id             int auto_increment
        primary key,
    title          varchar(200)                                                                                                                                                                                                                                                                              not null,
    description    text                                                                                                                                                                                                                                                                                      not null,
    workspace_path varchar(1000)                                                                                                                                                                                                                                                                             null,
    status         enum ('REQUIREMENT_DRAFT', 'PLAN_REQUESTED', 'PLAN_READY', 'PLAN_CONFIRMED', 'IMPLEMENTING', 'IMPLEMENT_DONE', 'REVIEW_REQUESTED', 'REVIEW_DONE', 'FIX_REQUIRED', 'FIXING', 'FIX_DONE', 'RECHECK_REQUESTED', 'RECHECK_DONE', 'ACCEPTANCE_READY', 'ACCEPTANCE_PASSED', 'ARCHIVED', 'DONE') not null,
    mode           varchar(32) default 'secretary'                                                                                                                                                                                                                                                           not null,
    created_at     datetime                                                                                                                                                                                                                                                                                  not null,
    updated_at     datetime                                                                                                                                                                                                                                                                                  not null,
    archived_at    datetime                                                                                                                                                                                                                                                                                  null
);

create table agentrun
(
    id                 int auto_increment
        primary key,
    task_id            int                                               null,
    worker_id          int                                               null,
    run_type           varchar(100)                                      not null,
    status             enum ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED') not null,
    input_payload      text                                              null,
    output_payload     text                                              null,
    error_message      text                                              null,
    started_at         datetime                                          null,
    finished_at        datetime                                          null,
    provider_type      varchar(80) default 'local_cli'                   not null,
    external_thread_id varchar(120)                                      null,
    external_turn_id   varchar(120)                                      null,
    command_display    varchar(500)                                      null,
    cwd                varchar(1000)                                     null,
    exit_code          int                                               null,
    stderr             text                                              null,
    created_at         datetime                                          null,
    agent_session_id   int                                               null,
    constraint agentrun_ibfk_1
        foreign key (task_id) references task (id),
    constraint agentrun_ibfk_2
        foreign key (worker_id) references agentworker (id)
);

create index ix_agentrun_run_type
    on agentrun (run_type);

create index ix_agentrun_status
    on agentrun (status);

create index ix_agentrun_task_id
    on agentrun (task_id);

create index ix_agentrun_worker_id
    on agentrun (worker_id);

create table commandrun
(
    id              int auto_increment
        primary key,
    task_id         int                                                  null,
    command_key     varchar(100)                                         not null,
    command_display varchar(500)                                         not null,
    cwd             varchar(1000)                                        not null,
    exit_code       int                                                  null,
    stdout          text                                                 null,
    stderr          text                                                 null,
    duration_ms     int                                                  null,
    status          enum ('RUNNING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT') not null,
    created_at      datetime                                             not null,
    constraint commandrun_ibfk_1
        foreign key (task_id) references task (id)
);

create index ix_commandrun_command_key
    on commandrun (command_key);

create index ix_commandrun_status
    on commandrun (status);

create index ix_commandrun_task_id
    on commandrun (task_id);

create table reviewitem
(
    id          int auto_increment
        primary key,
    task_id     int                                       null,
    severity    enum ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN') not null,
    title       varchar(300)                              not null,
    description varchar(255)                              null,
    status      enum ('OPEN', 'RESOLVED', 'WONT_FIX')     not null,
    source_file varchar(1000)                             null,
    created_at  datetime                                  not null,
    constraint reviewitem_ibfk_1
        foreign key (task_id) references task (id)
);

create index ix_reviewitem_severity
    on reviewitem (severity);

create index ix_reviewitem_status
    on reviewitem (status);

create index ix_reviewitem_task_id
    on reviewitem (task_id);

create index ix_task_status
    on task (status);

create index ix_task_title
    on task (title);

create table taskevent
(
    id          int auto_increment
        primary key,
    task_id     int                                                                                                                                                                                                                                                                                       not null,
    event_type  varchar(100)                                                                                                                                                                                                                                                                              not null,
    from_status enum ('REQUIREMENT_DRAFT', 'PLAN_REQUESTED', 'PLAN_READY', 'PLAN_CONFIRMED', 'IMPLEMENTING', 'IMPLEMENT_DONE', 'REVIEW_REQUESTED', 'REVIEW_DONE', 'FIX_REQUIRED', 'FIXING', 'FIX_DONE', 'RECHECK_REQUESTED', 'RECHECK_DONE', 'ACCEPTANCE_READY', 'ACCEPTANCE_PASSED', 'ARCHIVED', 'DONE') null,
    to_status   enum ('REQUIREMENT_DRAFT', 'PLAN_REQUESTED', 'PLAN_READY', 'PLAN_CONFIRMED', 'IMPLEMENTING', 'IMPLEMENT_DONE', 'REVIEW_REQUESTED', 'REVIEW_DONE', 'FIX_REQUIRED', 'FIXING', 'FIX_DONE', 'RECHECK_REQUESTED', 'RECHECK_DONE', 'ACCEPTANCE_READY', 'ACCEPTANCE_PASSED', 'ARCHIVED', 'DONE') null,
    message     text                                                                                                                                                                                                                                                                                      null,
    created_by  varchar(100)                                                                                                                                                                                                                                                                              not null,
    created_at  datetime                                                                                                                                                                                                                                                                                  not null,
    constraint taskevent_ibfk_1
        foreign key (task_id) references task (id)
);

create index ix_taskevent_event_type
    on taskevent (event_type);

create index ix_taskevent_task_id
    on taskevent (task_id);

