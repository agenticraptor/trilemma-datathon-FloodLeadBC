-- 011_nws_products (Stage 3 part 2): official NWS text products (IEM archive) and their VTEC records. New tables.
CREATE TABLE nws_products (
    product_id     bigserial   PRIMARY KEY,
    pil            text        NOT NULL,           -- 'FLWSEW', 'FLSSEW', 'FFASEW'
    wfo            text        NOT NULL,
    wmo            text        NOT NULL,           -- 'WGUS46 KSEW 141950'
    issued_at      timestamptz NOT NULL,
    text           text        NOT NULL,
    raw_object_id  bigint REFERENCES raw_objects (raw_object_id),
    UNIQUE (pil, wmo, issued_at)
);

CREATE TABLE nws_vtec (
    product_id     bigint      NOT NULL REFERENCES nws_products (product_id),
    seq            int         NOT NULL,           -- order within the product
    segment        int         NOT NULL,
    issued_at      timestamptz NOT NULL,
    product_class  text        NOT NULL,
    action         text        NOT NULL,           -- NEW, CON, EXT, EXA, EXB, UPG, CAN, EXP, COR, ROU
    office         text        NOT NULL,
    phenomena      text        NOT NULL,           -- FL (river flood), FA (areal flood), FF (flash flood), HY
    significance   text        NOT NULL,           -- W warning, A watch, Y advisory, S statement
    etn            int         NOT NULL,
    vtec_begin     timestamptz,
    vtec_end       timestamptz,
    nwsli          text,                           -- H-VTEC forecast point, e.g. 'NRKW1'
    severity       text,                           -- 1 minor, 2 moderate, 3 major, N, 0, U
    cause          text,
    flood_begin    timestamptz,
    flood_crest    timestamptz,
    flood_end      timestamptz,
    record         text,
    forecast_crest_ft real,                        -- from the segment text ("crest near 148.9 feet")
    observed_crest_ft real,                        -- "crested at ... feet"
    observed_stage_ft real,                        -- "the stage was 144.0 feet"
    PRIMARY KEY (product_id, seq)
);
CREATE INDEX nws_vtec_point ON nws_vtec (nwsli, issued_at);
