"""ESP32 Thin-Client Serial and HTTP Protocol Contracts for Project eMyrge.

Implements F-08 (Thin-Client Protocol Contract) and F-41 (ESP32 Gateway Relay).
Strictly adheres to <= 200 bytes packet frames ([M<id>:<seq>/<total>]),
sliding-window ACK tracking, UART 115200 8N1 parsing, and ESP32-CAM JPEG validation.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from emyrge.core.config import ThinClientProtocolError


class ESP32CommandType(str, Enum):
    """ESP32 command types."""

    AI = "AI"
    CALC = "CALC"
    LOG = "LOG"
    PING = "PING"
    STATUS = "STATUS"
    CAMERA = "CAMERA"
    TIER = "TIER"
    HELP = "HELP"
    QUERY = "QUERY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ESP32Request:
    """Structured request parsed from serial UART or HTTP query."""

    device_id: str = "esp32_default"
    msg_id: int = 1
    cmd_type: ESP32CommandType = ESP32CommandType.UNKNOWN
    command: str = ""
    args: str = ""
    raw_text: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "msg_id": self.msg_id,
            "cmd_type": self.cmd_type.value,
            "command": self.command,
            "args": self.args,
            "raw_text": self.raw_text,
            "timestamp": self.timestamp,
        }


@dataclass
class ESP32Packet:
    """Sequenced and bounded packet strictly <= 200 UTF-8 bytes."""

    msg_id: int
    seq: int
    total: int
    payload: str
    raw_frame: str
    byte_length: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "seq": self.seq,
            "total": self.total,
            "payload": self.payload,
            "raw_frame": self.raw_frame,
            "byte_length": self.byte_length,
        }


@dataclass
class ESP32PacketAck:
    """Acknowledgment packet from ESP32 microcontroller or mesh radio."""

    msg_id: int
    seq: int  # -1 indicates ALL
    status: str = "ACK"  # "ACK" or "NACK"


@dataclass
class ESP32Telemetry:
    """Hardware health and connection telemetry from ESP32."""

    device_id: str
    battery_mv: int
    uptime_s: int
    free_heap_bytes: int
    wifi_rssi: Optional[int] = None
    tier: str = "Tier -1"


@dataclass
class ESP32CameraFrame:
    """JPEG image snapshot frame received from ESP32-CAM."""

    device_id: str
    timestamp: float
    image_bytes: bytes
    format: str = "jpeg"
    width: Optional[int] = None
    height: Optional[int] = None
    battery_mv: Optional[int] = None
    note: Optional[str] = None


class ESP32Protocol:
    """Parser and packetizer for ESP32 UART serial lines and mesh packets."""

    # Regex patterns for line commands
    ENVELOPE_PATTERN = re.compile(r"^(?:\[(?:DEV:(?P<dev>[^ \]]+)\s+)?REQ:(?P<req>\d+)\]\s*)?(?P<body>.+)$")
    ACK_PATTERN = re.compile(r"^\[(?P<status>ACK|NACK)\s+M(?P<id>\d+):(?P<seq>\d+|ALL)\]$", re.IGNORECASE)

    @classmethod
    def parse_command_line(cls, line: str, max_line_bytes: int = 200, strict_mtu: bool = True) -> ESP32Request:
        """Parses an inbound ASCII/UTF-8 serial line command into an ESP32Request.

        Enforces the <= 200 bytes MTU limit unless strict_mtu is False.
        """
        raw_bytes = line.encode("utf-8")
        if strict_mtu and len(raw_bytes) > max_line_bytes:
            raise ThinClientProtocolError(f"Serial frame exceeded {max_line_bytes}B limit ({len(raw_bytes)} bytes)")

        clean = line.strip().rstrip("\r\n")
        if not clean:
            return ESP32Request(raw_text=line)

        device_id = "esp32_default"
        msg_id = 1

        # Check for envelope: [DEV:<dev> REQ:<id>] or [REQ:<id>]
        env_match = cls.ENVELOPE_PATTERN.match(clean)
        body = clean
        if env_match:
            d = env_match.group("dev")
            r = env_match.group("req")
            if d:
                device_id = d
            if r:
                msg_id = int(r)
            body = env_match.group("body").strip()

        # Check syntax styles:
        # 1. CMD:<TYPE>[:<ARGS>] (case-insensitive prefix)
        if body[:4].upper() == "CMD:":
            parts = body[4:].split(":", 1)
            raw_cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""
            cmd_type = getattr(ESP32CommandType, raw_cmd, ESP32CommandType.UNKNOWN)
            return ESP32Request(
                device_id=device_id,
                msg_id=msg_id,
                cmd_type=cmd_type,
                command=raw_cmd,
                args=args,
                raw_text=line,
            )

        # 2. @ai, @calc, @log, @ping, @status
        if body.startswith("@"):
            parts = body[1:].split(" ", 1)
            raw_cmd = parts[0].upper()
            args = parts[1].strip() if len(parts) > 1 else ""
            cmd_type = getattr(ESP32CommandType, raw_cmd, ESP32CommandType.UNKNOWN)
            return ESP32Request(
                device_id=device_id,
                msg_id=msg_id,
                cmd_type=cmd_type,
                command=raw_cmd,
                args=args,
                raw_text=line,
            )

        # 3. Simple colon format: QUERY:<args>, PING, TIER, CALC:<args>
        if ":" in body:
            parts = body.split(":", 1)
            raw_cmd = parts[0].upper()
            args = parts[1].strip()
            cmd_type = getattr(ESP32CommandType, raw_cmd, ESP32CommandType.UNKNOWN)
            return ESP32Request(
                device_id=device_id,
                msg_id=msg_id,
                cmd_type=cmd_type,
                command=raw_cmd,
                args=args,
                raw_text=line,
            )

        # 4. Single-token command: PING, TIER, STATUS, HELP
        raw_cmd = body.upper()
        cmd_type = getattr(ESP32CommandType, raw_cmd, ESP32CommandType.UNKNOWN)
        return ESP32Request(
            device_id=device_id,
            msg_id=msg_id,
            cmd_type=cmd_type,
            command=raw_cmd,
            args="",
            raw_text=line,
        )

    @classmethod
    def chunk_message(cls, msg_id: int, text: str, max_bytes: int = 200) -> List[ESP32Packet]:
        """Splits an outbound message into sequenced packets where each packet's
        UTF-8 encoded raw_frame strictly satisfies len(raw_frame.encode('utf-8')) <= max_bytes.

        Framing: [M<id>:<seq>/<total>] <payload>
        Uses dynamic prefix reservation and UTF-8 multi-byte safe boundaries.
        """
        if not text:
            frame = f"[M{msg_id}:1/1] "
            b_len = len(frame.encode("utf-8"))
            return [ESP32Packet(msg_id=msg_id, seq=1, total=1, payload="", raw_frame=frame, byte_length=b_len)]

        # Two-pass convergence for prefix length
        # Conservative initial guess of total chunks
        est_prefix_overhead = len(f"[M{msg_id}:999/999] ".encode("utf-8"))
        est_avail = max(10, max_bytes - est_prefix_overhead)

        # Split text into candidate words
        words = text.split(" ")
        raw_chunks = cls._group_words_to_budget(words, est_avail)
        total_chunks = len(raw_chunks)

        # Refine if actual prefix format needs different budget
        prefix_sample = f"[M{msg_id}:{total_chunks}/{total_chunks}] "
        actual_prefix_bytes = len(prefix_sample.encode("utf-8"))
        refined_avail = max_bytes - actual_prefix_bytes

        if refined_avail != est_avail:
            raw_chunks = cls._group_words_to_budget(words, refined_avail)
            total_chunks = len(raw_chunks)

        # Build final packets and verify byte boundaries
        packets: List[ESP32Packet] = []
        for seq, payload in enumerate(raw_chunks, start=1):
            frame = f"[M{msg_id}:{seq}/{total_chunks}] {payload}"
            frame_bytes = frame.encode("utf-8")

            # Hard guarantee: if frame exceeds max_bytes, clamp payload safely
            if len(frame_bytes) > max_bytes:
                prefix = f"[M{msg_id}:{seq}/{total_chunks}] "
                avail = max_bytes - len(prefix.encode("utf-8"))
                safe_payload = cls._truncate_utf8(payload, avail)
                frame = f"{prefix}{safe_payload}"
                frame_bytes = frame.encode("utf-8")

            packets.append(
                ESP32Packet(
                    msg_id=msg_id,
                    seq=seq,
                    total=total_chunks,
                    payload=payload,
                    raw_frame=frame,
                    byte_length=len(frame_bytes),
                )
            )

        return packets

    @classmethod
    def _group_words_to_budget(cls, words: List[str], max_chunk_bytes: int) -> List[str]:
        """Groups words into chunks where each chunk's UTF-8 byte length <= max_chunk_bytes."""
        chunks: List[str] = []
        current: List[str] = []
        current_bytes = 0

        for w in words:
            w_bytes = len(w.encode("utf-8"))

            # If a single word is larger than the entire budget, force-split it
            if w_bytes > max_chunk_bytes:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    current_bytes = 0
                # Split large word into byte-bounded fragments
                subparts = cls._split_large_word(w, max_chunk_bytes)
                chunks.extend(subparts)
                continue

            space_overhead = 1 if current else 0
            if current_bytes + space_overhead + w_bytes > max_chunk_bytes and current:
                chunks.append(" ".join(current))
                current = [w]
                current_bytes = w_bytes
            else:
                current.append(w)
                current_bytes += space_overhead + w_bytes

        if current:
            chunks.append(" ".join(current))

        return chunks or [""]

    @classmethod
    def _split_large_word(cls, word: str, max_bytes: int) -> List[str]:
        """Safely splits a large single string into slices <= max_bytes without cutting code points."""
        subparts = []
        remaining = word
        while remaining:
            chunk = cls._truncate_utf8(remaining, max_bytes)
            if not chunk:
                break
            subparts.append(chunk)
            remaining = remaining[len(chunk):]
        return subparts

    @classmethod
    def _truncate_utf8(cls, text: str, max_bytes: int) -> str:
        """Truncates text to fit within max_bytes without breaking UTF-8 code points."""
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        truncated = encoded[:max_bytes]
        # Decode ignoring invalid trailing byte sequences
        return truncated.decode("utf-8", errors="ignore")

    @classmethod
    def format_serial_chunks(cls, msg_id: int, text: str, max_line_bytes: int = 180) -> List[str]:
        """Formats multi-line response as RSP:CHUNK:<seq>:<total>:<payload>\\n ending with RSP:END\\n.

        Each line satisfies <= 200 bytes.
        """
        packets = cls.chunk_message(msg_id, text, max_bytes=max_line_bytes)
        total = len(packets)
        lines = []
        for p in packets:
            line = f"RSP:CHUNK:{p.seq}:{total}:{p.payload}\n"
            lines.append(line)
        lines.append("RSP:END\n")
        return lines

    @classmethod
    def format_ack(cls, msg_id: int, seq: int, status: str = "ACK") -> str:
        """Formats an acknowledgment frame: [ACK M<id>:<seq>] or [ACK M<id>:ALL]."""
        seq_str = "ALL" if seq == -1 else str(seq)
        return f"[{status.upper()} M{msg_id}:{seq_str}]"

    @classmethod
    def parse_ack(cls, ack_line: str) -> Optional[ESP32PacketAck]:
        """Parses an incoming ACK/NACK frame string."""
        m = cls.ACK_PATTERN.match(ack_line.strip())
        if not m:
            return None
        st = m.group("status").upper()
        mid = int(m.group("id"))
        seq_val = m.group("seq")
        seq = -1 if seq_val.upper() == "ALL" else int(seq_val)
        return ESP32PacketAck(msg_id=mid, seq=seq, status=st)

    @classmethod
    def validate_camera_frame(cls, image_bytes: bytes, max_bytes: int = 2097152) -> Tuple[bool, Optional[str]]:
        """Validates ESP32-CAM binary JPEG snapshot:

        - Checks max size <= 2MB (2,097,152 bytes)
        - Verifies standard JPEG magic bytes (\\xff\\xd8\\xff)
        """
        if len(image_bytes) > max_bytes:
            return False, f"Payload exceeded maximum size of {max_bytes} bytes (received {len(image_bytes)} bytes)"
        if len(image_bytes) < 4:
            return False, "Payload too short to be a valid image"
        if not image_bytes.startswith(b"\xff\xd8\xff"):
            return False, "Invalid JPEG binary stream (missing 0xFFD8FF magic bytes)"
        return True, None


class ESP32TransmissionTracker:
    """Sliding-window state machine tracking pending frames and retransmissions."""

    def __init__(self, msg_id: int, packets: List[ESP32Packet], timeout_sec: float = 2.0):
        self.msg_id = msg_id
        self.packets: Dict[int, ESP32Packet] = {p.seq: p for p in packets}
        self.total = len(packets)
        self.acked_seqs: set[int] = set()
        self.last_sent: Dict[int, float] = {p.seq: time.time() for p in packets}
        self.timeout_sec = timeout_sec

    def record_ack(self, ack: ESP32PacketAck) -> bool:
        """Records an incoming ACK. Returns True if all packets are now acknowledged."""
        if ack.msg_id != self.msg_id:
            return False
        if ack.status.upper() == "ACK":
            if ack.seq == -1:  # ACK ALL
                self.acked_seqs = set(self.packets.keys())
            else:
                self.acked_seqs.add(ack.seq)
        return self.is_complete()

    def is_complete(self) -> bool:
        """Returns True if every sequence number has been acknowledged."""
        return set(self.packets.keys()).issubset(self.acked_seqs)

    def get_unacked_packets(self) -> List[ESP32Packet]:
        """Returns all packets that have not yet been acknowledged."""
        return [self.packets[seq] for seq in sorted(self.packets.keys()) if seq not in self.acked_seqs]

    def check_timeouts(self, now: Optional[float] = None) -> List[ESP32Packet]:
        """Identifies packets requiring retransmission due to elapsed timeout."""
        current_time = now or time.time()
        to_resend = []
        for seq, pkt in self.packets.items():
            if seq not in self.acked_seqs:
                if current_time - self.last_sent.get(seq, 0) >= self.timeout_sec:
                    to_resend.append(pkt)
                    self.last_sent[seq] = current_time
        return to_resend
