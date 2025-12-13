import json
import asyncio
import threading
import time
import random
import argparse
import os
import sys
import socket
from datetime import datetime
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, asdict
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse
import cantools

from Drivers.BaseDriver import CANMessage, CANBaudRate
from Drivers.CANable_Driver import CANableDriver


# ============================================================================
# Helper Functions
# ============================================================================

def get_local_ip() -> str:
    """Get the local IPv4 address of this machine."""
    try:
        # Create a socket and connect to an external address
        # This doesn't actually send data, just determines the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        # Fallback: try to get from hostname
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return local_ip
        except Exception:
            return "127.0.0.1"


# ============================================================================
# DBC Manager (for decoding CAN messages)
# ============================================================================

class DBCManager:
    """
    Manages DBC file loading and CAN message decoding using cantools.
    """
    
    def __init__(self):
        self._database = None
        self._loaded = False
        self._message_count = 0
    
    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._database is not None
    
    @property
    def message_count(self) -> int:
        return self._message_count
    
    def load_dbc(self, content: str) -> tuple[bool, str]:
        """
        Load a DBC file from string content.
        Returns (success, message).
        """
        if cantools is None:
            return False, "cantools not installed"
        
        try:
            # Explicitly specify DBC format
            self._database = cantools.database.load_string(content, database_format='dbc')
            self._message_count = len(self._database.messages)
            self._loaded = True
            
            # Debug: print loaded messages
            print(f"✓ DBC loaded with {self._message_count} messages:")
            for msg in self._database.messages:
                ext_str = " (extended)" if msg.is_extended_frame else ""
                print(f"   0x{msg.frame_id:X}{ext_str}: {msg.name}")
            
            return True, f"Loaded {self._message_count} messages"
        except Exception as e:
            self._database = None
            self._loaded = False
            self._message_count = 0
            import traceback
            traceback.print_exc()
            return False, f"Failed to parse DBC: {str(e)}"
    
    def unload(self):
        """Unload the current DBC database."""
        self._database = None
        self._loaded = False
        self._message_count = 0
    
    def decode_message(self, frame_id: int, data: bytes, is_extended: bool = False) -> Optional[Dict]:
        """
        Decode a CAN message using the loaded DBC.
        Returns dict with message_name and signals, or None if not found.
        
        For 29-bit extended IDs, we try both the raw ID and with the extended flag bit.
        """
        if not self.is_loaded:
            return None
        
        if not data or len(data) == 0:
            return None
        
        try:
            # Try to find the message - cantools may store extended IDs with bit 31 set
            message = None
            lookup_id = frame_id
            
            try:
                message = self._database.get_message_by_frame_id(frame_id)
            except KeyError:
                # If extended frame, try with the 0x80000000 flag that some DBC files use
                if is_extended:
                    try:
                        message = self._database.get_message_by_frame_id(frame_id | 0x80000000)
                        lookup_id = frame_id | 0x80000000
                    except KeyError:
                        pass
            
            if message is None:
                return None
            
            # Ensure data is long enough for the message
            if len(data) < message.length:
                # Pad with zeros if needed
                data = data + bytes(message.length - len(data))
            
            # First decode with raw values to get numeric data
            decoded_raw = self._database.decode_message(lookup_id, data, decode_choices=False)
            
            # Try to decode with choices (enum names) - may fail for some signals
            try:
                decoded_choices = self._database.decode_message(lookup_id, data, decode_choices=True)
            except Exception:
                decoded_choices = decoded_raw
            
            signals = []
            for signal in message.signals:
                raw_value = decoded_raw.get(signal.name)
                choice_value = decoded_choices.get(signal.name)
                
                # Format the value nicely
                if isinstance(raw_value, float):
                    raw_value = round(raw_value, 2)
                
                # If the signal has choices and we got a named value, use it
                if signal.choices and choice_value is not None and choice_value != raw_value:
                    # choice_value is the enum name (string)
                    display_value = str(choice_value)
                elif signal.choices and raw_value is not None:
                    # Try to look up the choice name manually
                    choice_name = signal.choices.get(int(raw_value) if isinstance(raw_value, (int, float)) else raw_value)
                    if choice_name:
                        display_value = choice_name
                    else:
                        display_value = raw_value
                else:
                    display_value = raw_value
                
                signals.append({
                    "name": signal.name,
                    "value": display_value,
                    "unit": signal.unit or ""
                })
            
            return {
                "message_name": message.name,
                "signals": signals
            }
        except KeyError:
            # Message ID not found in DBC
            return None
        except Exception as e:
            # Decoding error - print for debugging but don't crash
            print(f"  DBC decode error for 0x{frame_id:X}: {type(e).__name__}: {e}")
            return None
        except KeyError:
            # Message ID not found in DBC
            return None
        except Exception as e:
            # Decoding error - print for debugging but don't crash
            print(f"  DBC decode error for 0x{frame_id:X}: {type(e).__name__}: {e}")
            return None
    
    def get_status(self) -> Dict:
        """Get DBC manager status."""
        return {
            "loaded": self.is_loaded,
            "message_count": self._message_count
        }


# Global DBC manager instance
dbc_manager = DBCManager()


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class CANMessageJSON:
    """JSON-serializable CAN message format for API responses."""
    id: int
    data: List[int]
    timestamp: float
    is_extended: bool = False
    is_remote: bool = False
    is_error: bool = False
    dlc: int = 0
    
    def to_dict(self) -> dict:
        # Try to decode using DBC if loaded
        try:
            decoded = dbc_manager.decode_message(self.id, bytes(self.data), self.is_extended)
        except Exception as e:
            print(f"  to_dict decode error: {e}")
            decoded = None
        
        result = {
            "id": self.id,
            "id_hex": f"0x{self.id:X}",
            "timestamp": self.timestamp,
            "dlc": self.dlc
        }
        
        if decoded:
            # Decoded message - include name and signals
            result["message_name"] = decoded["message_name"]
            result["signals"] = decoded["signals"]
            result["data_hex"] = None  # Not needed for decoded messages
        else:
            # Unknown message - include raw data
            result["message_name"] = None
            result["signals"] = None
            result["data_hex"] = " ".join(f"{b:02X}" for b in self.data)
        
        return result
    
    @classmethod
    def from_can_message(cls, msg: CANMessage) -> "CANMessageJSON":
        return cls(
            id=msg.id,
            data=list(msg.data),
            timestamp=msg.timestamp,
            is_extended=msg.is_extended,
            is_remote=msg.is_remote,
            is_error=msg.is_error,
            dlc=msg.dlc
        )


# ============================================================================
# CAN Bus Simulator (Test Mode)
# ============================================================================

class CANSimulator:
    """
    Simulates CAN bus traffic for testing without hardware.
    Generates realistic CAN messages with common automotive patterns.
    """
    
    # Common automotive CAN message IDs and their simulated data patterns
    SIMULATED_MESSAGES = [
        # Engine RPM (ID 0x0C0) - varies between 800-6000 RPM
        {"id": 0x0C0, "name": "Engine RPM", "pattern": "rpm"},
        # Vehicle Speed (ID 0x0B0) - varies between 0-120 mph
        {"id": 0x0B0, "name": "Vehicle Speed", "pattern": "speed"},
        # Throttle Position (ID 0x0D0) - varies between 0-100%
        {"id": 0x0D0, "name": "Throttle Position", "pattern": "throttle"},
        # Coolant Temperature (ID 0x0E0) - varies between 60-100°C
        {"id": 0x0E0, "name": "Coolant Temp", "pattern": "temperature"},
        # Brake Pressure (ID 0x1A0) - varies during braking events
        {"id": 0x1A0, "name": "Brake Pressure", "pattern": "brake"},
        # Steering Angle (ID 0x1B0) - varies with turning
        {"id": 0x1B0, "name": "Steering Angle", "pattern": "steering"},
        # Battery Voltage (ID 0x1C0) - relatively stable around 12-14V
        {"id": 0x1C0, "name": "Battery Voltage", "pattern": "voltage"},
        # Fuel Level (ID 0x1D0) - slowly decreases
        {"id": 0x1D0, "name": "Fuel Level", "pattern": "fuel"},
    ]
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._message_callback: Optional[Callable[[CANMessage], None]] = None
        self._tx_queue: deque = deque(maxlen=100)
        self._rx_buffer: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
        
        # Simulation state
        self._rpm = 800
        self._speed = 0
        self._throttle = 0
        self._temp = 70
        self._brake = 0
        self._steering = 0
        self._fuel = 75
        self._voltage = 12.6
        
        print("✓ CAN Simulator initialized (Test Mode)")
    
    def start(self, callback: Optional[Callable[[CANMessage], None]] = None):
        """Start the simulator."""
        if self._running:
            return
        
        self._running = True
        self._message_callback = callback
        self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self._thread.start()
        print("✓ CAN Simulator started - generating fake traffic")
    
    def stop(self):
        """Stop the simulator."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("✓ CAN Simulator stopped")
    
    def send_message(self, can_id: int, data: bytes, 
                     is_extended: bool = False) -> bool:
        """Simulate sending a message (adds to TX queue for echo)."""
        msg = CANMessage(
            id=can_id,
            data=data,
            timestamp=time.time(),
            is_extended=is_extended,
            dlc=len(data)
        )
        
        with self._lock:
            self._tx_queue.append(msg)
        
        print(f"  [SIM TX] ID: 0x{can_id:03X} Data: {data.hex()}")
        
        # Echo back after a short delay (simulating loopback)
        threading.Timer(0.05, self._echo_message, args=[msg]).start()
        return True
    
    def _echo_message(self, msg: CANMessage):
        """Echo transmitted message back as if received on bus."""
        with self._lock:
            self._rx_buffer.append(msg)
        
        if self._message_callback:
            self._message_callback(msg)
    
    def read_message(self, timeout: float = 1.0) -> Optional[CANMessage]:
        """Read a message from the buffer."""
        with self._lock:
            if self._rx_buffer:
                return self._rx_buffer.popleft()
        return None
    
    def _simulation_loop(self):
        """Generate simulated CAN messages."""
        while self._running:
            try:
                # Update simulation state
                self._update_simulation_state()
                
                # Generate messages for each simulated ECU
                for msg_def in self.SIMULATED_MESSAGES:
                    if not self._running:
                        break
                    
                    data = self._generate_message_data(msg_def["pattern"])
                    msg = CANMessage(
                        id=msg_def["id"],
                        data=data,
                        timestamp=time.time(),
                        is_extended=False,
                        dlc=len(data)
                    )
                    
                    with self._lock:
                        self._rx_buffer.append(msg)
                    
                    if self._message_callback:
                        self._message_callback(msg)
                    
                    # Small delay between messages
                    time.sleep(0.01)
                
                # Wait before next cycle (simulating ~50ms message cycle)
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Simulation error: {e}")
                time.sleep(0.1)
    
    def _update_simulation_state(self):
        """Update simulation values to create realistic patterns."""
        # Simulate driving behavior
        if random.random() < 0.1:  # 10% chance to change throttle
            self._throttle = max(0, min(100, self._throttle + random.randint(-20, 20)))
        
        # RPM follows throttle
        target_rpm = 800 + (self._throttle * 50)
        self._rpm += (target_rpm - self._rpm) * 0.1
        
        # Speed follows RPM/throttle
        target_speed = self._throttle * 1.2
        self._speed += (target_speed - self._speed) * 0.05
        
        # Temperature slowly increases then stabilizes
        if self._temp < 90:
            self._temp += random.uniform(0, 0.1)
        
        # Brake when throttle is low and speed is high
        if self._throttle < 10 and self._speed > 20:
            self._brake = min(100, self._brake + 10)
        else:
            self._brake = max(0, self._brake - 5)
        
        # Steering varies randomly
        self._steering += random.uniform(-5, 5)
        self._steering = max(-45, min(45, self._steering))
        
        # Fuel slowly decreases
        self._fuel = max(0, self._fuel - 0.001)
        
        # Voltage varies slightly
        self._voltage = 12.0 + random.uniform(0, 2) + (self._rpm / 6000)
    
    def _generate_message_data(self, pattern: str) -> bytes:
        """Generate realistic data for a message pattern."""
        if pattern == "rpm":
            rpm_val = int(self._rpm)
            return bytes([
                (rpm_val >> 8) & 0xFF,
                rpm_val & 0xFF,
                random.randint(0, 255),
                random.randint(0, 255),
                0, 0, 0, 0
            ])
        
        elif pattern == "speed":
            speed_val = int(self._speed * 10)  # 0.1 km/h resolution
            return bytes([
                (speed_val >> 8) & 0xFF,
                speed_val & 0xFF,
                0, 0, 0, 0, 0, 0
            ])
        
        elif pattern == "throttle":
            return bytes([
                int(self._throttle * 2.55),  # 0-255 for 0-100%
                0, 0, 0, 0, 0, 0, 0
            ])
        
        elif pattern == "temperature":
            temp_val = int(self._temp + 40)  # Offset by 40
            return bytes([temp_val, 0, 0, 0, 0, 0, 0, 0])
        
        elif pattern == "brake":
            return bytes([
                int(self._brake * 2.55),
                0, 0, 0, 0, 0, 0, 0
            ])
        
        elif pattern == "steering":
            angle = int((self._steering + 180) * 10)  # -180 to +180 degrees
            return bytes([
                (angle >> 8) & 0xFF,
                angle & 0xFF,
                0, 0, 0, 0, 0, 0
            ])
        
        elif pattern == "voltage":
            voltage_val = int(self._voltage * 10)
            return bytes([voltage_val, 0, 0, 0, 0, 0, 0, 0])
        
        elif pattern == "fuel":
            return bytes([
                int(self._fuel * 2.55),
                0, 0, 0, 0, 0, 0, 0
            ])
        
        else:
            return bytes([random.randint(0, 255) for _ in range(8)])


# ============================================================================
# CAN Bus Manager (Abstracts Hardware vs Simulation)
# ============================================================================

class CANBusManager:
    """
    Manages CAN bus communication, supporting both real hardware and simulation.
    """
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self._driver: Optional[CANableDriver] = None
        self._simulator: Optional[CANSimulator] = None
        self._message_buffer: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._connected = False
        self._message_callbacks: List[Callable[[CANMessage], None]] = []
        
        if test_mode:
            self._simulator = CANSimulator()
            print("✓ CAN Bus Manager initialized in TEST MODE (no hardware)")
        else:
            self._driver = CANableDriver()
            print("✓ CAN Bus Manager initialized for HARDWARE mode")
    
    def connect(self, channel: int = 0, 
                baudrate: CANableBaudRate = CANableBaudRate.BAUD_500K) -> bool:
        """Connect to CAN bus (hardware or start simulation)."""
        if self.test_mode:
            self._simulator.start(callback=self._on_message_received)
            self._connected = True
            return True
        else:
            if self._driver.connect(channel, baudrate):
                self._driver.start_receive_thread(self._on_message_received)
                self._connected = True
                return True
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from CAN bus."""
        self._connected = False
        
        if self.test_mode:
            if self._simulator:
                self._simulator.stop()
            return True
        else:
            if self._driver:
                self._driver.stop_receive_thread()
                return self._driver.disconnect()
            return False
    
    def send_message(self, can_id: int, data: bytes, 
                     is_extended: bool = False) -> bool:
        """Send a CAN message."""
        if not self._connected:
            return False
        
        if self.test_mode:
            return self._simulator.send_message(can_id, data, is_extended)
        else:
            return self._driver.send_message(can_id, data, is_extended)
    
    def get_messages(self, count: int = 100, 
                     filter_id: Optional[int] = None) -> List[CANMessageJSON]:
        """Get recent messages from the buffer."""
        with self._lock:
            messages = list(self._message_buffer)
        
        if filter_id is not None:
            messages = [m for m in messages if m.id == filter_id]
        
        # Return most recent messages
        messages = messages[-count:]
        
        return [CANMessageJSON.from_can_message(m) for m in messages]
    
    def clear_buffer(self):
        """Clear the message buffer."""
        with self._lock:
            self._message_buffer.clear()
    
    def add_callback(self, callback: Callable[[CANMessage], None]):
        """Add a callback for received messages."""
        self._message_callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[CANMessage], None]):
        """Remove a message callback."""
        if callback in self._message_callbacks:
            self._message_callbacks.remove(callback)
    
    def _on_message_received(self, msg: CANMessage):
        """Internal callback for received messages."""
        with self._lock:
            self._message_buffer.append(msg)
        
        for callback in self._message_callbacks:
            try:
                callback(msg)
            except Exception as e:
                print(f"Callback error: {e}")
    
    def get_status(self) -> dict:
        """Get current status."""
        status = {
            "connected": self._connected,
            "mode": "test/simulation" if self.test_mode else "hardware",
            "buffer_size": len(self._message_buffer),
            "buffer_capacity": self._message_buffer.maxlen
        }
        
        if not self.test_mode and self._driver:
            hw_status = self._driver.get_bus_status()
            status.update(hw_status)
        
        return status
    
    @property
    def is_connected(self) -> bool:
        return self._connected


# ============================================================================
# HTTPS Request Handler
# ============================================================================

class CANServerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for CAN bus API."""
    
    # Class-level reference to CAN bus manager
    can_manager: Optional[CANBusManager] = None
    
    def log_message(self, format, *args):
        """Override to customize logging."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} - {format % args}")
    
    def _set_headers(self, status: int = 200, content_type: str = "application/json"):
        """Set response headers."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _send_json(self, data: dict, status: int = 200):
        """Send JSON response."""
        self._set_headers(status)
        response = json.dumps(data, indent=2)
        self.wfile.write(response.encode("utf-8"))
    
    def _send_error(self, message: str, status: int = 400):
        """Send error response."""
        self._send_json({"error": message, "success": False}, status)
    
    def _parse_query_params(self) -> dict:
        """Parse URL query parameters."""
        parsed = urllib.parse.urlparse(self.path)
        return dict(urllib.parse.parse_qsl(parsed.query))
    
    def _get_path(self) -> str:
        """Get URL path without query string."""
        return urllib.parse.urlparse(self.path).path
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self._set_headers(204)
    
    def do_GET(self):
        """Handle GET requests."""
        path = self._get_path()
        params = self._parse_query_params()
        
        try:
            # API Routes
            if path == "/":
                self._handle_root()
            elif path == "/api/status":
                self._handle_status()
            elif path == "/api/messages":
                self._handle_get_messages(params)
            elif path == "/api/messages/stream":
                self._handle_message_stream()
            elif path == "/api/devices":
                self._handle_get_devices()
            else:
                self._send_error(f"Unknown endpoint: {path}", 404)
                
        except Exception as e:
            self._send_error(str(e), 500)
    
    def do_POST(self):
        """Handle POST requests."""
        path = self._get_path()
        
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            
            # Special handling for DBC upload (raw file content, not JSON)
            if path == "/api/dbc":
                self._handle_dbc_upload(body)
                return
            
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_error("Invalid JSON in request body")
                return
            
            # API Routes
            if path == "/api/connect":
                self._handle_connect(data)
            elif path == "/api/disconnect":
                self._handle_disconnect()
            elif path == "/api/messages":
                self._handle_send_message(data)
            elif path == "/api/transmit":
                self._handle_transmit(data)
            elif path == "/api/messages/batch":
                self._handle_send_batch(data)
            else:
                self._send_error(f"Unknown endpoint: {path}", 404)
                
        except Exception as e:
            self._send_error(str(e), 500)
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        path = self._get_path()
        
        try:
            if path == "/api/messages":
                self._handle_clear_messages()
            elif path == "/api/dbc":
                self._handle_dbc_unload()
            else:
                self._send_error(f"Unknown endpoint: {path}", 404)
                
        except Exception as e:
            self._send_error(str(e), 500)
    
    # ========================================================================
    # API Handlers
    # ========================================================================
    
    def _handle_root(self):
        """Handle root endpoint - API info."""
        self._send_json({
            "name": "CAN Bus HTTPS Server",
            "version": "1.0.0",
            "description": "REST API for CAN bus communication",
            "endpoints": {
                "GET /": "API information",
                "GET /api/status": "Get server and CAN bus status",
                "GET /api/devices": "List available CAN devices",
                "GET /api/messages": "Get received messages (query: count, filter_id)",
                "GET /api/messages/stream": "Server-Sent Events stream",
                "POST /api/connect": "Connect to CAN bus",
                "POST /api/disconnect": "Disconnect from CAN bus",
                "POST /api/dbc": "Upload DBC file for message decoding",
                "POST /api/messages": "Send a CAN message",
                "POST /api/messages/batch": "Send multiple CAN messages",
                "DELETE /api/messages": "Clear message buffer",
                "DELETE /api/dbc": "Unload DBC file"
            },
            "mode": "test" if self.can_manager.test_mode else "hardware"
        })
    
    def _handle_status(self):
        """Handle status endpoint."""
        status = self.can_manager.get_status()
        status["timestamp"] = datetime.now().isoformat()
        status["dbc"] = dbc_manager.get_status()
        self._send_json({"success": True, "status": status})
    
    def _handle_get_devices(self):
        """Handle device listing (hardware mode only)."""
        if self.can_manager.test_mode:
            self._send_json({
                "success": True,
                "mode": "test",
                "devices": [{
                    "index": 0,
                    "name": "Simulated CAN Bus",
                    "description": "Virtual CAN bus for testing"
                }]
            })
        else:
            devices = self.can_manager._driver.get_available_devices()
            self._send_json({
                "success": True,
                "mode": "hardware",
                "devices": devices
            })
    
    def _handle_get_messages(self, params: dict):
        """Handle getting messages."""
        if not self.can_manager.is_connected:
            self._send_error("Not connected to CAN bus", 400)
            return
        
        try:
            count = int(params.get("count", 100))
            filter_id = params.get("filter_id")
            
            if filter_id:
                # Support hex format (0x123) or decimal
                if filter_id.lower().startswith("0x"):
                    filter_id = int(filter_id, 16)
                else:
                    filter_id = int(filter_id)
            
            messages = self.can_manager.get_messages(count, filter_id)
            
            # Convert messages with error handling for each
            message_dicts = []
            for m in messages:
                try:
                    message_dicts.append(m.to_dict())
                except Exception as e:
                    print(f"  Error converting message 0x{m.id:X}: {e}")
                    # Add raw message on error
                    message_dicts.append({
                        "id": m.id,
                        "id_hex": f"0x{m.id:X}",
                        "timestamp": m.timestamp,
                        "dlc": m.dlc,
                        "message_name": None,
                        "signals": None,
                        "data_hex": " ".join(f"{b:02X}" for b in m.data)
                    })
            
            self._send_json({
                "success": True,
                "count": len(message_dicts),
                "messages": message_dicts
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_error(f"Error getting messages: {str(e)}", 500)
    
    def _handle_message_stream(self):
        """Handle Server-Sent Events stream for real-time messages."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        # Message queue for this stream
        message_queue = deque(maxlen=100)
        stop_flag = threading.Event()
        
        def on_message(msg: CANMessage):
            message_queue.append(msg)
        
        self.can_manager.add_callback(on_message)
        
        try:
            while not stop_flag.is_set():
                while message_queue:
                    msg = message_queue.popleft()
                    json_msg = CANMessageJSON.from_can_message(msg)
                    event_data = json.dumps(json_msg.to_dict())
                    self.wfile.write(f"data: {event_data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                
                time.sleep(0.01)
                
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.can_manager.remove_callback(on_message)
    
    def _handle_connect(self, data: dict):
        """Handle connect request."""
        if self.can_manager.is_connected:
            self._send_error("Already connected", 400)
            return
        
        channel = data.get("channel", 0)
        baudrate_str = data.get("baudrate", "BAUD_500K")
        
        # Parse baudrate
        try:
            baudrate = CANableBaudRate[baudrate_str]
        except KeyError:
            self._send_error(
                f"Invalid baudrate: {baudrate_str}. "
                f"Valid options: {[b.name for b in CANableBaudRate]}"
            )
            return
        
        if self.can_manager.connect(channel, baudrate):
            self._send_json({
                "success": True,
                "message": "Connected to CAN bus",
                "channel": channel,
                "baudrate": baudrate.name
            })
        else:
            self._send_error("Failed to connect to CAN bus", 500)
    
    def _handle_disconnect(self):
        """Handle disconnect request."""
        if not self.can_manager.is_connected:
            self._send_error("Not connected", 400)
            return
        
        if self.can_manager.disconnect():
            self._send_json({
                "success": True,
                "message": "Disconnected from CAN bus"
            })
        else:
            self._send_error("Failed to disconnect", 500)
    
    def _handle_send_message(self, data: dict):
        """Handle sending a single message."""
        if not self.can_manager.is_connected:
            self._send_error("Not connected to CAN bus", 400)
            return
        
        # Validate required fields
        if "id" not in data:
            self._send_error("Missing required field: id")
            return
        
        if "data" not in data:
            self._send_error("Missing required field: data")
            return
        
        # Parse CAN ID (supports hex string or integer)
        can_id = data["id"]
        if isinstance(can_id, str):
            if can_id.lower().startswith("0x"):
                can_id = int(can_id, 16)
            else:
                can_id = int(can_id)
        
        # Parse data (supports array of ints, hex string, or bytes)
        msg_data = data["data"]
        if isinstance(msg_data, str):
            # Hex string: "01 02 03 04" or "01020304"
            msg_data = msg_data.replace(" ", "")
            msg_data = bytes.fromhex(msg_data)
        elif isinstance(msg_data, list):
            msg_data = bytes(msg_data)
        
        is_extended = data.get("is_extended", False)
        
        if self.can_manager.send_message(can_id, msg_data, is_extended):
            self._send_json({
                "success": True,
                "message": "Message sent",
                "id": can_id,
                "id_hex": f"0x{can_id:X}",
                "data": list(msg_data),
                "data_hex": " ".join(f"{b:02X}" for b in msg_data)
            })
        else:
            self._send_error("Failed to send message", 500)
    
    def _handle_transmit(self, data: dict):
        """Handle transmit endpoint from Android app."""
        if not self.can_manager.is_connected:
            self._send_error("Not connected to CAN bus", 400)
            return
        
        # Validate required fields
        if "id" not in data:
            self._send_error("Missing required field: id")
            return
        
        if "data" not in data:
            self._send_error("Missing required field: data")
            return
        
        # Parse CAN ID (integer from Android)
        can_id = int(data["id"])
        
        # Parse data (hex string from Android, e.g. "0102030405060708")
        msg_data = data["data"]
        if isinstance(msg_data, str):
            msg_data = msg_data.replace(" ", "")
            msg_data = bytes.fromhex(msg_data) if msg_data else bytes()
        elif isinstance(msg_data, list):
            msg_data = bytes(msg_data)
        
        is_extended = data.get("extended", False)
        
        if self.can_manager.send_message(can_id, msg_data, is_extended):
            self._send_json({
                "success": True,
                "message": "Message transmitted",
                "id": can_id,
                "id_hex": f"0x{can_id:X}",
                "extended": is_extended,
                "data_hex": " ".join(f"{b:02X}" for b in msg_data)
            })
        else:
            self._send_error("Failed to transmit message", 500)

    def _handle_send_batch(self, data: dict):
        """Handle sending multiple messages."""
        if not self.can_manager.is_connected:
            self._send_error("Not connected to CAN bus", 400)
            return
        
        messages = data.get("messages", [])
        if not messages:
            self._send_error("No messages provided")
            return
        
        results = []
        for i, msg in enumerate(messages):
            try:
                can_id = msg["id"]
                if isinstance(can_id, str):
                    can_id = int(can_id, 16) if can_id.startswith("0x") else int(can_id)
                
                msg_data = msg["data"]
                if isinstance(msg_data, str):
                    msg_data = bytes.fromhex(msg_data.replace(" ", ""))
                elif isinstance(msg_data, list):
                    msg_data = bytes(msg_data)
                
                success = self.can_manager.send_message(
                    can_id, msg_data, msg.get("is_extended", False)
                )
                
                results.append({
                    "index": i,
                    "success": success,
                    "id": can_id
                })
                
            except Exception as e:
                results.append({
                    "index": i,
                    "success": False,
                    "error": str(e)
                })
        
        success_count = sum(1 for r in results if r["success"])
        self._send_json({
            "success": success_count == len(messages),
            "total": len(messages),
            "sent": success_count,
            "failed": len(messages) - success_count,
            "results": results
        })
    
    def _handle_clear_messages(self):
        """Handle clearing message buffer."""
        self.can_manager.clear_buffer()
        self._send_json({
            "success": True,
            "message": "Message buffer cleared"
        })
    
    def _handle_dbc_upload(self, content: str):
        """Handle DBC file upload."""
        if not content:
            print("  DBC upload: No content received!")
            self._send_error("No DBC content provided")
            return
        
        print(f"  DBC upload: Received {len(content)} bytes")
        success, message = dbc_manager.load_dbc(content)
        
        if success:
            self._send_json({
                "success": True,
                "message": message,
                "message_count": dbc_manager.message_count
            })
        else:
            print(f"  DBC upload failed: {message}")
            self._send_error(message)
    
    def _handle_dbc_unload(self):
        """Handle DBC file unload."""
        dbc_manager.unload()
        self._send_json({
            "success": True,
            "message": "DBC unloaded"
        })


# ============================================================================
# Thread-safe HTTPS Server
# ============================================================================

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Thread-per-request HTTP server."""
    daemon_threads = True


# ============================================================================
# SSL Certificate Generation
# ============================================================================

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CAN Bus HTTP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start in test mode (no hardware required)
  python can_server.py --test
  
  # Start with real hardware
  python can_server.py --channel 0 --baudrate 500000
  
  # Start on custom port
  python can_server.py --test --port 8080
        """
    )
    
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Run in test mode with simulated CAN traffic (no hardware required)"
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Server port (default: 8080)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0 - all interfaces)"
    )
    
    parser.add_argument(
        "--channel", "-c",
        type=int,
        default=0,
        help="CAN device channel/index (default: 0)"
    )
    
    parser.add_argument(
        "--baudrate", "-b",
        type=int,
        default=500000,
        help="CAN baudrate in bps (default: 500000)"
    )
    
    parser.add_argument(
        "--auto-connect",
        action="store_true",
        help="Automatically connect to CAN bus on startup"
    )
    
    args = parser.parse_args()
    
    # Create CAN bus manager
    can_manager = CANBusManager(test_mode=args.test)
    CANServerHandler.can_manager = can_manager
    
    # Auto-connect if requested
    if args.auto_connect:
        # Find baudrate enum
        baudrate = None
        for br in CANableBaudRate:
            if br.value == args.baudrate:
                baudrate = br
                break
        
        if baudrate is None:
            print(f"⚠ Invalid baudrate {args.baudrate}, using 500K")
            baudrate = CANableBaudRate.BAUD_500K
        
        print(f"\nAuto-connecting to CAN bus...")
        if not can_manager.connect(args.channel, baudrate):
            print("⚠ Auto-connect failed, server starting anyway")
            print("  Use POST /api/connect to connect manually")
    
    # Create server
    server_address = (args.host, args.port)
    httpd = ThreadedHTTPServer(server_address, CANServerHandler)
    
    # Get local IP address
    local_ip = get_local_ip()
    
    # Print startup info
    print("\n" + "=" * 60)
    print("CAN Bus HTTP Server")
    print("=" * 60)
    print(f"  Mode:     {'TEST (simulated)' if args.test else 'HARDWARE'}")
    print(f"  URL:      http://{args.host}:{args.port}/")
    print(f"  Local IP: http://{local_ip}:{args.port}/")
    
    if not args.test:
        print(f"  Channel:  {args.channel}")
        print(f"  Baudrate: {args.baudrate} bps")
    
    print("=" * 60)
    print("\nAPI Endpoints:")
    print("  GET  /                  - API info")
    print("  GET  /api/status        - Server status")
    print("  GET  /api/devices       - List CAN devices")
    print("  GET  /api/messages      - Get received messages")
    print("  GET  /api/messages/stream - Real-time message stream (SSE)")
    print("  POST /api/connect       - Connect to CAN bus")
    print("  POST /api/disconnect    - Disconnect from CAN bus")
    print("  POST /api/messages      - Send a CAN message")
    print("  POST /api/messages/batch - Send multiple messages")
    print("  DELETE /api/messages    - Clear message buffer")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60 + "\n")
    
    # Start server
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        
        # Disconnect CAN bus
        if can_manager.is_connected:
            can_manager.disconnect()
        
        httpd.shutdown()
        print("✓ Server stopped")


if __name__ == "__main__":
    main()
