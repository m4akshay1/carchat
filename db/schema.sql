-- CarChat schema.
-- One table holds everything. The app never queries it directly:
-- each role gets its own view, and its own database user that can
-- SELECT from that view and nothing else (grants are in scripts/seed.py).

DROP VIEW IF EXISTS inventory_view;
DROP VIEW IF EXISTS inventory_gm_view;
DROP TABLE IF EXISTS vehicles;

CREATE TABLE vehicles (
    stock_number   text    PRIMARY KEY,
    vin            text    NOT NULL UNIQUE CHECK (length(vin) = 17),
    year           integer NOT NULL CHECK (year BETWEEN 2015 AND 2027),
    make           text    NOT NULL,
    model          text    NOT NULL,
    trim           text,
    body_style     text    NOT NULL CHECK (body_style IN ('truck', 'suv', 'sedan', 'van', 'coupe')),
    drive          text    NOT NULL CHECK (drive IN ('FWD', 'RWD', 'AWD', '4WD')),
    fuel_type      text    NOT NULL CHECK (fuel_type IN ('gasoline', 'diesel', 'hybrid', 'plug-in hybrid', 'electric')),
    combined_mpg   integer,
    condition      text    NOT NULL CHECK (condition IN ('new', 'used', 'certified')),
    mileage        integer NOT NULL CHECK (mileage >= 0),
    exterior_color text    NOT NULL,
    list_price     integer NOT NULL CHECK (list_price > 0),
    cost           integer NOT NULL CHECK (cost > 0),
    date_in_stock  date    NOT NULL,
    status         text    NOT NULL CHECK (status IN ('available', 'sale_pending', 'sold')),
    store          text    NOT NULL
);

-- Sales manager view: everything except cost.
CREATE VIEW inventory_view AS
SELECT stock_number, vin, year, make, model, trim, body_style, drive, fuel_type,
       combined_mpg, condition, mileage, exterior_color, list_price,
       date_in_stock, (CURRENT_DATE - date_in_stock) AS days_on_lot,
       status, store
FROM vehicles;

-- General manager view: the same columns plus cost.
CREATE VIEW inventory_gm_view AS
SELECT stock_number, vin, year, make, model, trim, body_style, drive, fuel_type,
       combined_mpg, condition, mileage, exterior_color, list_price, cost,
       date_in_stock, (CURRENT_DATE - date_in_stock) AS days_on_lot,
       status, store
FROM vehicles;
