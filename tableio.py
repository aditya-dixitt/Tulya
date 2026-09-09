"""Table IO shim. Uses Parquet when pyarrow/fastparquet is installed (your
machines), falls back to CSV otherwise (this sandbox). Call sites never change."""
import pathlib, pandas as pd

def _has_parquet():
    try:
        import pyarrow  # noqa
        return True
    except Exception:
        try:
            import fastparquet  # noqa
            return True
        except Exception:
            return False

PARQUET = _has_parquet()
EXT = ".parquet" if PARQUET else ".csv"

def path(base):
    """base is given without extension, e.g. out/records"""
    return pathlib.Path(str(base) + EXT)

def write(df, base):
    p = path(base)
    df.to_parquet(p, index=False) if PARQUET else df.to_csv(p, index=False)
    return p

def read(base):
    p = path(base)
    return pd.read_parquet(p) if PARQUET else pd.read_csv(p)
