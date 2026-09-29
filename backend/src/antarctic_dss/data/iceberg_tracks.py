import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from datetime import datetime
from typing import Optional

STATS_COLUMNS = ["date", "date_gap", "disp", "flags", "lat", "lon", "mask", "size", "vel_angle"]

def load_stats_track(csv_path: Path) -> pd.DataFrame:
    """
    Load a single iceberg CSV file.
    
    Args:
        csv_path (Path): Path to the CSV file.
        
    Returns:
        pd.DataFrame: A DataFrame containing the iceberg track data.
    """
    df = pd.read_csv(csv_path, names=STATS_COLUMNS, sep=r'\s+')
    df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%j')
    df['iceberg_id'] = csv_path.stem
    df = df[(df['lat'] < 0) & (df['lat'] > -90) & (df['lon'].abs() <= 180)]
    return df

def load_all_stats_tracks(stats_dir: Path) -> pd.DataFrame:
    """
    Load all CSV files in a directory and concatenate them into a single DataFrame.
    
    Args:
        stats_dir (Path): Path to the directory containing the CSV files.
        
    Returns:
        pd.DataFrame: A DataFrame containing all iceberg track data sorted by iceberg_id and datetime.
    """
    csv_paths = list(stats_dir.glob("*.csv"))
    if not csv_paths:
        return pd.DataFrame()
    dfs = [load_stats_track(p) for p in csv_paths]
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df = combined_df.sort_values(by=['iceberg_id', 'date']).reset_index(drop=True)
    return combined_df

def load_consolidated_track(csv_path: Path) -> pd.DataFrame:
    """
    Load a consolidated DB track and extract relevant data.
    
    Args:
        csv_path (Path): Path to the consolidated CSV file.
        
    Returns:
        pd.DataFrame: A DataFrame with extracted and computed data.
    """
    df = pd.read_csv(csv_path)
    
    # Find best lat/lon by preferring nic, then ascat, then qscat
    lat_col = 'nic_lat' if 'nic_lat' in df.columns else ('ascat_lat' if 'ascat_lat' in df.columns else ('qscat_lat' if 'qscat_lat' in df.columns else df.filter(like='lat').columns[0]))
    lon_col = 'nic_lon' if 'nic_lon' in df.columns else ('ascat_lon' if 'ascat_lon' in df.columns else ('qscat_lon' if 'qscat_lon' in df.columns else df.filter(like='lon').columns[0]))
    
    df['best_lat'] = df[lat_col]
    df['best_lon'] = df[lon_col]
    
    if 'size_1' in df.columns and 'size_2' in df.columns:
        df['area_km2'] = df['size_1'] * df['size_2'] * (1.852**2)
    return df

def compute_displacements_epsg3031(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Convert DataFrame to GeoDataFrame, project to EPSG:3031, and compute displacements.
    
    Args:
        df (pd.DataFrame): DataFrame containing 'lat' and 'lon' columns.
        
    Returns:
        gpd.GeoDataFrame: GeoDataFrame with added displacement metrics.
    """
    lat_col = 'best_lat' if 'best_lat' in df.columns else 'lat'
    lon_col = 'best_lon' if 'best_lon' in df.columns else 'lon'
    
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs="EPSG:4326")
    gdf = gdf.to_crs("EPSG:3031")
    
    gdf['x_3031'] = gdf.geometry.x
    gdf['y_3031'] = gdf.geometry.y
    
    gdf['dx'] = gdf.groupby('iceberg_id')['x_3031'].diff()
    gdf['dy'] = gdf.groupby('iceberg_id')['y_3031'].diff()
    gdf['displacement_km'] = np.sqrt(gdf['dx']**2 + gdf['dy']**2) / 1000.0
    
    return gdf

def get_track_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a summary for each iceberg track.
    
    Args:
        df (pd.DataFrame): DataFrame containing iceberg tracks.
        
    Returns:
        pd.DataFrame: Summary DataFrame per iceberg.
    """
    summary = df.groupby('iceberg_id').agg(
        first_date=('date', 'min'),
        last_date=('date', 'max'),
        n_observations=('date', 'count'),
        mean_displacement_km=('displacement_km', 'mean'),
        total_distance_km=('displacement_km', 'sum')
    ).reset_index()
    summary['track_duration_days'] = (summary['last_date'] - summary['first_date']).dt.days
    return summary

# Position sources in the BYU/NIC consolidated database, in order of preference. NIC positions
# are daily (interpolated between analyst fixes) and smooth; scatterometer sources repeat the
# last fix on days without a new detection, which would create fake zero-displacement targets.
CONSOLIDATED_SOURCES = ['nic', 'ascat', 'oscat', 'qscat', 'seawinds', 'nscat', 'ers', 'sass']

# Daily drift above this is treated as a bad fix (observed extremes are ~20-40 km/day).
MAX_DRIFT_KM_PER_DAY = 80.0
# Real fixes can be several days apart (NIC analysts fix positions every few days).
MAX_GAP_DAYS = 7

# Grounding heuristic: net drift below GROUNDED_MAX_KM_PER_DAY over at least GROUNDED_WINDOW_DAYS,
# in water shallower than GROUNDED_MAX_DEPTH_M (large tabular icebergs draft up to ~300-500 m).
GROUNDED_WINDOW_DAYS = 7
GROUNDED_MAX_KM_PER_DAY = 0.5
GROUNDED_MAX_DEPTH_M = 600.0

def load_consolidated_daily_track(csv_path: Path, year: Optional[int] = None, years: Optional[list] = None) -> pd.DataFrame:
    """
    Load a consolidated-DB track as one clean daily position series.

    Keeps only real observed fixes (the source's `_3` flag == 1): NIC's daily positions are
    straight-line interpolations between analyst fixes, so day-to-day displacements between
    interpolated rows don't reflect that day's forcing. Picks a single position source per
    track (the preferred source with the most fixes) so consecutive positions are comparable,
    drops empty (0, 0) rows and repeated stale fixes, and carries size measurements forward.

    Returns columns: iceberg_id, timestamp, lat, lon, source, size_km2.
    """
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['date'].astype(str), format='%Y%j', errors='coerce')
    years = list(years or ([year] if year is not None else []))
    if years:
        # Keep the following year too, so the last day's target can be computed.
        df = df[df['timestamp'].dt.year.isin(set(years) | {max(years) + 1})]

    def valid(src):
        lat, lon = df[f'{src}_1'], df[f'{src}_2']
        ok = (lat < -30) & (lat >= -90) & (lon.abs() <= 180) & ~((lat == 0) & (lon == 0))
        flag = f'{src}_3'
        return ok & (df[flag] == 1) if flag in df.columns else ok

    available = [s for s in CONSOLIDATED_SOURCES if f'{s}_1' in df.columns and f'{s}_2' in df.columns]
    empty = pd.DataFrame(columns=['iceberg_id', 'timestamp', 'lat', 'lon', 'source', 'size_km2'])
    if not available:
        return empty
    counts = {s: int(valid(s).sum()) for s in available}
    # Prefer NIC when it has reasonable coverage, otherwise the source with the most fixes.
    nic_count = counts.get('nic', 0)
    source = 'nic' if nic_count > 0 and nic_count >= 0.5 * max(counts.values()) else max(counts, key=counts.get)
    if counts[source] == 0:
        return empty

    if 'size_1' in df.columns and 'size_2' in df.columns:
        size = (df['size_1'] * df['size_2']).where(lambda v: v > 0)
        size_km2 = (size * 1.852 ** 2).ffill().bfill()
    else:
        size_km2 = pd.Series(np.nan, index=df.index)

    track = pd.DataFrame({
        'iceberg_id': csv_path.stem,
        'timestamp': df['timestamp'],
        'lat': df[f'{source}_1'],
        'lon': df[f'{source}_2'],
        'source': source,
        'size_km2': size_km2,
    })[valid(source) & df['timestamp'].notna()]

    track = track.sort_values('timestamp').drop_duplicates('timestamp')
    # Drop stale repeats: identical position to the previous fix means no new observation.
    stale = (track['lat'].diff() == 0) & (track['lon'].diff() == 0)
    return track[~stale].reset_index(drop=True)

def build_displacement_targets(track: pd.DataFrame) -> pd.DataFrame:
    """
    Add per-day displacement targets (target_dx east, target_dy north, metres per 24 h)
    from each position to the next one of the same iceberg.

    East/north metres match the frame of wind/current (u, v) components and the physics
    baseline. Gaps longer than MAX_GAP_DAYS and implausible jumps are dropped.
    """
    from antarctic_dss.utils.geo import east_north_displacement_m

    df = track.sort_values(['iceberg_id', 'timestamp']).copy()
    nxt = df.groupby('iceberg_id')[['timestamp', 'lat', 'lon']].shift(-1)
    gap_days = (nxt['timestamp'] - df['timestamp']).dt.total_seconds() / 86400.0
    dx, dy = east_north_displacement_m(df['lat'].values, df['lon'].values, nxt['lat'].values, nxt['lon'].values)

    df['gap_days'] = gap_days
    df['target_dx'] = dx / gap_days
    df['target_dy'] = dy / gap_days
    speed_km_day = np.hypot(df['target_dx'], df['target_dy']) / 1000.0
    keep = gap_days.between(1, MAX_GAP_DAYS) & (speed_km_day <= MAX_DRIFT_KM_PER_DAY)
    return df[keep].reset_index(drop=True)

def flag_grounded(df: pd.DataFrame) -> pd.DataFrame:
    """Add a boolean `grounded` column: slow net drift over >= a week in shallow water.

    For each fix, the net drift rate is measured to the first fix at least
    GROUNDED_WINDOW_DAYS later (same iceberg). Depth comes from the model bathymetry;
    without it, only the drift criterion is used.
    """
    from antarctic_dss.utils.geo import haversine_km_array
    from antarctic_dss.routing.bathymetry import depth_at_points

    df = df.sort_values(['iceberg_id', 'timestamp']).reset_index(drop=True)
    later = df[['iceberg_id', 'timestamp', 'lat', 'lon']].copy()
    probe = df[['iceberg_id', 'timestamp']].copy()
    probe['probe_time'] = probe['timestamp'] + pd.Timedelta(days=GROUNDED_WINDOW_DAYS)
    matched = pd.merge_asof(
        probe.sort_values('probe_time'), later.rename(columns={'timestamp': 'later_time'}).sort_values('later_time'),
        left_on='probe_time', right_on='later_time', by='iceberg_id', direction='forward',
        tolerance=pd.Timedelta(days=3 * GROUNDED_WINDOW_DAYS)).sort_index()
    span_days = (matched['later_time'] - df['timestamp']).dt.total_seconds() / 86400.0
    net_km = haversine_km_array(df['lat'], df['lon'], matched['lat'], matched['lon'])
    slow = (net_km / span_days) < GROUNDED_MAX_KM_PER_DAY

    depth = depth_at_points(df['lat'].values, df['lon'].values)
    shallow = depth < GROUNDED_MAX_DEPTH_M if depth is not None else True
    df['grounded'] = (slow & shallow).fillna(False).astype(bool)
    return df

def load_consolidated_training_tracks(consolidated_dir: Path, year: Optional[int] = None, years: Optional[list] = None) -> pd.DataFrame:
    """Load all consolidated tracks with displacement targets, optionally restricted to given year(s)."""
    years = list(years or ([year] if year is not None else []))
    frames = []
    for path in sorted(consolidated_dir.glob('*.csv')):
        try:
            track = load_consolidated_daily_track(path, years=years)
        except Exception as e:
            print(f"Skipping {path.name}: {e}")
            continue
        if len(track) > 1:
            frames.append(build_displacement_targets(track))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = flag_grounded(df)
    if years:
        df = df[df['timestamp'].dt.year.isin(years)]
    return df.reset_index(drop=True)
