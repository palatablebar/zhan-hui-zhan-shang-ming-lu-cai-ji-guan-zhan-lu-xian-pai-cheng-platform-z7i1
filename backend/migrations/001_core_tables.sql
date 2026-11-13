-- 核心表结构参考（MySQL 8.0 语法，运行时不执行；建表由 SQLAlchemy create_all 完成）

CREATE TABLE users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(160) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    org             VARCHAR(120),
    created_at      DATETIME     NOT NULL
);

CREATE TABLE exhibitors (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    name                  VARCHAR(120) NOT NULL,
    hall                  VARCHAR(8)   NOT NULL,
    booth_no              VARCHAR(16)  NOT NULL,
    row_no                INT NOT NULL DEFAULT 0,
    col_no                INT NOT NULL DEFAULT 0,
    category              VARCHAR(24) NOT NULL,
    target_industry       VARCHAR(24) NOT NULL DEFAULT 'general',
    contact_name          VARCHAR(60),
    contact_title         VARCHAR(40),
    contact_phone         VARCHAR(32),
    priority              VARCHAR(4)  NOT NULL DEFAULT 'P2',
    dwell_min             INT NOT NULL DEFAULT 6,
    appointment_at        DATETIME,
    appointment_day       INT,
    appointment_start_min INT,
    appointment_end_min   INT,
    note                  TEXT,
    seed_key              VARCHAR(120) UNIQUE,
    created_at            DATETIME NOT NULL,
    updated_at            DATETIME NOT NULL,
    CONSTRAINT uq_exhibitors_hall_booth UNIQUE (hall, booth_no)
);

CREATE TABLE sessions (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    title      VARCHAR(160) NOT NULL,
    hall       VARCHAR(24)  NOT NULL,
    start_at   DATETIME NOT NULL,
    end_at     DATETIME NOT NULL,
    day        INT NOT NULL DEFAULT 1,
    speaker    VARCHAR(80),
    track      VARCHAR(40),
    note       TEXT,
    seed_key   VARCHAR(120) UNIQUE,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_sessions_title_start UNIQUE (title, start_at)
);

CREATE TABLE route_runs (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    run_no         VARCHAR(40) NOT NULL UNIQUE,
    day_count      INT NOT NULL DEFAULT 2,
    status         VARCHAR(20) NOT NULL,
    operator_email VARCHAR(160) NOT NULL,
    trigger        VARCHAR(20) NOT NULL DEFAULT 'manual',
    params         JSON,
    metrics        JSON,
    log_text       TEXT,
    seed_key       VARCHAR(120) UNIQUE,
    started_at     DATETIME NOT NULL,
    finished_at    DATETIME
);

CREATE TABLE visits (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    run_id         INT NOT NULL,
    exhibitor_id   INT NOT NULL,
    day            INT NOT NULL DEFAULT 1,
    seq            INT NOT NULL DEFAULT 0,
    eta_min        INT NOT NULL DEFAULT 0,
    eta_at         DATETIME,
    dwell_min      INT NOT NULL DEFAULT 6,
    walk_before_m  DOUBLE NOT NULL DEFAULT 0,
    conflict       BOOL NOT NULL DEFAULT FALSE,
    conflict_kind  VARCHAR(20),
    conflict_note  TEXT,
    status         VARCHAR(16) NOT NULL DEFAULT 'planned',
    reviewer       VARCHAR(160),
    review_note    TEXT,
    created_at     DATETIME NOT NULL,
    updated_at     DATETIME NOT NULL,
    CONSTRAINT uq_visits_run_exhibitor UNIQUE (run_id, exhibitor_id),
    CONSTRAINT fk_visits_run FOREIGN KEY (run_id) REFERENCES route_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_visits_exhibitor FOREIGN KEY (exhibitor_id) REFERENCES exhibitors(id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    actor_email    VARCHAR(160) NOT NULL,
    actor_role     VARCHAR(20)  NOT NULL,
    action         VARCHAR(64)  NOT NULL,
    entity         VARCHAR(40)  NOT NULL,
    entity_id      VARCHAR(64),
    detail         JSON,
    layer          VARCHAR(16) NOT NULL DEFAULT 'domain',
    ip             VARCHAR(64),
    seed_key       VARCHAR(120) UNIQUE,
    created_at     DATETIME NOT NULL
);
