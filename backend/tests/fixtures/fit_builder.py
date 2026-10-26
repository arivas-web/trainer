"""Genera FIT sintéticos (con fit-tool) para los tests: sin datos personales."""

from datetime import UTC, datetime, timedelta

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.length_message import LengthMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    FileType,
    LengthType,
    Manufacturer,
    Sport,
    SubSport,
    SwimStroke,
)

START = datetime(2026, 10, 20, 7, 0, 0, tzinfo=UTC)


def _ms(dt: datetime) -> int:
    return round(dt.timestamp() * 1000)


def build_run_fit(
    seconds: int = 600,
    speed: float = 3.0,
    hr: int = 150,
    start: datetime = START,
    with_power: bool = True,
    serial: int = 123456,
) -> bytes:
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.GARMIN.value
    fid.product = 0
    fid.serial_number = serial
    fid.time_created = _ms(start)
    b.add(fid)
    for i in range(seconds + 1):
        r = RecordMessage()
        r.timestamp = _ms(start + timedelta(seconds=i))
        r.position_lat = 42.2 + i * 1e-5
        r.position_long = -8.7
        r.distance = speed * i
        r.enhanced_speed = speed
        r.enhanced_altitude = 10.0 + (i % 60) * 0.1
        r.heart_rate = hr
        r.cadence = 85
        if with_power:
            r.power = 250
        b.add(r)
    end = start + timedelta(seconds=seconds)
    half = seconds // 2
    for a, z in [(0, half), (half, seconds)]:
        lap = LapMessage()
        lap.timestamp = _ms(start + timedelta(seconds=z))
        lap.start_time = _ms(start + timedelta(seconds=a))
        lap.total_elapsed_time = z - a
        lap.total_timer_time = z - a
        lap.total_distance = speed * (z - a)
        lap.avg_heart_rate = hr
        b.add(lap)
    s = SessionMessage()
    s.timestamp = _ms(end)
    s.start_time = _ms(start)
    s.sport = Sport.RUNNING
    s.sub_sport = SubSport.GENERIC
    s.total_elapsed_time = seconds
    s.total_timer_time = seconds
    s.total_distance = speed * seconds
    s.avg_heart_rate = hr
    s.max_heart_rate = hr + 10
    s.avg_cadence = 85
    s.total_ascent = 12
    b.add(s)
    a = ActivityMessage()
    a.timestamp = _ms(end)
    a.local_timestamp = round((end + timedelta(hours=2)).timestamp()) - 631065600
    a.num_sessions = 1
    b.add(a)
    return b.build().to_bytes()


def build_swim_fit(lengths: int = 8, pool: float = 25.0, start: datetime = START) -> bytes:
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.GARMIN.value
    fid.serial_number = 999
    fid.time_created = _ms(start)
    b.add(fid)
    t = start
    for _ in range(lengths):
        ln = LengthMessage()
        ln.timestamp = _ms(t + timedelta(seconds=30))
        ln.start_time = _ms(t)
        ln.total_elapsed_time = 30
        ln.total_timer_time = 30
        ln.length_type = LengthType.ACTIVE
        ln.swim_stroke = SwimStroke.FREESTYLE
        ln.total_strokes = 18
        b.add(ln)
        t += timedelta(seconds=30)
    s = SessionMessage()
    s.timestamp = _ms(t)
    s.start_time = _ms(start)
    s.sport = Sport.SWIMMING
    s.sub_sport = SubSport.LAP_SWIMMING
    s.total_elapsed_time = lengths * 30
    s.total_timer_time = lengths * 30
    s.total_distance = lengths * pool
    s.pool_length = pool
    b.add(s)
    return b.build().to_bytes()
