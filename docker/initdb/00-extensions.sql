-- Runs before 10-kb.sql.gz (the init directory executes in lexical order).
--
-- The dump declares prose.chunks.embedding as public.vector(384) but cannot
-- create the extension itself: extensions live in public, which the dump's
-- --schema=football --schema=prose excludes. Without this the restore fails
-- with "type public.vector does not exist".
CREATE EXTENSION IF NOT EXISTS vector;
