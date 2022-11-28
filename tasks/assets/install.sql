BEGIN;

CREATE SCHEMA tasks;
SET search_path TO tasks;

CREATE TABLE run (
    id      text PRIMARY KEY,
    start   timestamp DEFAULT now()
);

CREATE TABLE proposal (
    id      text PRIMARY KEY,
    run_id  text NOT NULL REFERENCES run(id),
    initial bool NOT NULL,
    data    json
);

CREATE TABLE agreement (
    id          text PRIMARY KEY,
    proposal_id text NOT NULL REFERENCES proposal(id),
    status      text NOT NULL
);

CREATE TABLE activity (
    id              text PRIMARY KEY,
    agreement_id    text NOT NULL REFERENCES agreement(id),
    status          text NOT NULL
);


COMMIT;
