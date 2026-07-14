DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supportpilot_migrator') THEN
        CREATE ROLE supportpilot_migrator LOGIN PASSWORD 'local_migrator_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supportpilot_app') THEN
        CREATE ROLE supportpilot_app LOGIN PASSWORD 'local_app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE supportpilot TO supportpilot_migrator, supportpilot_app;
GRANT CREATE, USAGE ON SCHEMA public TO supportpilot_migrator;
GRANT USAGE ON SCHEMA public TO supportpilot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE supportpilot_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO supportpilot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE supportpilot_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO supportpilot_app;

CREATE EXTENSION IF NOT EXISTS vector;

