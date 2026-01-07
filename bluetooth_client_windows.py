#!/usr/bin/env python3
"""
Bluetooth CAN Client for Windows
=================================
Simple Bluetooth SPP client using Windows native sockets.

This is an alternative to bluetooth_client_example.py that works better on Windows.
Uses the built-in socket module with Bluetooth support on Windows 10/11.

Requirements:
    - Windows 10/11 with Bluetooth
    - Python 3.9+ (has native Bluetooth socket support)
    - Device must be paired first via Windows Bluetooth settings

Usage:
    python bluetooth_client_windows.py --address 2C:CF:67:91:EF:15

Author: GitHub Copilot
Date: January 2026
"""

import socket
import json
import time
import threading
import argparse
import sys


class WindowsBluetoothClient:
    """
    Windows Bluetooth SPP client using native sockets.
    
    Python 3.9+ on Windows supports Bluetooth sockets natively without pybluez.
    """
    
    # Bluetooth RFCOMM protocol
    BTPROTO_RFCOMM = 3
    
    def __init__(self):
        self._socket = None
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
    
    def connect(self, address: str, channel: int = 1, timeout: float = 10.0) -> bool:
        """
        Connect to Bluetooth device.
        
        Args:
            address: Bluetooth MAC address (XX:XX:XX:XX:XX:XX)
            channel: RFCOMM channel (default 1)
            timeout: Connection timeout
        """
        if self._connected:
            print("Already connected")
            return True
        
        try:
            print(f"Connecting to {address} on channel {channel}...")
            
            # Create Bluetooth socket
            # AF_BLUETOOTH = 32 on Windows
            self._socket = socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                self.BTPROTO_RFCOMM
            )
            self._socket.settimeout(timeout)
            self._socket.connect((address, channel))
            
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
            
        except OSError as e:
            if e.errno == 10061:
                print(f"✗ Connection refused - is the server running?")
            elif e.errno == 10060:
                print(f"✗ Connection timed out - is the device in range and paired?")
            elif e.errno == 10050:
                print(f"✗ Bluetooth adapter not available")
            else:
                print(f"✗ Connection failed: {e}")
            self._socket = None
            return False
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            self._socket = None
            return False
    
    def disconnect(self):
        """Disconnect from server."""
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
        """Background receive thread."""
        while not self._stop_receive and self._connected:
            try:
                self._socket.settimeout(0.5)
                data = self._socket.recv(4096)
                
                if not data:
                    break
                
                self._response_buffer += data.decode('utf-8', errors='ignore')
                
                while '\n' in self._response_buffer:
                    line, self._response_buffer = self._response_buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self._handle_response(line)
                        
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop_receive:
                    print(f"⚠ Receive error: {e}")
                break
        
        if self._connected:
            self._connected = False
            print("⚠ Connection lost")
    
    def _handle_response(self, line: str):
        """Handle received response."""
        try:
            response = json.loads(line)
            
            if response.get("event") == "messages":
                if self._message_callback:
                    self._message_callback(response)
            else:
                with self._response_lock:
                    self._pending_responses.append(response)
                    
        except json.JSONDecodeError:
            print(f"⚠ Invalid JSON: {line[:100]}")
    
    def _send_command(self, cmd: str, params: dict = None, timeout: float = 5.0) -> dict:
        """Send command and wait for response."""
        if not self._connected:
            return {"success": False, "error": "Not connected"}
        
        command = {"cmd": cmd}
        if params:
            command["params"] = params
        
        with self._response_lock:
            self._pending_responses.clear()
        
        try:
            message = json.dumps(command) + '\n'
            self._socket.send(message.encode('utf-8'))
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._response_lock:
                if self._pending_responses:
                    return self._pending_responses.pop(0)
            time.sleep(0.01)
        
        return {"success": False, "error": "Timeout"}
    
    def set_message_callback(self, callback):
        """Set callback for streaming messages."""
        self._message_callback = callback
    
    # High-level API
    def ping(self): return self._send_command("ping")
    def get_status(self): return self._send_command("get_status")
    def get_devices(self): return self._send_command("get_devices")
    def get_messages(self, count=100): return self._send_command("get_messages", {"count": count})
    def send_message(self, id, data): return self._send_command("send_message", {"id": id, "data": data})
    def subscribe(self): return self._send_command("subscribe")
    def unsubscribe(self): return self._send_command("unsubscribe")
    def clear_messages(self): return self._send_command("clear_messages")


def main():
    parser = argparse.ArgumentParser(description="Windows Bluetooth CAN Client")
    parser.add_argument("--address", "-a", required=True, help="Bluetooth MAC address")
    parser.add_argument("--channel", "-c", type=int, default=1, help="RFCOMM channel")
    parser.add_argument("--subscribe", "-s", action="store_true", help="Subscribe to messages")
    
    args = parser.parse_args()
    
    # Check Python version
    if sys.version_info < (3, 9):
        print("⚠ Python 3.9+ recommended for native Bluetooth support")
    
    client = WindowsBluetoothClient()
    
    if not client.connect(args.address, args.channel):
        print("\nTroubleshooting:")
        print("  1. Ensure the device is paired in Windows Bluetooth settings")
        print("  2. Check that the server is running on the Pi")
        print("  3. Verify the MAC address is correct")
        return
    
    try:
        print("\n--- Ping ---")
        print(client.ping())
        
        print("\n--- Status ---")
        status = client.get_status()
        print(json.dumps(status, indent=2))
        
        print("\n--- Messages ---")
        messages = client.get_messages(10)
        print(f"Count: {messages.get('count', 0)}")
        for msg in messages.get('messages', [])[:3]:
            print(f"  {msg.get('id_hex')}: {msg.get('data_hex')}")
        
        if args.subscribe:
            print("\n--- Subscribing (Ctrl+C to stop) ---")
            
            def on_msg(resp):
                for m in resp.get('messages', []):
                    print(f"  {m.get('id_hex')}: {m.get('data_hex')} ({m.get('message_name', 'Unknown')})")
            
            client.set_message_callback(on_msg)
            client.subscribe()
            
            while client.is_connected:
                time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
