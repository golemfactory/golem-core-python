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
    agreement_id    text NOT NULL REFERENCES agreement(id),
    status          text NOT NULL DEFAULT 'NEW'
);

CREATE TABLE batch (
    id          text PRIMARY KEY,
    activity_id text NOT NULL REFERENCES activity(id)
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

COMMIT;
