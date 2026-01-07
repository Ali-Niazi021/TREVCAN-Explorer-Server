"""
Bluetooth RFCOMM/SPP Server for CAN Bus
=======================================
Provides Bluetooth Serial Port Profile (SPP) access to the CAN server.

This module allows clients to connect via Bluetooth and use the same
JSON-based protocol as the HTTP API.

Requirements:
    - Linux with BlueZ stack (Raspberry Pi OS includes this)
    - pybluez: pip install pybluez
    - System packages: sudo apt install bluetooth bluez libbluetooth-dev

Pairing:
    Before connecting, devices must be paired with the Raspberry Pi.
    See PROTOCOL.md for detailed pairing instructions.

Author: GitHub Copilot
Date: January 2026
"""

import json
import threading
import time
import select
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass

# Try to import bluetooth module
try:
    import bluetooth
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False
    print("⚠ Bluetooth not available. Install with: pip install pybluez")
    print("  Also ensure system packages: sudo apt install bluetooth bluez libbluetooth-dev")


# SPP UUID - Standard Serial Port Profile
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"

# Custom service name (visible during discovery)
SERVICE_NAME = "TREV-CAN-Server"
SERVICE_DESCRIPTION = "CAN Bus Bluetooth Server"


@dataclass
class BluetoothClient:
    """Represents a connected Bluetooth client."""
    socket: Any
    address: str
    name: str
    connected_at: float
    
    def __hash__(self):
        return hash(self.address)


class BluetoothCANServer:
    """
    Bluetooth RFCOMM server for CAN bus communication.
    
    Supports the same JSON protocol as the HTTP API, allowing clients
    to send commands and receive CAN messages over Bluetooth.
    
    Protocol:
        - Each message is a JSON object terminated by newline (\\n)
        - Request: {"cmd": "command_name", "params": {...}}
        - Response: {"success": true/false, "data": {...}}
    
    Commands:
        - get_status: Get server/CAN status
        - get_devices: List available CAN devices
        - connect: Connect to CAN bus
        - disconnect: Disconnect from CAN bus
        - get_messages: Get received CAN messages
        - send_message: Send a CAN message
        - send_batch: Send multiple CAN messages
        - clear_messages: Clear message buffer
        - load_dbc: Load DBC file content
        - unload_dbc: Unload DBC file
        - subscribe: Subscribe to real-time messages (streaming)
        - unsubscribe: Stop real-time message streaming
    
    Example:
        >>> server = BluetoothCANServer(can_manager, dbc_manager)
        >>> server.start()
        >>> # ... clients can now connect
        >>> server.stop()
    """
    
    def __init__(self, can_manager, dbc_manager, message_buffer):
        """
        Initialize the Bluetooth server.
        
        Args:
            can_manager: CANBusManager instance for CAN operations
            dbc_manager: DBCManager instance for message decoding
            message_buffer: MessageBuffer instance for received messages
        """
        if not BLUETOOTH_AVAILABLE:
            raise RuntimeError("Bluetooth module not available")
        
        self._can_manager = can_manager
        self._dbc_manager = dbc_manager
        self._message_buffer = message_buffer
        
        self._server_socket: Optional[Any] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._clients: Dict[str, BluetoothClient] = {}
        self._client_threads: Dict[str, threading.Thread] = {}
        self._client_lock = threading.Lock()
        
        # Streaming subscribers (clients receiving real-time messages)
        self._subscribers: Dict[str, bool] = {}
        self._stream_thread: Optional[threading.Thread] = None
        self._last_message_count = 0
        
        # Server info
        self._port = 1  # RFCOMM channel (1-30)
        self._local_address: Optional[str] = None
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
    
    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)
    
    @property
    def local_address(self) -> Optional[str]:
        """Local Bluetooth MAC address."""
        return self._local_address
    
    def start(self, channel: int = 1) -> bool:
        """
        Start the Bluetooth RFCOMM server.
        
        Args:
            channel: RFCOMM channel number (1-30, default 1)
        
        Returns:
            True if server started successfully
        """
        if self._running:
            print("⚠ Bluetooth server already running")
            return True
        
        try:
            self._port = channel
            
            # Create RFCOMM server socket
            self._server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self._server_socket.bind(("", self._port))
            self._server_socket.listen(5)  # Max 5 pending connections
            
            # Get local address
            self._local_address = bluetooth.read_local_bdaddr()[0]
            
            # Advertise SPP service
            bluetooth.advertise_service(
                self._server_socket,
                SERVICE_NAME,
                service_id=SPP_UUID,
                service_classes=[SPP_UUID, bluetooth.SERIAL_PORT_CLASS],
                profiles=[bluetooth.SERIAL_PORT_PROFILE],
                description=SERVICE_DESCRIPTION
            )
            
            self._running = True
            
            # Start accept thread
            self._accept_thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="BT-Accept"
            )
            self._accept_thread.start()
            
            # Start stream broadcast thread
            self._stream_thread = threading.Thread(
                target=self._stream_loop,
                daemon=True,
                name="BT-Stream"
            )
            self._stream_thread.start()
            
            print(f"✓ Bluetooth server started")
            print(f"  Address: {self._local_address}")
            print(f"  Channel: {self._port}")
            print(f"  Service: {SERVICE_NAME}")
            
            return True
            
        except Exception as e:
            print(f"✗ Failed to start Bluetooth server: {e}")
            self._running = False
            if self._server_socket:
                try:
                    self._server_socket.close()
                except:
                    pass
                self._server_socket = None
            return False
    
    def stop(self):
        """Stop the Bluetooth server and disconnect all clients."""
        if not self._running:
            return
        
        print("Stopping Bluetooth server...")
        self._running = False
        
        # Close all client connections
        with self._client_lock:
            for addr, client in list(self._clients.items()):
                try:
                    client.socket.close()
                except:
                    pass
            self._clients.clear()
            self._subscribers.clear()
        
        # Stop advertising and close server socket
        if self._server_socket:
            try:
                bluetooth.stop_advertising(self._server_socket)
            except:
                pass
            try:
                self._server_socket.close()
            except:
                pass
            self._server_socket = None
        
        # Wait for threads
        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2)
        
        print("✓ Bluetooth server stopped")
    
    def _accept_loop(self):
        """Accept incoming Bluetooth connections."""
        while self._running:
            try:
                # Use select for non-blocking accept with timeout
                ready, _, _ = select.select([self._server_socket], [], [], 1.0)
                if not ready:
                    continue
                
                client_socket, client_info = self._server_socket.accept()
                client_addr = client_info[0]
                
                # Try to get device name
                try:
                    client_name = bluetooth.lookup_name(client_addr, timeout=5) or "Unknown"
                except:
                    client_name = "Unknown"
                
                print(f"✓ Bluetooth client connected: {client_name} ({client_addr})")
                
                # Create client object
                client = BluetoothClient(
                    socket=client_socket,
                    address=client_addr,
                    name=client_name,
                    connected_at=time.time()
                )
                
                with self._client_lock:
                    self._clients[client_addr] = client
                
                # Start client handler thread
                client_thread = threading.Thread(
                    target=self._client_handler,
                    args=(client,),
                    daemon=True,
                    name=f"BT-Client-{client_addr[-8:]}"
                )
                self._client_threads[client_addr] = client_thread
                client_thread.start()
                
            except bluetooth.BluetoothError as e:
                if self._running:
                    print(f"⚠ Bluetooth accept error: {e}")
            except Exception as e:
                if self._running:
                    print(f"⚠ Bluetooth accept error: {e}")
    
    def _client_handler(self, client: BluetoothClient):
        """Handle communication with a connected client."""
        buffer = ""
        
        try:
            while self._running and client.address in self._clients:
                try:
                    # Use select for non-blocking recv with timeout
                    ready, _, _ = select.select([client.socket], [], [], 0.5)
                    if not ready:
                        continue
                    
                    # Receive data
                    data = client.socket.recv(4096)
                    if not data:
                        break  # Client disconnected
                    
                    # Decode and buffer
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Process complete messages (newline-delimited JSON)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            response = self._process_command(client, line)
                            self._send_response(client, response)
                    
                except bluetooth.BluetoothError as e:
                    if self._running:
                        print(f"⚠ Client {client.address} error: {e}")
                    break
                except Exception as e:
                    if self._running:
                        print(f"⚠ Client {client.address} error: {e}")
                    break
        
        finally:
            self._disconnect_client(client)
    
    def _disconnect_client(self, client: BluetoothClient):
        """Disconnect a client and clean up."""
        with self._client_lock:
            if client.address in self._clients:
                del self._clients[client.address]
            if client.address in self._subscribers:
                del self._subscribers[client.address]
            if client.address in self._client_threads:
                del self._client_threads[client.address]
        
        try:
            client.socket.close()
        except:
            pass
        
        print(f"✗ Bluetooth client disconnected: {client.name} ({client.address})")
    
    def _send_response(self, client: BluetoothClient, response: dict):
        """Send a JSON response to a client."""
        try:
            message = json.dumps(response) + '\n'
            client.socket.send(message.encode('utf-8'))
        except Exception as e:
            print(f"⚠ Failed to send to {client.address}: {e}")
    
    def _process_command(self, client: BluetoothClient, message: str) -> dict:
        """
        Process a command from a client.
        
        Args:
            client: The client that sent the command
            message: JSON command string
        
        Returns:
            Response dictionary
        """
        try:
            cmd_data = json.loads(message)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        
        cmd = cmd_data.get("cmd", "").lower()
        params = cmd_data.get("params", {})
        
        # Command routing
        handlers = {
            "get_status": self._cmd_get_status,
            "get_devices": self._cmd_get_devices,
            "connect": self._cmd_connect,
            "disconnect": self._cmd_disconnect,
            "get_messages": self._cmd_get_messages,
            "send_message": self._cmd_send_message,
            "send_batch": self._cmd_send_batch,
            "clear_messages": self._cmd_clear_messages,
            "load_dbc": self._cmd_load_dbc,
            "unload_dbc": self._cmd_unload_dbc,
            "subscribe": lambda c, p: self._cmd_subscribe(client, p),
            "unsubscribe": lambda c, p: self._cmd_unsubscribe(client, p),
            "ping": self._cmd_ping,
        }
        
        handler = handlers.get(cmd)
        if handler:
            try:
                return handler(client, params)
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": f"Unknown command: {cmd}"}
    
    # ========================================================================
    # Command Handlers
    # ========================================================================
    
    def _cmd_ping(self, client: BluetoothClient, params: dict) -> dict:
        """Ping/pong for connection testing."""
        return {"success": True, "pong": True, "timestamp": time.time()}
    
    def _cmd_get_status(self, client: BluetoothClient, params: dict) -> dict:
        """Get server and CAN bus status."""
        status = {
            "connected": self._can_manager.is_connected,
            "mode": "test/simulation" if self._can_manager._test_mode else "hardware",
            "buffer_size": self._message_buffer.size,
            "buffer_capacity": self._message_buffer._buffer.maxlen,
            "bluetooth_clients": self.client_count,
            "timestamp": time.time()
        }
        
        if self._can_manager.is_connected and hasattr(self._can_manager, '_channel'):
            status["channel"] = self._can_manager._channel
            if hasattr(self._can_manager, '_baudrate') and self._can_manager._baudrate:
                status["baudrate"] = self._can_manager._baudrate.name
        
        return {"success": True, "status": status}
    
    def _cmd_get_devices(self, client: BluetoothClient, params: dict) -> dict:
        """List available CAN devices."""
        devices = self._can_manager.get_available_devices()
        return {
            "success": True,
            "mode": "test" if self._can_manager._test_mode else "hardware",
            "devices": devices
        }
    
    def _cmd_connect(self, client: BluetoothClient, params: dict) -> dict:
        """Connect to CAN bus."""
        from Drivers.BaseDriver import CANBaudRate
        
        channel = params.get("channel", 0)
        baudrate_str = params.get("baudrate", "BAUD_500K")
        
        # Parse baudrate
        baudrate = None
        for br in CANBaudRate:
            if br.name == baudrate_str or str(br.value) == str(baudrate_str):
                baudrate = br
                break
        
        if baudrate is None:
            return {"success": False, "error": f"Invalid baudrate: {baudrate_str}"}
        
        success = self._can_manager.connect(channel, baudrate)
        if success:
            return {
                "success": True,
                "message": f"Connected to channel {channel} at {baudrate.name}"
            }
        else:
            return {"success": False, "error": "Failed to connect to CAN bus"}
    
    def _cmd_disconnect(self, client: BluetoothClient, params: dict) -> dict:
        """Disconnect from CAN bus."""
        self._can_manager.disconnect()
        return {"success": True, "message": "Disconnected from CAN bus"}
    
    def _cmd_get_messages(self, client: BluetoothClient, params: dict) -> dict:
        """Get received CAN messages."""
        count = params.get("count", 100)
        filter_id = params.get("filter_id")
        
        # Convert hex string filter_id if needed
        if isinstance(filter_id, str):
            try:
                filter_id = int(filter_id, 16) if filter_id.startswith("0x") else int(filter_id)
            except:
                filter_id = None
        
        messages = self._message_buffer.get_messages(count=count, filter_id=filter_id)
        
        # Convert to JSON format
        from can_server import CANMessageJSON
        json_messages = []
        for msg in messages:
            json_msg = CANMessageJSON.from_can_message(msg)
            json_messages.append(json_msg.to_dict())
        
        return {
            "success": True,
            "count": len(json_messages),
            "messages": json_messages
        }
    
    def _cmd_send_message(self, client: BluetoothClient, params: dict) -> dict:
        """Send a CAN message."""
        # Parse message ID
        msg_id = params.get("id")
        if msg_id is None:
            return {"success": False, "error": "Missing 'id' parameter"}
        
        if isinstance(msg_id, str):
            try:
                msg_id = int(msg_id, 16) if msg_id.startswith("0x") else int(msg_id)
            except:
                return {"success": False, "error": f"Invalid message ID: {msg_id}"}
        
        # Parse data
        data = params.get("data", [])
        if isinstance(data, str):
            # Hex string: "01 02 03" or "010203"
            data = data.replace(" ", "")
            try:
                data = [int(data[i:i+2], 16) for i in range(0, len(data), 2)]
            except:
                return {"success": False, "error": "Invalid hex data string"}
        
        if len(data) > 8:
            return {"success": False, "error": "Data length exceeds 8 bytes"}
        
        is_extended = params.get("extended", False)
        
        success = self._can_manager.send_message(msg_id, bytes(data), is_extended)
        if success:
            return {
                "success": True,
                "message": f"Sent message 0x{msg_id:X} with {len(data)} bytes"
            }
        else:
            return {"success": False, "error": "Failed to send message"}
    
    def _cmd_send_batch(self, client: BluetoothClient, params: dict) -> dict:
        """Send multiple CAN messages."""
        messages = params.get("messages", [])
        if not messages:
            return {"success": False, "error": "No messages provided"}
        
        sent = 0
        failed = 0
        
        for msg_params in messages:
            result = self._cmd_send_message(client, msg_params)
            if result.get("success"):
                sent += 1
            else:
                failed += 1
        
        return {
            "success": failed == 0,
            "sent": sent,
            "failed": failed
        }
    
    def _cmd_clear_messages(self, client: BluetoothClient, params: dict) -> dict:
        """Clear message buffer."""
        self._message_buffer.clear()
        return {"success": True, "message": "Message buffer cleared"}
    
    def _cmd_load_dbc(self, client: BluetoothClient, params: dict) -> dict:
        """Load DBC file content."""
        content = params.get("content")
        if not content:
            return {"success": False, "error": "Missing 'content' parameter"}
        
        success, message = self._dbc_manager.load_from_string(content)
        if success:
            return {
                "success": True,
                "message": "DBC loaded successfully",
                "message_count": self._dbc_manager.message_count
            }
        else:
            return {"success": False, "error": message}
    
    def _cmd_unload_dbc(self, client: BluetoothClient, params: dict) -> dict:
        """Unload DBC file."""
        self._dbc_manager.unload()
        return {"success": True, "message": "DBC unloaded"}
    
    def _cmd_subscribe(self, client: BluetoothClient, params: dict) -> dict:
        """Subscribe to real-time message streaming."""
        with self._client_lock:
            self._subscribers[client.address] = True
        return {"success": True, "message": "Subscribed to message stream"}
    
    def _cmd_unsubscribe(self, client: BluetoothClient, params: dict) -> dict:
        """Unsubscribe from real-time message streaming."""
        with self._client_lock:
            if client.address in self._subscribers:
                del self._subscribers[client.address]
        return {"success": True, "message": "Unsubscribed from message stream"}
    
    # ========================================================================
    # Message Streaming
    # ========================================================================
    
    def _stream_loop(self):
        """Broadcast new messages to subscribed clients."""
        while self._running:
            try:
                time.sleep(0.05)  # 50ms interval (20 Hz)
                
                # Check for new messages
                current_count = self._message_buffer.size
                if current_count <= self._last_message_count:
                    continue
                
                # Get new messages
                new_count = current_count - self._last_message_count
                messages = self._message_buffer.get_messages(count=new_count)
                
                if not messages:
                    continue
                
                self._last_message_count = current_count
                
                # Get subscribers
                with self._client_lock:
                    subscribers = [
                        self._clients[addr]
                        for addr in self._subscribers
                        if addr in self._clients
                    ]
                
                if not subscribers:
                    continue
                
                # Convert messages to JSON
                from can_server import CANMessageJSON
                json_messages = []
                for msg in messages[-50:]:  # Limit to 50 per batch
                    json_msg = CANMessageJSON.from_can_message(msg)
                    json_messages.append(json_msg.to_dict())
                
                # Broadcast to subscribers
                stream_data = {
                    "event": "messages",
                    "count": len(json_messages),
                    "messages": json_messages
                }
                
                for client in subscribers:
                    try:
                        self._send_response(client, stream_data)
                    except:
                        pass  # Client will be cleaned up by handler
                
            except Exception as e:
                if self._running:
                    print(f"⚠ Stream error: {e}")


# =============================================================================
# Helper Functions
# =============================================================================

def get_bluetooth_info() -> dict:
    """Get local Bluetooth adapter information."""
    if not BLUETOOTH_AVAILABLE:
        return {"available": False, "error": "Bluetooth module not installed"}
    
    try:
        # Get local address
        local_addr = bluetooth.read_local_bdaddr()[0]
        
        # Get adapter name
        try:
            import subprocess
            result = subprocess.run(
                ["hciconfig", "hci0", "name"],
                capture_output=True,
                text=True,
                timeout=5
            )
            name = "Unknown"
            for line in result.stdout.split('\n'):
                if "Name:" in line:
                    name = line.split("Name:")[1].strip().strip("'")
                    break
        except:
            name = "Unknown"
        
        return {
            "available": True,
            "address": local_addr,
            "name": name
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def make_discoverable(timeout: int = 0):
    """
    Make the Bluetooth adapter discoverable.
    
    Args:
        timeout: Discoverable timeout in seconds (0 = forever)
    """
    try:
        import subprocess
        
        # Enable page and inquiry scan (discoverable + connectable)
        subprocess.run(["hciconfig", "hci0", "piscan"], check=True, timeout=5)
        
        if timeout > 0:
            # Set discoverable timeout
            subprocess.run(
                ["bluetoothctl", "discoverable-timeout", str(timeout)],
                timeout=5
            )
        
        print(f"✓ Bluetooth adapter is now discoverable")
        return True
    except Exception as e:
        print(f"⚠ Failed to make discoverable: {e}")
        return False
