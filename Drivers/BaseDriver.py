"""
CAN Driver Base Class
=====================
Abstract base class that defines the interface for CAN device drivers.
All CAN device drivers should inherit from this class and implement the
required methods.

This module also contains the CANMessage dataclass which provides a 
standardized message format across all drivers.

Author: GitHub Copilot
Date: December 2025
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Callable


class CANBaudRate(Enum):
    """Standard CAN baud rates supported by drivers"""
    BAUD_1M = 1000000
    BAUD_800K = 800000
    BAUD_500K = 500000
    BAUD_250K = 250000
    BAUD_125K = 125000
    BAUD_100K = 100000
    BAUD_50K = 50000
    BAUD_20K = 20000
    BAUD_10K = 10000


@dataclass
class CANMessage:
    """
    Represents a CAN message with all relevant information.
    
    This is the standard message format used across all CAN drivers.
    
    Attributes:
        id: CAN arbitration ID (11-bit for standard, 29-bit for extended)
        data: Message payload as bytes (up to 8 bytes for CAN 2.0, up to 64 for CAN FD)
        timestamp: Message timestamp in seconds (default: 0.0)
        is_extended: True if using 29-bit extended ID (default: False)
        is_remote: True if this is a remote frame (default: False)
        is_error: True if this is an error frame (default: False)
        is_fd: True if this is a CAN FD frame (default: False)
        dlc: Data Length Code, automatically set from data length if not provided
    """
    id: int
    data: bytes
    timestamp: float = 0.0
    is_extended: bool = False
    is_remote: bool = False
    is_error: bool = False
    is_fd: bool = False
    dlc: int = 0
    
    def __post_init__(self):
        if self.dlc == 0:
            self.dlc = len(self.data)
    
    def __str__(self):
        msg_type = "EXT" if self.is_extended else "STD"
        data_str = ' '.join([f'{b:02X}' for b in self.data])
        return f"ID: 0x{self.id:X} [{msg_type}] DLC: {self.dlc} Data: [{data_str}]"


class BaseCANDriver(ABC):
    """
    Abstract base class for CAN device drivers.
    
    All CAN drivers should inherit from this class and implement the
    abstract methods to provide a consistent interface for the application.
    
    Example implementation:
        class MyCANDriver(BaseCANDriver):
            def get_available_devices(self) -> List[dict]:
                # Scan for devices
                ...
            
            def connect(self, channel: int, baudrate: CANBaudRate, fd_mode: bool = False) -> bool:
                # Connect to device
                ...
            
            # ... implement other required methods
    """
    
    @abstractmethod
    def get_available_devices(self) -> List[dict]:
        """
        Scan for available CAN devices.
        
        Returns:
            List of dictionaries containing device information.
            Each device dict should include at minimum:
                - 'index': Device index/number
                - 'description': Human-readable device description
            
            Additional fields are driver-specific.
        """
        pass
    
    @abstractmethod
    def connect(self, channel: int, baudrate: CANBaudRate, fd_mode: bool = False) -> bool:
        """
        Connect to a CAN device.
        
        Args:
            channel: Device channel/index to connect to
            baudrate: CAN bus baudrate
            fd_mode: Enable CAN FD mode (default: False)
        
        Returns:
            True if connection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the CAN device.
        
        Returns:
            True if disconnection successful, False otherwise.
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def read_message(self, timeout: float = 1.0) -> Optional[CANMessage]:
        """
        Read a CAN message from the bus.
        
        Args:
            timeout: Timeout in seconds (default: 1.0)
        
        Returns:
            CANMessage object if message received, None on timeout or error.
        """
        pass
    
    @abstractmethod
    def start_receive_thread(self, callback: Callable[[CANMessage], None]) -> bool:
        """
        Start a background thread to continuously receive messages.
        
        Args:
            callback: Function to call when a message is received.
                     Should accept a CANMessage parameter.
        
        Returns:
            True if thread started successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def stop_receive_thread(self) -> bool:
        """
        Stop the background receive thread.
        
        Returns:
            True if thread stopped successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the driver is currently connected to a device.
        
        Returns:
            True if connected, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_bus_status(self) -> dict:
        """
        Get the current status of the CAN bus.
        
        Returns:
            Dictionary containing bus status information.
            Should include at minimum:
                - 'connected': bool
                - 'channel': current channel or None
                - 'baudrate': current baudrate or None
            
            Additional fields are driver-specific.
        """
        pass
