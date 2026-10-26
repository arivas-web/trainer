import numpy as np
import pytest

from app.mapping import streams
from app.mapping.fit import parse_fit
from app.mapping.gpx_tcx import haversine_cum, parse_gpx, parse_tcx
from tests.fixtures.fit_builder import START, build_run_fit, build_swim_fit


def test_parse_run_fit_summary_laps_streams() -> None:
    p = parse_fit(build_run_fit(seconds=600, speed=3.0, hr=150))
    s = p.summary
    assert s["sport"] == "running"
    assert s["start_time_utc"] == START
    assert s["tz_offset_min"] == 120
    assert s["distance_m"] == pytest.approx(1800)
    assert s["avg_speed"] == pytest.approx(3.0)  # derivada de distancia / tiempo en movimiento
    assert s["avg_cadence"] == pytest.approx(170)  # 85 por pierna -> 170 pasos/min
    assert s["has_power"] and s["has_streams"] and not s["has_running_dynamics"]
    assert [lap["start_offset_s"] for lap in p.laps] == [0, 300]
    assert len(p.streams["time"]) == 601
    assert p.streams["lat"][0] == pytest.approx(42.2, abs=1e-6)
    assert np.all(p.streams["cadence"] == 170)
    assert p.external_id == f"fit:123456:{int(START.timestamp())}"


def test_parse_swim_fit_lengths() -> None:
    p = parse_fit(build_swim_fit(lengths=8, pool=25))
    assert p.summary["sport"] == "swimming"
    assert p.summary["sub_sport"] == "lap_swimming"
    assert len(p.lengths) == 8
    assert p.lengths[0]["stroke_type"] == "freestyle"
    assert p.lengths[0]["pool_length_m"] == 25


def test_parse_fit_rejects_garbage() -> None:
    with pytest.raises(Exception):  # noqa: B017 - fitdecode lanza tipos distintos
        parse_fit(b"esto no es un fit")


def test_stream_codec_roundtrip_with_nan() -> None:
    data = {
        "time": np.arange(5, dtype=float),
        "hr": np.array([120, np.nan, 130, 131, 132.5]),
    }
    channels, n, blob = streams.encode(data)
    out = streams.decode(channels, n, blob)
    assert channels == ["time", "hr"] and n == 5
    np.testing.assert_allclose(out["hr"], data["hr"], equal_nan=True)


def test_stream_codec_rejects_ragged() -> None:
    with pytest.raises(ValueError):
        streams.encode({"time": np.arange(3.0), "hr": np.arange(2.0)})


GPX = b"""<?xml version="1.0"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"
 xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
<trk><type>running</type><trkseg>
<trkpt lat="42.0" lon="-8.0"><ele>10</ele><time>2026-01-01T08:00:00Z</time>
 <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>140</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
<trkpt lat="42.001" lon="-8.0"><ele>15</ele><time>2026-01-01T08:00:40Z</time>
 <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>150</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
</trkseg></trk></gpx>"""


def test_parse_gpx() -> None:
    p = parse_gpx(GPX)
    assert p.summary["sport"] == "running"
    assert p.summary["distance_m"] == pytest.approx(111.2, abs=0.5)  # 0,001º de latitud
    assert p.summary["duration_s"] == 40
    assert p.summary["avg_hr"] == 145
    assert p.summary["elev_gain_m"] == 5


TCX = b"""<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Biking"><Lap><Track>
<Trackpoint><Time>2026-01-01T08:00:00Z</Time><DistanceMeters>0</DistanceMeters>
 <HeartRateBpm><Value>120</Value></HeartRateBpm><Cadence>80</Cadence></Trackpoint>
<Trackpoint><Time>2026-01-01T08:01:00Z</Time><DistanceMeters>500</DistanceMeters>
 <HeartRateBpm><Value>130</Value></HeartRateBpm><Cadence>90</Cadence></Trackpoint>
</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""


def test_parse_tcx() -> None:
    p = parse_tcx(TCX)
    assert p.summary["sport"] == "biking"
    assert p.summary["distance_m"] == 500
    assert p.summary["max_hr"] == 130
    assert list(p.streams["cadence"]) == [80, 90]


def test_haversine_one_degree_lat() -> None:
    d = haversine_cum(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
    assert d[-1] == pytest.approx(111_195, rel=1e-3)
