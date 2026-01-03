"""
PCAN Driver
===========
Driver for PEAK PCAN-USB adapters.

This driver provides support for PEAK-System PCAN-USB CAN interfaces
using the python-can library with the PCAN backend.

Author: GitHub Copilot
Date: January 2026
"""

from typing import Optional, List, Callable
import time
import threading
import asyncio
import inspect

try:
    from can import Bus, Message
    from can.interfaces.pcan.basic import (
        PCANBasic,
        PCAN_USBBUS1, PCAN_USBBUS2, PCAN_USBBUS3, PCAN_USBBUS4,
        PCAN_USBBUS5, PCAN_USBBUS6, PCAN_USBBUS7, PCAN_USBBUS8,
        PCAN_USBBUS9, PCAN_USBBUS10, PCAN_USBBUS11, PCAN_USBBUS12,
        PCAN_USBBUS13, PCAN_USBBUS14, PCAN_USBBUS15, PCAN_USBBUS16,
        PCAN_ERROR_OK, PCAN_CHANNEL_CONDITION, PCAN_CHANNEL_AVAILABLE,
        PCAN_CHANNEL_OCCUPIED, PCAN_DEVICE_NUMBER,
        PCAN_ERROR_BUSLIGHT, PCAN_ERROR_BUSHEAVY, PCAN_ERROR_BUSOFF
    )
    PCAN_AVAILABLE = True
except ImportError:
    PCAN_AVAILABLE = False
    print("⚠ PCAN library not available. Install with: pip install python-can")

from Drivers.BaseDriver import BaseCANDriver, CANBaudRate, CANMessage


# PCAN USB channel mapping
PCAN_CHANNELS = [
    ('USB1', PCAN_USBBUS1 if PCAN_AVAILABLE else 0x51),
    ('USB2', PCAN_USBBUS2 if PCAN_AVAILABLE else 0x52),
    ('USB3', PCAN_USBBUS3 if PCAN_AVAILABLE else 0x53),
    ('USB4', PCAN_USBBUS4 if PCAN_AVAILABLE else 0x54),
    ('USB5', PCAN_USBBUS5 if PCAN_AVAILABLE else 0x55),
    ('USB6', PCAN_USBBUS6 if PCAN_AVAILABLE else 0x56),
    ('USB7', PCAN_USBBUS7 if PCAN_AVAILABLE else 0x57),
    ('USB8', PCAN_USBBUS8 if PCAN_AVAILABLE else 0x58),
    ('USB9', PCAN_USBBUS9 if PCAN_AVAILABLE else 0x59),
    ('USB10', PCAN_USBBUS10 if PCAN_AVAILABLE else 0x5A),
    ('USB11', PCAN_USBBUS11 if PCAN_AVAILABLE else 0x5B),
    ('USB12', PCAN_USBBUS12 if PCAN_AVAILABLE else 0x5C),
    ('USB13', PCAN_USBBUS13 if PCAN_AVAILABLE else 0x5D),
    ('USB14', PCAN_USBBUS14 if PCAN_AVAILABLE else 0x5E),
    ('USB15', PCAN_USBBUS15 if PCAN_AVAILABLE else 0x5F),
    ('USB16', PCAN_USBBUS16 if PCAN_AVAILABLE else 0x60),
]


class PCANDriver(BaseCANDriver):
    """
    Driver for PEAK PCAN-USB adapters.
    
    This class provides a high-level interface to:
    - Initialize and connect to PCAN-USB devices
    - Send and receive CAN messages
    - Configure CAN parameters
    - Monitor bus status
    - Handle errors
    
    Uses the PCAN interface from python-can for communication with
    PEAK-System CAN adapters.
    
    Example:
        >>> driver = PCANDriver()
        >>> devices = driver.get_available_devices()
        >>> driver.connect(0, CANBaudRate.BAUD_500K)  # Connect to first device
        >>> driver.send_message(0x123, b'\\x01\\x02\\x03\\x04')
        >>> msg = driver.read_message()
        >>> driver.disconnect()
    """
    
    def __init__(self):
        """Initialize the PCAN driver."""
        self._bus: Optional[Bus] = None
        self._channel: Optional[int] = None
        self._channel_name: Optional[str] = None
        self._channel_value: Optional[int] = None
        self._baudrate: Optional[CANBaudRate] = None
        self._is_connected: bool = False
        self._receive_thread: Optional[threading.Thread] = None
        self._receive_callback: Optional[Callable[[CANMessage], None]] = None
        self._stop_receive: bool = False
        self._device_info: Optional[dict] = None
        
        # Initialize PCANBasic for device enumeration
        self._pcan_basic = None
        if PCAN_AVAILABLE:
            try:
                self._pcan_basic = PCANBasic()
            except Exception as e:
                print(f"⚠ Could not initialize PCANBasic: {e}")
    
    def get_available_devices(self) -> List[dict]:
        """
        Scan for available PCAN-USB devices.
        
        Returns:
            List of dictionaries containing device information.
            Each device has: index, channel_name, channel_value, available, occupied
        """
        available_devices = []
        
        if not PCAN_AVAILABLE:
            print("⚠ PCAN library not available")
            return available_devices
        
        if self._pcan_basic is None:
            print("⚠ PCANBasic not initialized")
            return available_devices
        
        device_index = 0
        for channel_name, channel_value in PCAN_CHANNELS:
            try:
                # Try to get channel condition
                result = self._pcan_basic.GetValue(
                    channel_value, 
                    PCAN_CHANNEL_CONDITION
                )
                
                if result[0] == PCAN_ERROR_OK:
                    condition = result[1]
                    if condition & PCAN_CHANNEL_AVAILABLE:
                        device_info = {
                            'index': device_index,
                            'channel_name': channel_name,
                            'channel_value': channel_value,
                            'available': True,
                            'occupied': bool(condition & PCAN_CHANNEL_OCCUPIED),
                            'description': f"PCAN-USB {channel_name}"
                        }
                        
                        # Try to get device number
                        try:
                            result = self._pcan_basic.GetValue(
                                channel_value,
                                PCAN_DEVICE_NUMBER
                            )
                            if result[0] == PCAN_ERROR_OK:
                                device_info['device_number'] = result[1]
                        except:
                            pass
                        
                        available_devices.append(device_info)
                        device_index += 1
            except Exception:
                # Channel not available or error occurred
                pass
        
        if not available_devices:
            print("ℹ No PCAN-USB devices found")
            print("  Make sure:")
            print("  1. PCAN-USB adapter is connected")
            print("  2. PCAN drivers are installed")
            print("  3. On Windows: PCAN-Basic API DLL is available")
        
        return available_devices
    
    def connect(self, channel: int, baudrate: CANBaudRate, 
                fd_mode: bool = False) -> bool:
        """
        Connect to a PCAN-USB device.
        
        Args:
            channel: Device index (0 for first device, 1 for second, etc.)
                    Use get_available_devices() to see available indices.
            baudrate: CAN bus baudrate (e.g., CANBaudRate.BAUD_500K)
            fd_mode: Enable CAN FD mode (default: False)
        
        Returns:
            True if connection successful, False otherwise.
        """
        if not PCAN_AVAILABLE:
            print("✗ PCAN library not available")
            return False
        
        if self._is_connected:
            print("Already connected to a PCAN device. Disconnect first.")
            return False
        
        try:
            # Get available devices
            devices = self.get_available_devices()
            
            if channel >= len(devices):
                print(f"✗ Invalid channel index {channel}. Available: 0-{len(devices)-1}")
                return False
            
            device = devices[channel]
            channel_name = device['channel_name']
            channel_value = device['channel_value']
            
            # Map channel name to string for python-can (e.g., USB1 -> PCAN_USBBUS1)
            channel_str = channel_name.replace('USB', 'PCAN_USBBUS')
            
            # Get bitrate value
            bitrate = baudrate.value
            
            print(f"ℹ Attempting to connect to {channel_str} at {bitrate} bps...")
            
            # Create bus instance using PCAN interface
            self._bus = Bus(
                interface='pcan',
                channel=channel_str,
                bitrate=bitrate,
                fd=fd_mode
            )
            
            self._channel = channel
            self._channel_name = channel_name
            self._channel_value = channel_value
            self._baudrate = baudrate
            self._is_connected = True
            self._device_info = device
            
            print(f"✓ Connected to PCAN-{channel_name} at {bitrate} bps")
            return True
            
        except Exception as e:
            print(f"✗ Failed to connect: {str(e)}")
            print(f"\n  Troubleshooting:")
            print(f"  1. Verify PCAN-USB adapter is connected")
            print(f"  2. Check that PCAN drivers are installed")
            print(f"  3. On Windows: Ensure PCAN-Basic API DLL is available")
            print(f"  4. Try installing: pip install python-can[pcan]")
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from the PCAN device.
        
        Returns:
            True if disconnection successful, False otherwise.
        """
        if not self._is_connected:
            print("Not connected to any PCAN device.")
            return False
        
        try:
            # Set flag to signal we're disconnecting
            self._is_connected = False
            
            # Stop receive thread if running
            self.stop_receive_thread()
            
            # Give time for thread to fully stop
            time.sleep(0.3)
            
            # Shutdown bus
            if self._bus:
                try:
                    self._bus.shutdown()
                except Exception as e:
                    print(f"⚠ Note during shutdown: {str(e)}")
                finally:
                    self._bus = None
            
            # Additional delay to ensure device is released
            time.sleep(0.5)
            
            self._channel = None
            self._channel_name = None
            self._channel_value = None
            self._baudrate = None
            self._device_info = None
            
            print("✓ Disconnected from PCAN device")
            return True
            
        except Exception as e:
            print(f"✗ Failed to disconnect: {str(e)}")
            # Clean up even on error
            self._is_connected = False
            self._bus = None
            self._channel = None
            self._channel_name = None
            self._channel_value = None
            self._baudrate = None
            self._device_info = None
            return False
    
    def send_message(self, can_id: int, data: bytes, 
                    is_extended: bool = False, 
                    is_remote: bool = False) -> bool:
        """
        Send a CAN message.
        
        Args:
            can_id: CAN identifier (11-bit for standard, 29-bit for extended)
            data: Message data (up to 8 bytes for CAN 2.0, up to 64 for CAN FD)
            is_extended: Use extended 29-bit identifier (default: False)
            is_remote: Send as remote frame (default: False)
        
        Returns:
            True if message sent successfully, False otherwise.
        """
        if not self._is_connected or self._bus is None:
            print("✗ Not connected to PCAN device")
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
                     Should accept a CANMessage parameter.
        
        Returns:
            True if thread started successfully, False otherwise.
        """
        if not self._is_connected:
            print("✗ Not connected to PCAN device")
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
        
        # Wait for thread to finish
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
                if not self._stop_receive and self._is_connected:
                    print(f"Error in receive loop: {str(e)}")
                break
    
    def is_connected(self) -> bool:
        """Check if connected to a PCAN device."""
        return self._is_connected
    
    def get_bus_status(self) -> dict:
        """
        Get the current status of the CAN bus.
        
        Returns:
            Dictionary containing bus status information.
        """
        if not self._is_connected:
            return {'connected': False, 'error': 'Not connected'}
        
        status = {
            'connected': True,
            'channel': self._channel,
            'channel_name': self._channel_name,
            'baudrate': self._baudrate.name if self._baudrate else 'Unknown',
            'interface': 'PCAN-USB',
            'status': 'OK'
        }
        
        # Try to get detailed status from PCAN
        if self._pcan_basic and self._channel_value:
            try:
                result = self._pcan_basic.GetStatus(self._channel_value)
                
                if result == PCAN_ERROR_OK:
                    status['bus_status'] = 'OK'
                elif result == PCAN_ERROR_BUSLIGHT:
                    status['bus_status'] = 'Bus Light Error'
                elif result == PCAN_ERROR_BUSHEAVY:
                    status['bus_status'] = 'Bus Heavy Error'
                elif result == PCAN_ERROR_BUSOFF:
                    status['bus_status'] = 'Bus Off'
                else:
                    status['bus_status'] = f'Error: {result}'
            except:
                pass
        
        # Add device info if available
        if self._device_info:
            status['device'] = self._device_info.get('description', 'Unknown')
            if 'device_number' in self._device_info:
                status['device_number'] = self._device_info['device_number']
        
        return status
    
    def reset_device(self) -> bool:
        """
        Reset the PCAN device.
        
        Returns:
            True if reset successful, False otherwise.
        """
        if not self._is_connected or not self._pcan_basic:
            print("✗ Not connected to PCAN device")
            return False
        
        try:
            from can.interfaces.pcan.basic import PCAN_ERROR_OK
            result = self._pcan_basic.Reset(self._channel_value)
            if result == PCAN_ERROR_OK:
                print("✓ Device reset successfully")
                return True
            else:
                print(f"✗ Failed to reset device: Error {result}")
                return False
        except Exception as e:
            print(f"✗ Failed to reset device: {str(e)}")
            return False
    
    def clear_receive_queue(self) -> bool:
        """
        Clear the receive queue.
        
        Returns:
            True if queue cleared successfully, False otherwise.
        """
        if not self._is_connected:
            print("✗ Not connected to PCAN device")
            return False
        
        try:
            count = 0
            while self.read_message(timeout=0.01):
                count += 1
            
            print(f"✓ Cleared {count} messages from queue")
            return True
            
        except Exception as e:
            print(f"✗ Failed to clear queue: {str(e)}")
            return False
    
    @property
    def channel(self) -> Optional[int]:
        """Get the current channel (device index)."""
        return self._channel
    
    @property
    def baudrate(self) -> Optional[CANBaudRate]:
        """Get the current baudrate."""
        return self._baudrate
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.disconnect()
    
    def __del__(self):
        """Destructor - ensures cleanup."""
        if self._is_connected:
            self.disconnect()


# Example usage and testing
if __name__ == "__main__":
    print("=" * 60)
    print("PCAN Driver Test")
    print("=" * 60)
    
    # Create driver instance
    driver = PCANDriver()
    
    # Scan for available devices
    print("\n1. Scanning for PCAN devices...")
    devices = driver.get_available_devices()
    
    if not devices:
        print("✗ No PCAN devices found!")
        print("  Make sure your PCAN-USB adapter is connected.")
        exit(1)
    
    print(f"✓ Found {len(devices)} device(s):")
    for dev in devices:
        status = "OCCUPIED" if dev.get('occupied') else "AVAILABLE"
        print(f"  - {dev['channel_name']}: {status}")
    
    # Connect to first available device
    print("\n2. Connecting to device...")
    
    if driver.connect(0, CANBaudRate.BAUD_500K):
        print(f"✓ Successfully connected!")
        
        # Get bus status
        print("\n3. Checking bus status...")
        status = driver.get_bus_status()
        print(f"  Status: {status.get('status', 'Unknown')}")
        
        # Example: Send a message
        print("\n4. Sending test message...")
        test_data = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
        if driver.send_message(0x123, test_data):
            print(f"✓ Message sent: ID=0x123, Data={test_data.hex()}")
        
        # Example: Read messages
        print("\n5. Listening for messages (5 seconds)...")
        print("  (Send some CAN messages to see them here)")
        
        def message_handler(msg: CANMessage):
            print(f"  Received: {msg}")
        
        driver.start_receive_thread(message_handler)
        time.sleep(5)
        driver.stop_receive_thread()
        
        # Disconnect
        print("\n6. Disconnecting...")
        driver.disconnect()
    else:
        print("✗ Failed to connect!")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
