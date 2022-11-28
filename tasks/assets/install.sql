BEGIN;

CREATE SCHEMA tasks;
SET search_path TO tasks;

CREATE TABLE run (
    id      text PRIMARY KEY,
    start   timestamp DEFAULT now()
);

CREATE TABLE demand (
    id      text PRIMARY KEY,
    run_id  text NOT NULL REFERENCES run(id)
);

CREATE TABLE proposal (
    id          text PRIMARY KEY,
    demand_id   text NOT NULL REFERENCES demand(id),
    data        json
);

CREATE TABLE agreement (
    id          text PRIMARY KEY,
    proposal_id text NOT NULL REFERENCES proposal(id)
);

CREATE TABLE activity (
    id              text PRIMARY KEY,
    agreement_id    text NOT NULL REFERENCES agreement(id)
);

CREATE TABLE batch (
    id          text PRIMARY KEY,
    activity_id text NOT NULL REFERENCES activity(id)
);


COMMIT;
