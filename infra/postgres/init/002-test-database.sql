CREATE DATABASE supportpilot_test OWNER supportpilot_migrator;
GRANT CONNECT ON DATABASE supportpilot_test TO supportpilot_app;

\connect supportpilot_test

CREATE EXTENSION IF NOT EXISTS vector;
GRANT USAGE ON SCHEMA public TO supportpilot_app;

