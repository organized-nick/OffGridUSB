"""Minimal <= 200B Packet Chunker stub wrapping ESP32Protocol."""

from __future__ import annotations

from typing import Any, Dict, List
from emyrge.mesh.esp32_protocol import ESP32Protocol


class PacketChunker:
    """Thin wrapper routing compact text into <= 200B `[M<id>:<seq>/<total>]` frames."""

    _counter: int = 100

    @classmethod
    def chunk_reply(cls, text: str, max_bytes: int = 200) -> List[Dict[str, Any]]:
        cls._counter += 1
        pkts = ESP32Protocol.chunk_message(cls._counter, text, max_bytes=max_bytes)
        return [
            {
                **p.to_dict(),
                "frame": p.raw_frame,
                "ack": ESP32Protocol.format_ack(p.msg_id, p.seq, "ACK"),
                "status": "ACKED",
            }
            for p in pkts
        ]
