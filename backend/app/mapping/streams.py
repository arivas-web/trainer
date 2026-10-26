"""Codificación compacta de streams: cada canal como float32 little-endian, concatenados en el
orden de `channels` y comprimidos con zlib. NaN = muestra sin dato."""

import zlib

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Canales canónicos (unidades SI salvo indicación).
CHANNELS = (
    "time",  # s desde el inicio
    "distance",  # m
    "lat",  # grados
    "lon",  # grados
    "altitude",  # m
    "hr",  # ppm
    "speed",  # m/s
    "cadence",  # pasos/min (carrera) o rpm (bici)
    "power",  # W
    "temperature",  # ºC
    "ground_contact_time",  # ms
    "vertical_oscillation",  # mm
    "stride_length",  # m
    "vertical_ratio",  # %
)


def encode(streams: dict[str, FloatArray]) -> tuple[list[str], int, bytes]:
    channels = [c for c in CHANNELS if c in streams]
    n = len(streams["time"]) if "time" in streams else 0
    for c in channels:
        if len(streams[c]) != n:
            raise ValueError(f"El canal {c} tiene {len(streams[c])} muestras y time {n}")
    buf = b"".join(np.asarray(streams[c], dtype="<f4").tobytes() for c in channels)
    return channels, n, zlib.compress(buf, level=6)


def decode(channels: list[str], n_samples: int, data: bytes) -> dict[str, FloatArray]:
    raw = np.frombuffer(zlib.decompress(data), dtype="<f4")
    if raw.size != n_samples * len(channels):
        raise ValueError("Stream corrupto: tamaño inesperado")
    return {
        c: raw[i * n_samples : (i + 1) * n_samples].astype(np.float64)
        for i, c in enumerate(channels)
    }
