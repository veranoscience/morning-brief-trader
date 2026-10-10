-- Morning Brief Trader — schéma de la base "trading"
-- Données 100 % fictives (portefeuilles, traders, limites). Les cours peuvent être réels (yfinance).

CREATE TABLE IF NOT EXISTS traders (
    trader_id   TEXT PRIMARY KEY,
    nom         TEXT NOT NULL,
    desk        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    ticker       TEXT PRIMARY KEY,
    nom          TEXT NOT NULL,
    classe_actif TEXT NOT NULL,          -- Action, ETF
    secteur      TEXT NOT NULL,
    devise       TEXT NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS positions (
    position_id  SERIAL PRIMARY KEY,
    trader_id    TEXT NOT NULL REFERENCES traders(trader_id),
    ticker       TEXT NOT NULL REFERENCES instruments(ticker),
    quantite     NUMERIC NOT NULL,       -- négatif = position vendeuse (short)
    prix_moyen   NUMERIC NOT NULL,       -- prix moyen d'entrée
    ouverte_le   DATE NOT NULL
);

-- Types de limites :
--   exposition_brute  : somme des |valeurs de marché| <= valeur_limite (USD)
--   exposition_secteur: |valeur de marché nette du secteur| <= valeur_limite (USD), perimetre = secteur
--   concentration     : part max d'une ligne dans l'exposition brute <= valeur_limite (en %)
--   perte_journaliere : perte du jour <= valeur_limite (USD)
CREATE TABLE IF NOT EXISTS limites (
    limite_id     SERIAL PRIMARY KEY,
    trader_id     TEXT NOT NULL REFERENCES traders(trader_id),
    type_limite   TEXT NOT NULL CHECK (type_limite IN
                  ('exposition_brute', 'exposition_secteur', 'concentration', 'perte_journaliere')),
    perimetre     TEXT,                  -- secteur concerné, sinon NULL
    valeur_limite NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS cours (
    ticker      TEXT NOT NULL REFERENCES instruments(ticker),
    date_cours  DATE NOT NULL,
    cloture     NUMERIC NOT NULL,
    source      TEXT NOT NULL,           -- 'yfinance' ou 'simulation'
    PRIMARY KEY (ticker, date_cours)
);

-- Gouvernance : un rôle en LECTURE SEULE pour Claude (connecteur MCP).
-- Claude peut lire les positions et les cours, jamais les modifier.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brief_reader') THEN
        CREATE ROLE brief_reader LOGIN PASSWORD 'lecture_seule';
    END IF;
END $$;

GRANT CONNECT ON DATABASE trading TO brief_reader;
GRANT USAGE ON SCHEMA public TO brief_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO brief_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO brief_reader;
ALTER ROLE brief_reader SET default_transaction_read_only = on;
