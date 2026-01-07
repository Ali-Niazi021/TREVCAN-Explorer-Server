#!/usr/bin/env python3
"""
Bluetooth CAN Client Example
============================
Example Python client for connecting to the CAN server via Bluetooth RFCOMM/SPP.

This demonstrates how to:
- Discover and connect to the CAN server
- Send commands and receive responses
- Subscribe to real-time CAN message streaming

Requirements:
    pip install pybluez

Usage:
    # Discover devices
    python bluetooth_client_example.py --discover
    
    # Connect to known address
    python bluetooth_client_example.py --address XX:XX:XX:XX:XX:XX
    
    # Connect and subscribe to messages
    python bluetooth_client_example.py --address XX:XX:XX:XX:XX:XX --subscribe

Author: GitHub Copilot
Date: January 2026
"""

import json
import time
import threading
import argparse
import sys

try:
    import bluetooth
except ImportError:
    print("Error: pybluez not installed")
    print("Install with: pip install pybluez")
    sys.exit(1)


# SPP UUID - Standard Serial Port Profile
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"

# Service name to look for
SERVICE_NAME = "TREV-CAN-Server"


class BluetoothCANClient:
    """
    Bluetooth client for the CAN server.
    
    Connects via RFCOMM/SPP and provides methods to send commands
    and receive responses using the JSON protocol.
    
    Example:
        >>> client = BluetoothCANClient()
        >>> client.connect("XX:XX:XX:XX:XX:XX")
        >>> status = client.get_status()
        >>> print(status)
        >>> client.disconnect()
    """
    
    def __init__(self):
        self._socket = None
        self._address = None
        self._connected = False
        self._receive_thread = None
        self._stop_receive = False
        self._response_buffer = ""
        self._pending_responses = []
        self._response_lock = threading.Lock()
        self._message_callback = None
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def discover_services(self, duration: int = 8) -> list:
        """
        Discover CAN server services via Bluetooth.
        
        Args:
            duration: Discovery duration in seconds
        
        Returns:
            List of found services with address, name, and port
        """
        print(f"Discovering Bluetooth devices ({duration}s)...")
        
        # Find all nearby devices
        nearby_devices = bluetooth.discover_devices(
            duration=duration,
            lookup_names=True,
            lookup_class=True
        )
        
        print(f"Found {len(nearby_devices)} devices")
        
        services = []
        for addr, name, device_class in nearby_devices:
            print(f"  Checking {name} ({addr})...")
            
            # Search for SPP service
            try:
                service_matches = bluetooth.find_service(
                    uuid=SPP_UUID,
                    address=addr
                )
                
                for svc in service_matches:
                    services.append({
                        "address": addr,
                        "name": name,
                        "service_name": svc.get("name", "Unknown"),
                        "port": svc.get("port", 1),
                        "description": svc.get("description", "")
                    })
                    print(f"    Found service: {svc.get('name')} on port {svc.get('port')}")
            except Exception as e:
                print(f"    Error: {e}")
        
        return services
    
    def connect(self, address: str, port: int = 1, timeout: float = 10.0) -> bool:
        """
        Connect to the CAN server.
        
        Args:
            address: Bluetooth MAC address (XX:XX:XX:XX:XX:XX)
            port: RFCOMM channel (default 1)
            timeout: Connection timeout in seconds
        
        Returns:
            True if connected successfully
        """
        if self._connected:
            print("Already connected")
            return True
        
        try:
            print(f"Connecting to {address} on channel {port}...")
            
            self._socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self._socket.settimeout(timeout)
            
            # Windows requires different connection approach
            if sys.platform == 'win32':
                # On Windows, try using the service UUID lookup
                try:
                    # Find services on the device
                    services = bluetooth.find_service(
                        uuid="00001101-0000-1000-8000-00805F9B34FB",
                        address=address
                    )
                    if services:
                        service = services[0]
                        host = service["host"]
                        port = service["port"]
                        print(f"  Found SPP service on port {port}")
                        self._socket.connect((host, port))
                    else:
                        # Fallback: connect directly
                        self._socket.connect((address, port))
                except Exception as e:
                    print(f"  Service lookup failed: {e}")
                    # Try direct connection with tuple format
                    self._socket.connect((address, port))
            else:
                # Linux/Mac: direct connection works
                self._socket.connect((address, port))
            
            self._address = address
            self._connected = True
            self._stop_receive = False
            
            # Start receive thread
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True
            )
            self._receive_thread.start()
            
            print(f"✓ Connected to {address}")
            return True
            
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            self._socket = None
            return False
    
    def disconnect(self):
        """Disconnect from the server."""
        if not self._connected:
            return
        
        self._stop_receive = True
        self._connected = False
        
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        print("✓ Disconnected")
    
    def _receive_loop(self):
        """Background thread to receive data."""
        while not self._stop_receive and self._connected:
            try:
                self._socket.settimeout(0.5)
                data = self._socket.recv(4096)
                
                if not data:
                    break
                
                self._response_buffer += data.decode('utf-8', errors='ignore')
                
                # Process complete messages
                while '\n' in self._response_buffer:
                    line, self._response_buffer = self._response_buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self._handle_response(line)
                        
            except bluetooth.BluetoothError as e:
                if "timed out" not in str(e).lower():
                    if not self._stop_receive:
                        print(f"⚠ Receive error: {e}")
                    break
            except Exception as e:
                if not self._stop_receive:
                    print(f"⚠ Receive error: {e}")
                break
        
        if self._connected:
            self._connected = False
            print("⚠ Connection lost")
    
    def _handle_response(self, line: str):
        """Handle a received response."""
        try:
            response = json.loads(line)
            
            # Check if it's a streaming message
            if response.get("event") == "messages":
                if self._message_callback:
                    self._message_callback(response)
            else:
                # Regular response - add to queue
                with self._response_lock:
                    self._pending_responses.append(response)
                    
        except json.JSONDecodeError:
            print(f"⚠ Invalid JSON: {line[:100]}")
    
    def _send_command(self, cmd: str, params: dict = None, timeout: float = 5.0) -> dict:
        """
        Send a command and wait for response.
        
        Args:
            cmd: Command name
            params: Command parameters
            timeout: Response timeout in seconds
        
        Returns:
            Response dictionary
        """
        if not self._connected:
            return {"success": False, "error": "Not connected"}
        
        # Build command
        command = {"cmd": cmd}
        if params:
            command["params"] = params
        
        # Clear pending responses
        with self._response_lock:
            self._pending_responses.clear()
        
        # Send
        try:
            message = json.dumps(command) + '\n'
            self._socket.send(message.encode('utf-8'))
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._response_lock:
                if self._pending_responses:
                    return self._pending_responses.pop(0)
            time.sleep(0.01)
        
        return {"success": False, "error": "Timeout waiting for response"}
    
    def set_message_callback(self, callback):
        """
        Set callback for streaming messages.
        
        Args:
            callback: Function(response_dict) called for each message batch
        """
        self._message_callback = callback
    
    # ========================================================================
    # High-level API methods
    # ========================================================================
    
    def ping(self) -> dict:
        """Test connection with ping/pong."""
        return self._send_command("ping")
    
    def get_status(self) -> dict:
        """Get server and CAN bus status."""
        return self._send_command("get_status")
    
    def get_devices(self) -> dict:
        """List available CAN devices."""
        return self._send_command("get_devices")
    
    def connect_can(self, channel: int = 0, baudrate: str = "BAUD_500K") -> dict:
        """
        Connect to CAN bus.
        
        Args:
            channel: CAN channel index
            baudrate: Baudrate name (e.g., "BAUD_500K", "BAUD_250K")
        """
        return self._send_command("connect", {
            "channel": channel,
            "baudrate": baudrate
        })
    
    def disconnect_can(self) -> dict:
        """Disconnect from CAN bus."""
        return self._send_command("disconnect")
    
    def get_messages(self, count: int = 100, filter_id: int = None) -> dict:
        """
        Get received CAN messages.
        
        Args:
            count: Maximum number of messages
            filter_id: Filter by message ID (optional)
        """
        params = {"count": count}
        if filter_id is not None:
            params["filter_id"] = filter_id
        return self._send_command("get_messages", params)
    
    def send_message(self, msg_id: int, data: list, extended: bool = False) -> dict:
        """
        Send a CAN message.
        
        Args:
            msg_id: CAN arbitration ID
            data: Data bytes (list of integers 0-255)
            extended: Use extended (29-bit) ID
        """
        return self._send_command("send_message", {
            "id": msg_id,
            "data": data,
            "extended": extended
        })
    
    def send_batch(self, messages: list) -> dict:
        """
        Send multiple CAN messages.
        
        Args:
            messages: List of message dicts with id, data, extended
        """
        return self._send_command("send_batch", {"messages": messages})
    
    def clear_messages(self) -> dict:
        """Clear message buffer."""
        return self._send_command("clear_messages")
    
    def load_dbc(self, content: str) -> dict:
        """
        Load DBC file content.
        
        Args:
            content: DBC file content as string
        """
        return self._send_command("load_dbc", {"content": content})
    
    def unload_dbc(self) -> dict:
        """Unload DBC file."""
        return self._send_command("unload_dbc")
    
    def subscribe(self) -> dict:
        """Subscribe to real-time message streaming."""
        return self._send_command("subscribe")
    
    def unsubscribe(self) -> dict:
        """Unsubscribe from message streaming."""
        return self._send_command("unsubscribe")


# =============================================================================
# CLI Application
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Bluetooth CAN Client Example",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover available services
  python bluetooth_client_example.py --discover
  
  # Connect to a specific device
  python bluetooth_client_example.py --address XX:XX:XX:XX:XX:XX
  
  # Connect and stream messages
  python bluetooth_client_example.py --address XX:XX:XX:XX:XX:XX --subscribe
        """
    )
    
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover Bluetooth CAN servers"
    )
    
    parser.add_argument(
        "--address", "-a",
        type=str,
        help="Bluetooth MAC address to connect to"
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=1,
        help="RFCOMM channel (default: 1)"
    )
    
    parser.add_argument(
        "--subscribe", "-s",
        action="store_true",
        help="Subscribe to real-time messages"
    )
    
    args = parser.parse_args()
    
    client = BluetoothCANClient()
    
    # Discovery mode
    if args.discover:
        services = client.discover_services()
        print(f"\nFound {len(services)} CAN server services:")
        for svc in services:
            print(f"  {svc['name']} ({svc['address']})")
            print(f"    Service: {svc['service_name']}")
            print(f"    Port: {svc['port']}")
        
        if services:
            print(f"\nTo connect, use:")
            print(f"  python {sys.argv[0]} --address {services[0]['address']} --port {services[0]['port']}")
        return
    
    # Connect mode
    if not args.address:
        print("Error: --address required (or use --discover)")
        return
    
    if not client.connect(args.address, args.port):
        return
    
    try:
        # Test connection
        print("\n--- Ping ---")
        result = client.ping()
        print(f"Ping: {result}")
        
        # Get status
        print("\n--- Status ---")
        result = client.get_status()
        print(json.dumps(result, indent=2))
        
        # Get devices
        print("\n--- Devices ---")
        result = client.get_devices()
        print(json.dumps(result, indent=2))
        
        # Subscribe to messages if requested
        if args.subscribe:
            print("\n--- Subscribing to messages (Ctrl+C to stop) ---")
            
            def on_messages(response):
                messages = response.get("messages", [])
                for msg in messages:
                    print(f"  {msg.get('id_hex', '???')}: {msg.get('data_hex', '???')} "
                          f"({msg.get('message_name', 'Unknown')})")
            
            client.set_message_callback(on_messages)
            result = client.subscribe()
            print(f"Subscribe: {result}")
            
            # Keep running
            try:
                while client.is_connected:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n\nUnsubscribing...")
                client.unsubscribe()
        else:
            # Interactive demo
            print("\n--- Getting messages ---")
            result = client.get_messages(count=10)
            print(f"Message count: {result.get('count', 0)}")
            for msg in result.get("messages", [])[:5]:
                print(f"  {msg.get('id_hex')}: {msg.get('data_hex')} ({msg.get('message_name')})")
    
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
