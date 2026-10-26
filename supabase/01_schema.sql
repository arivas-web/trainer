-- Pulse · esquema completo (GENERADO con `make schema-sql`; no editar a mano).
-- Pégalo entero en Supabase → SQL Editor → Run. Equivale a `make migrate`.

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 2c2f81dbba1b

CREATE TABLE ai_reports (
    id SERIAL NOT NULL, 
    week_start DATE NOT NULL, 
    model VARCHAR(80) NOT NULL, 
    payload_sent_json JSONB NOT NULL, 
    response_md TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_ai_reports PRIMARY KEY (id)
);

CREATE TABLE app_settings (
    key VARCHAR(80) NOT NULL, 
    value_json JSONB NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_app_settings PRIMARY KEY (key)
);

CREATE TABLE athlete_thresholds (
    id SERIAL NOT NULL, 
    effective_from DATE NOT NULL, 
    hr_max FLOAT, 
    hr_rest FLOAT, 
    lthr FLOAT, 
    threshold_pace_s_km FLOAT, 
    css_s_100m FLOAT, 
    ftp_w FLOAT, 
    running_ftp_w FLOAT, 
    weight_kg FLOAT, 
    source VARCHAR(20) NOT NULL, 
    notes TEXT, 
    CONSTRAINT pk_athlete_thresholds PRIMARY KEY (id), 
    CONSTRAINT uq_athlete_thresholds_effective_from UNIQUE (effective_from)
);

CREATE TABLE daily_load (
    date DATE NOT NULL, 
    load_total FLOAT NOT NULL, 
    load_by_sport_json JSONB, 
    ctl FLOAT, 
    atl FLOAT, 
    tsb FLOAT, 
    acwr FLOAT, 
    ramp_rate_7d FLOAT, 
    monotony_7d FLOAT, 
    strain_7d FLOAT, 
    inputs_hash VARCHAR(64), 
    CONSTRAINT pk_daily_load PRIMARY KEY (date)
);

CREATE TABLE daily_metrics (
    date DATE NOT NULL, 
    resting_hr FLOAT, 
    hrv_night_avg FLOAT, 
    hrv_weekly_avg FLOAT, 
    hrv_status VARCHAR(30), 
    sleep_total_s FLOAT, 
    sleep_deep_s FLOAT, 
    sleep_light_s FLOAT, 
    sleep_rem_s FLOAT, 
    sleep_awake_s FLOAT, 
    sleep_score FLOAT, 
    sleep_start_local TIMESTAMP WITH TIME ZONE, 
    sleep_end_local TIMESTAMP WITH TIME ZONE, 
    body_battery_max FLOAT, 
    body_battery_min FLOAT, 
    body_battery_charged FLOAT, 
    body_battery_drained FLOAT, 
    stress_avg FLOAT, 
    steps INTEGER, 
    active_kcal FLOAT, 
    readiness_score FLOAT, 
    readiness_factors_json JSONB, 
    vo2max_run FLOAT, 
    vo2max_bike FLOAT, 
    fitness_age FLOAT, 
    training_status VARCHAR(40), 
    acute_load FLOAT, 
    chronic_load FLOAT, 
    respiration_avg FLOAT, 
    spo2_avg FLOAT, 
    weight_kg FLOAT, 
    body_fat_pct FLOAT, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_daily_metrics PRIMARY KEY (date)
);

CREATE TABLE garmin_token (
    id SERIAL NOT NULL, 
    access_token_enc TEXT NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    obtained_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_garmin_token PRIMARY KEY (id)
);

CREATE TABLE gear (
    id SERIAL NOT NULL, 
    external_id VARCHAR(64), 
    name VARCHAR(120) NOT NULL, 
    type VARCHAR(20) NOT NULL, 
    initial_km FLOAT NOT NULL, 
    limit_km FLOAT, 
    retired BOOLEAN NOT NULL, 
    auto_assign_rule JSONB, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_gear PRIMARY KEY (id), 
    CONSTRAINT uq_gear_external_id UNIQUE (external_id)
);

CREATE TABLE goals (
    id SERIAL NOT NULL, 
    type VARCHAR(30) NOT NULL, 
    sport VARCHAR(40), 
    title VARCHAR(160) NOT NULL, 
    target_value FLOAT, 
    unit VARCHAR(20), 
    period VARCHAR(20), 
    deadline DATE, 
    achieved_at DATE, 
    CONSTRAINT pk_goals PRIMARY KEY (id)
);

CREATE TABLE insights (
    id SERIAL NOT NULL, 
    rule_id VARCHAR(80) NOT NULL, 
    date DATE NOT NULL, 
    severity VARCHAR(10) NOT NULL, 
    priority INTEGER NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    body TEXT, 
    evidence_json JSONB, 
    dismissed BOOLEAN NOT NULL, 
    CONSTRAINT pk_insights PRIMARY KEY (id)
);

CREATE TABLE raw_documents (
    id SERIAL NOT NULL, 
    kind VARCHAR(60) NOT NULL, 
    key VARCHAR(160) NOT NULL, 
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    payload JSONB NOT NULL, 
    CONSTRAINT pk_raw_documents PRIMARY KEY (id), 
    CONSTRAINT uq_raw_documents_kind_key UNIQUE (kind, key)
);

CREATE TABLE sync_jobs (
    id SERIAL NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    data_type VARCHAR(60) NOT NULL, 
    range_start DATE, 
    range_end DATE, 
    ref VARCHAR(80), 
    priority INTEGER NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    attempts INTEGER NOT NULL, 
    items INTEGER NOT NULL, 
    error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_sync_jobs PRIMARY KEY (id)
);

CREATE INDEX ix_sync_jobs_run_id ON sync_jobs (run_id);

CREATE INDEX ix_sync_jobs_status ON sync_jobs (status, priority, id);

CREATE TABLE sync_log (
    id SERIAL NOT NULL, 
    run_id VARCHAR(36), 
    at TIMESTAMP WITH TIME ZONE NOT NULL, 
    data_type VARCHAR(60) NOT NULL, 
    method VARCHAR(10) NOT NULL, 
    path VARCHAR(255) NOT NULL, 
    params_json JSONB, 
    status VARCHAR(10) NOT NULL, 
    http_code INTEGER, 
    items INTEGER, 
    error TEXT, 
    duration_ms FLOAT, 
    CONSTRAINT pk_sync_log PRIMARY KEY (id)
);

CREATE INDEX ix_sync_log_at ON sync_log (at);

CREATE INDEX ix_sync_log_run_id ON sync_log (run_id);

CREATE TABLE sync_state (
    data_type VARCHAR(60) NOT NULL, 
    synced_until DATE, 
    oldest_synced DATE, 
    last_run_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_sync_state PRIMARY KEY (data_type)
);

CREATE TABLE activities (
    id SERIAL NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    external_id VARCHAR(64) NOT NULL, 
    file_sha256 VARCHAR(64), 
    start_time_utc TIMESTAMP WITH TIME ZONE NOT NULL, 
    start_time_local TIMESTAMP WITH TIME ZONE, 
    tz_offset_min INTEGER, 
    sport VARCHAR(40) NOT NULL, 
    sub_sport VARCHAR(40), 
    name VARCHAR(200), 
    device VARCHAR(80), 
    distance_m FLOAT, 
    duration_s FLOAT, 
    moving_s FLOAT, 
    elev_gain_m FLOAT, 
    elev_loss_m FLOAT, 
    avg_hr FLOAT, 
    max_hr FLOAT, 
    avg_speed FLOAT, 
    max_speed FLOAT, 
    avg_cadence FLOAT, 
    avg_power FLOAT, 
    max_power FLOAT, 
    normalized_power FLOAT, 
    aerobic_te FLOAT, 
    anaerobic_te FLOAT, 
    garmin_training_load FLOAT, 
    vo2max FLOAT, 
    calories FLOAT, 
    avg_temp_c FLOAT, 
    weather_json JSONB, 
    gear_id INTEGER, 
    has_streams BOOLEAN NOT NULL, 
    has_power BOOLEAN NOT NULL, 
    has_running_dynamics BOOLEAN NOT NULL, 
    fit_storage_key VARCHAR(255), 
    is_race BOOLEAN NOT NULL, 
    is_trail_override BOOLEAN, 
    excluded_from_analytics BOOLEAN NOT NULL, 
    rpe INTEGER, 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_activities PRIMARY KEY (id), 
    CONSTRAINT fk_activities_gear_id_gear FOREIGN KEY(gear_id) REFERENCES gear (id) ON DELETE SET NULL, 
    CONSTRAINT uq_activities_source_external_id UNIQUE (source, external_id)
);

CREATE INDEX ix_activities_file_sha256 ON activities (file_sha256);

CREATE INDEX ix_activities_sport_start ON activities (sport, start_time_utc);

CREATE INDEX ix_activities_start_time_utc ON activities (start_time_utc);

CREATE TABLE activity_streams (
    activity_id INTEGER NOT NULL, 
    n_samples INTEGER NOT NULL, 
    channels JSONB NOT NULL, 
    data BYTEA NOT NULL, 
    schema_version INTEGER NOT NULL, 
    CONSTRAINT pk_activity_streams PRIMARY KEY (activity_id), 
    CONSTRAINT fk_activity_streams_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE
);

CREATE TABLE best_efforts (
    id SERIAL NOT NULL, 
    activity_id INTEGER NOT NULL, 
    sport VARCHAR(40) NOT NULL, 
    kind VARCHAR(10) NOT NULL, 
    target FLOAT NOT NULL, 
    value FLOAT NOT NULL, 
    start_offset_s FLOAT, 
    date DATE NOT NULL, 
    CONSTRAINT pk_best_efforts PRIMARY KEY (id), 
    CONSTRAINT fk_best_efforts_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE, 
    CONSTRAINT uq_best_efforts_activity_target UNIQUE (activity_id, kind, target)
);

CREATE INDEX ix_best_efforts_rank ON best_efforts (sport, kind, target, value);

CREATE TABLE computed_activity_metrics (
    activity_id INTEGER NOT NULL, 
    inputs_hash VARCHAR(64) NOT NULL, 
    algo_version INTEGER NOT NULL, 
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    load_value FLOAT, 
    load_method VARCHAR(20), 
    trimp FLOAT, 
    hrtss FLOAT, 
    rtss FLOAT, 
    tss_power FLOAT, 
    intensity_factor FLOAT, 
    gap_avg_speed FLOAT, 
    efficiency_factor FLOAT, 
    decoupling_pct FLOAT, 
    hr_drift_pct FLOAT, 
    vam_m_h FLOAT, 
    walk_pct FLOAT, 
    is_trail BOOLEAN, 
    pace_at_hr_json JSONB, 
    zone_time_json JSONB, 
    extra_json JSONB, 
    CONSTRAINT pk_computed_activity_metrics PRIMARY KEY (activity_id), 
    CONSTRAINT fk_computed_activity_metrics_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE
);

CREATE TABLE laps (
    id SERIAL NOT NULL, 
    activity_id INTEGER NOT NULL, 
    idx INTEGER NOT NULL, 
    start_offset_s FLOAT, 
    duration_s FLOAT, 
    moving_s FLOAT, 
    distance_m FLOAT, 
    avg_speed FLOAT, 
    avg_hr FLOAT, 
    max_hr FLOAT, 
    avg_cadence FLOAT, 
    avg_power FLOAT, 
    elev_gain_m FLOAT, 
    elev_loss_m FLOAT, 
    intensity VARCHAR(20), 
    swim_stroke VARCHAR(20), 
    num_lengths INTEGER, 
    total_strokes INTEGER, 
    CONSTRAINT pk_laps PRIMARY KEY (id), 
    CONSTRAINT fk_laps_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE, 
    CONSTRAINT uq_laps_activity_idx UNIQUE (activity_id, idx)
);

CREATE TABLE personal_records (
    id SERIAL NOT NULL, 
    sport VARCHAR(40) NOT NULL, 
    kind VARCHAR(10) NOT NULL, 
    target FLOAT NOT NULL, 
    value FLOAT NOT NULL, 
    activity_id INTEGER, 
    date DATE NOT NULL, 
    source VARCHAR(20) NOT NULL, 
    CONSTRAINT pk_personal_records PRIMARY KEY (id), 
    CONSTRAINT fk_personal_records_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE SET NULL
);

CREATE TABLE races (
    id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    date DATE, 
    distance_m FLOAT, 
    format VARCHAR(30) NOT NULL, 
    target_time_s FLOAT, 
    priority VARCHAR(1) NOT NULL, 
    result_activity_id INTEGER, 
    notes TEXT, 
    CONSTRAINT pk_races PRIMARY KEY (id), 
    CONSTRAINT fk_races_result_activity_id_activities FOREIGN KEY(result_activity_id) REFERENCES activities (id) ON DELETE SET NULL
);

CREATE TABLE swim_lengths (
    id SERIAL NOT NULL, 
    activity_id INTEGER NOT NULL, 
    lap_idx INTEGER, 
    idx INTEGER NOT NULL, 
    start_offset_s FLOAT, 
    duration_s FLOAT, 
    length_type VARCHAR(10), 
    stroke_type VARCHAR(20), 
    strokes INTEGER, 
    pool_length_m FLOAT, 
    CONSTRAINT pk_swim_lengths PRIMARY KEY (id), 
    CONSTRAINT fk_swim_lengths_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE
);

CREATE INDEX ix_swim_lengths_activity ON swim_lengths (activity_id, idx);

ALTER TABLE "ai_reports" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "app_settings" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "athlete_thresholds" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "daily_load" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "daily_metrics" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "garmin_token" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "gear" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "goals" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "insights" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "raw_documents" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "sync_jobs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "sync_log" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "sync_state" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "activities" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "activity_streams" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "best_efforts" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "computed_activity_metrics" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "laps" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "personal_records" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "races" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "swim_lengths" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "alembic_version" ENABLE ROW LEVEL SECURITY;

INSERT INTO alembic_version (version_num) VALUES ('2c2f81dbba1b') RETURNING alembic_version.version_num;

COMMIT;

