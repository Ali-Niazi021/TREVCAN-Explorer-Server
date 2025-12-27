"""
Waveshare 2-CH Isolated CAN HAT Driver
======================================
Driver for Raspberry Pi with Waveshare 2-Channel Isolated CAN HAT.
Uses SocketCAN interface via python-can.

This HAT uses MCP2515 CAN controllers connected via SPI.
Each channel (can0, can1) is configured via device tree overlays.

Prerequisites:
    - Enable SPI in raspi-config
    - Add to /boot/firmware/config.txt:
        dtparam=spi=on
        dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=25
        dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=23
    - Reboot after changes
    - Install python-can: pip install python-can

Author: GitHub Copilot
Date: December 2025
"""

from typing import Optional, List, Callable
import subprocess
import threading
import time
import asyncio
import inspect

from can import Bus, Message

from Drivers.BaseDriver import BaseCANDriver, CANBaudRate, CANMessage


class PiWaveshare2ChCAN_Driver(BaseCANDriver):
    """
    Driver for Waveshare 2-CH Isolated CAN HAT on Raspberry Pi.
    
    This driver uses the SocketCAN interface to communicate with the
    MCP2515-based CAN controllers on the HAT.
    
    Example:
        >>> driver = PiWaveshare2ChCAN_Driver(channel=0)  # Use can0
        >>> devices = driver.get_available_devices()
        >>> driver.connect(0, CANBaudRate.BAUD_500K)
        >>> driver.send_message(0x123, b'\\x01\\x02\\x03\\x04')
        >>> msg = driver.read_message()
        >>> driver.disconnect()
    """
    
    def __init__(self, channel: int = 0):
        """
        Initialize the Waveshare CAN HAT driver.
        
        Args:
            channel: CAN channel to use (0 for can0, 1 for can1)
        """
        if channel not in (0, 1):
            raise ValueError("Channel must be 0 or 1")
        
        self._default_channel = channel
        self._channel_name = f"can{channel}"
        self._bus: Optional[Bus] = None
        self._channel: Optional[int] = None
        self._baudrate: Optional[CANBaudRate] = None
        self._is_connected: bool = False
        self._receive_thread: Optional[threading.Thread] = None
        self._receive_callback: Optional[Callable[[CANMessage], None]] = None
        self._stop_receive: bool = False
    
    def _run_command(self, cmd: str) -> tuple[bool, str]:
        """Run a shell command and return (success, output)."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
    
    def _is_interface_up(self, interface: str) -> bool:
        """Check if a CAN interface is up."""
        success, output = self._run_command(f"ip link show {interface}")
        return success and "UP" in output
    
    def _get_interface_state(self, interface: str) -> Optional[str]:
        """Get the CAN interface state (ERROR-ACTIVE, ERROR-PASSIVE, etc.)."""
        success, output = self._run_command(f"ip -d link show {interface}")
        if not success:
            return None
        
        # Parse state from output
        for line in output.split('\n'):
            if 'can state' in line:
                parts = line.split('can state')
                if len(parts) > 1:
                    state = parts[1].strip().split()[0]
                    return state
        return None
    
    def _bring_up_interface(self, interface: str, bitrate: int) -> tuple[bool, str]:
        """Bring up a CAN interface with the specified bitrate."""
        # First bring it down if it's already up
        self._run_command(f"sudo ip link set {interface} down")
        time.sleep(0.2)
        
        # Configure and bring up
        success, output = self._run_command(
            f"sudo ip link set {interface} up type can bitrate {bitrate}"
        )
        
        if not success:
            return False, f"Failed to bring up {interface}: {output}"
        
        time.sleep(0.3)
        
        # Verify it's up
        if not self._is_interface_up(interface):
            return False, f"{interface} failed to come up"
        
        return True, f"{interface} up at {bitrate} bps"
    
    def _bring_down_interface(self, interface: str) -> tuple[bool, str]:
        """Bring down a CAN interface."""
        success, output = self._run_command(f"sudo ip link set {interface} down")
        if not success:
            return False, f"Failed to bring down {interface}: {output}"
        return True, f"{interface} down"
    
    def get_available_devices(self) -> List[dict]:
        """
        Scan for available CAN interfaces.
        
        Returns:
            List of dictionaries containing device information.
        """
        available_devices = []
        
        for channel in [0, 1]:
            interface = f"can{channel}"
            success, output = self._run_command(f"ip link show {interface}")
            
            if success:
                is_up = "UP" in output
                state = self._get_interface_state(interface)
                
                device_info = {
                    'index': channel,
                    'channel': interface,
                    'description': f"Waveshare 2-CH CAN HAT - Channel {channel}",
                    'is_up': is_up,
                    'state': state,
                    'type': 'socketcan'
                }
                available_devices.append(device_info)
        
        if not available_devices:
            print("ℹ No CAN interfaces found")
            print("  Make sure:")
            print("  1. Waveshare 2-CH CAN HAT is connected")
            print("  2. SPI is enabled in raspi-config")
            print("  3. Device tree overlays are configured in /boot/firmware/config.txt:")
            print("     dtparam=spi=on")
            print("     dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=25")
            print("     dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=23")
            print("  4. Raspberry Pi has been rebooted after config changes")
        
        return available_devices
    
    def connect(self, channel: int, baudrate: CANBaudRate, 
                fd_mode: bool = False) -> bool:
        """
        Connect to a CAN interface.
        
        Args:
            channel: CAN channel (0 or 1)
            baudrate: CAN bus baudrate
            fd_mode: CAN FD mode (not supported on MCP2515, ignored)
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self._is_connected:
            print("Already connected. Disconnect first.")
            return False
        
        if channel not in (0, 1):
            print(f"✗ Invalid channel: {channel}. Must be 0 or 1.")
            return False
        
        if fd_mode:
            print("⚠ Warning: CAN FD is not supported on MCP2515. Using classic CAN.")
        
        interface = f"can{channel}"
        bitrate = baudrate.value
        
        try:
            # Bring up the interface
            success, msg = self._bring_up_interface(interface, bitrate)
            if not success:
                print(f"✗ {msg}")
                return False
            
            # Create SocketCAN bus instance
            self._bus = Bus(
                channel=interface,
                interface='socketcan',
                bitrate=bitrate
            )
            
            self._channel = channel
            self._channel_name = interface
            self._baudrate = baudrate
            self._is_connected = True
            
            print(f"✓ Connected to {interface} at {bitrate} bps")
            return True
            
        except Exception as e:
            print(f"✗ Failed to connect: {str(e)}")
            # Try to clean up
            self._bring_down_interface(interface)
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from the CAN interface.
        
        Returns:
            True if disconnection successful, False otherwise.
        """
        if not self._is_connected:
            print("Not connected.")
            return False
        
        try:
            # Stop receive thread if running
            self.stop_receive_thread()
            
            # Shutdown bus
            if self._bus:
                try:
                    self._bus.shutdown()
                except Exception:
                    pass
                self._bus = None
            
            # Bring down the interface
            if self._channel_name:
                self._bring_down_interface(self._channel_name)
            
            self._is_connected = False
            self._channel = None
            self._baudrate = None
            
            print(f"✓ Disconnected from {self._channel_name}")
            return True
            
        except Exception as e:
            print(f"✗ Failed to disconnect: {str(e)}")
            # Force cleanup
            self._is_connected = False
            self._bus = None
            self._channel = None
            self._baudrate = None
            return False
    
    def send_message(self, can_id: int, data: bytes, 
                     is_extended: bool = False, 
                     is_remote: bool = False) -> bool:
        """
        Send a CAN message.
        
        Args:
            can_id: CAN identifier (11-bit for standard, 29-bit for extended)
            data: Message data (up to 8 bytes)
            is_extended: Use extended 29-bit identifier (default: False)
            is_remote: Send as remote frame (default: False)
        
        Returns:
            True if message sent successfully, False otherwise.
        """
        if not self._is_connected or self._bus is None:
            print("✗ Not connected")
            return False
        
        try:
            msg = Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=is_extended,
                is_remote_frame=is_remote
            )
            
            self._bus.send(msg)
            return True
            
        except Exception as e:
            if self._is_connected:
                print(f"✗ Failed to send message: {str(e)}")
            return False
    
    def read_message(self, timeout: float = 1.0) -> Optional[CANMessage]:
        """
        Read a CAN message from the bus.
        
        Args:
            timeout: Timeout in seconds (default: 1.0)
        
        Returns:
            CANMessage object if message received, None otherwise.
        """
        if not self._is_connected or self._bus is None:
            return None
        
        try:
            msg = self._bus.recv(timeout=timeout)
            
            if msg is None:
                return None
            
            return CANMessage(
                id=msg.arbitration_id,
                data=bytes(msg.data),
                timestamp=msg.timestamp,
                is_extended=msg.is_extended_id,
                is_remote=msg.is_remote_frame,
                is_error=msg.is_error_frame,
                is_fd=msg.is_fd,
                dlc=msg.dlc
            )
            
        except Exception as e:
            if self._is_connected:
                print(f"✗ Failed to read message: {str(e)}")
            return None
    
    def start_receive_thread(self, callback: Callable[[CANMessage], None]) -> bool:
        """
        Start a background thread to continuously receive messages.
        
        Args:
            callback: Function to call when a message is received.
        
        Returns:
            True if thread started successfully, False otherwise.
        """
        if not self._is_connected:
            print("✗ Not connected")
            return False
        
        if self._receive_thread and self._receive_thread.is_alive():
            print("✗ Receive thread already running")
            return False
        
        self._receive_callback = callback
        self._stop_receive = False
        self._receive_thread = threading.Thread(
            target=self._receive_loop,
            daemon=True
        )
        self._receive_thread.start()
        
        print("✓ Receive thread started")
        return True
    
    def stop_receive_thread(self) -> bool:
        """
        Stop the background receive thread.
        
        Returns:
            True if thread stopped successfully, False otherwise.
        """
        if not self._receive_thread or not self._receive_thread.is_alive():
            return False
        
        self._stop_receive = True
        self._receive_thread.join(timeout=3.0)
        
        if self._receive_thread.is_alive():
            print("⚠ Warning: Receive thread did not stop cleanly")
        
        self._receive_thread = None
        self._receive_callback = None
        
        print("✓ Receive thread stopped")
        return True
    
    def _receive_loop(self):
        """Internal method for receiving messages in a loop."""
        while not self._stop_receive and self._is_connected:
            try:
                msg = self.read_message(timeout=0.1)
                if msg and self._receive_callback:
                    # Check if callback is async
                    if inspect.iscoroutinefunction(self._receive_callback):
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self._receive_callback(msg),
                                    loop
                                )
                            else:
                                asyncio.run(self._receive_callback(msg))
                        except RuntimeError:
                            asyncio.run(self._receive_callback(msg))
                    else:
                        self._receive_callback(msg)
            except Exception as e:
                if self._is_connected and not self._stop_receive:
                    print(f"⚠ Receive error: {str(e)}")
                    time.sleep(0.1)
    
    def is_connected(self) -> bool:
        """
        Check if the driver is currently connected.
        
        Returns:
            True if connected, False otherwise.
        """
        return self._is_connected
    
    def get_bus_status(self) -> dict:
        """
        Get the current status of the CAN bus.
        
        Returns:
            Dictionary containing bus status information.
        """
        status = {
            'connected': self._is_connected,
            'channel': self._channel,
            'channel_name': self._channel_name if self._is_connected else None,
            'baudrate': self._baudrate.value if self._baudrate else None,
            'driver': 'PiWaveshare2ChCAN',
            'interface': 'socketcan'
        }
        
        if self._is_connected and self._channel_name:
            # Get detailed interface status
            state = self._get_interface_state(self._channel_name)
            status['bus_state'] = state
            
            # Get error counts
            success, output = self._run_command(
                f"ip -d -s link show {self._channel_name}"
            )
            if success:
                # Parse TX/RX stats
                for line in output.split('\n'):
                    if 'RX:' in line or 'TX:' in line:
                        status['raw_stats'] = output
                        break
        
        return status
