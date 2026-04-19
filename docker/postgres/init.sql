-- Habilita extensão pgvector (necessária para embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- Confirma instalação
DO $$
BEGIN
    RAISE NOTICE 'pgvector extension ativada com sucesso!';
END
$$;
