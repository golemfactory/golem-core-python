BEGIN;

CREATE SCHEMA tasks;
SET search_path TO tasks;

CREATE TABLE run (
    id              text PRIMARY KEY,
    app_session_id  text UNIQUE,
    created_ts      timestamp DEFAULT now()
);

CREATE TABLE results (
    id          serial,
    created_ts  timestamp DEFAULT now(),
    run_id      text NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    cnt         int NOT NULL CHECK (cnt >= 0)
);

CREATE TABLE allocation (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),              
    run_id      text NOT NULL REFERENCES run(id) ON DELETE CASCADE
);

CREATE TABLE demand (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),              
    run_id      text NOT NULL REFERENCES run(id) ON DELETE CASCADE
);

CREATE TABLE proposal (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),              
    demand_id   text NOT NULL REFERENCES demand(id) ON DELETE CASCADE,
    data        json
);

CREATE TABLE agreement (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),              
    proposal_id text NOT NULL REFERENCES proposal(id) ON DELETE CASCADE
);

CREATE TABLE activity (
    id              text PRIMARY KEY,
    created_ts      timestamp DEFAULT now(),              
    agreement_id    text NOT NULL REFERENCES agreement(id) ON DELETE CASCADE,
    status          text NOT NULL DEFAULT 'NEW',
    stop_reason     text
);

CREATE TABLE batch (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),              
    activity_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE
);

CREATE TABLE debit_note (
    id          text PRIMARY KEY,
    created_ts  timestamp DEFAULT now(),
    activity_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
    amount      numeric
);


CREATE FUNCTION tasks.demands(run_id text) RETURNS TABLE (demand_id text)
LANGUAGE SQL
AS $fff$
    SELECT  id
    FROM    tasks.demand
    WHERE   run_id = $1;
$fff$
;

CREATE FUNCTION tasks.proposals(run_id text) RETURNS TABLE (demand_id text, proposal_id text)
LANGUAGE SQL
AS $fff$
    SELECT  d.demand_id, p.id
    FROM    tasks.proposal      p
    NATURAL
    JOIN    tasks.demands($1)   d
$fff$
;

CREATE FUNCTION tasks.agreements(run_id text) RETURNS TABLE (demand_id text, proposal_id text, agreement_id text)
LANGUAGE SQL
AS $fff$
    SELECT  p.demand_id, p.proposal_id, a.id
    FROM    tasks.agreement     a
    NATURAL
    JOIN    tasks.proposals($1) p
$fff$
;

CREATE FUNCTION tasks.activities(run_id text) RETURNS TABLE (demand_id text, proposal_id text, agreement_id text, activity_id text)
LANGUAGE SQL
AS $fff$
    SELECT  ag.demand_id, ag.proposal_id, ag.agreement_id, ac.id
    FROM    tasks.activity          ac
    NATURAL
    JOIN    tasks.agreements($1)    ag
$fff$
;

CREATE FUNCTION tasks.batches(run_id text) RETURNS TABLE (demand_id text, proposal_id text, agreement_id text, activity_id text, batch_id text)
LANGUAGE SQL
AS $fff$
    SELECT  a.demand_id, a.proposal_id, a.agreement_id, a.activity_id, b.id
    FROM    tasks.batch          b
    NATURAL
    JOIN    tasks.activities($1) a
$fff$
;

CREATE FUNCTION tasks.debit_notes(run_id text) RETURNS TABLE (demand_id text, proposal_id text, agreement_id text, activity_id text, debit_note_id text)
LANGUAGE SQL
AS $fff$
    SELECT  a.demand_id, a.proposal_id, a.agreement_id, a.activity_id, d.id
    FROM    tasks.debit_note     d
    NATURAL
    JOIN    tasks.activities($1) a
$fff$
;

COMMIT;
