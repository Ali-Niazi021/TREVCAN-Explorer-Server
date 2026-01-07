# CAN Bus HTTP Server Protocol Documentation

## Overview

This document describes the CAN Bus HTTP Server protocol for interfacing with CAN bus hardware over a network. The server provides a REST API that allows clients to send and receive CAN messages, making it possible to integrate CAN bus communication into any application that can make HTTP requests.

## Server Information

| Property | Value |
|----------|-------|
| Default Port | 8080 |
| Protocol | HTTP |
| Content-Type | application/json |
| Authentication | None (network-level security recommended) |

## Quick Start

### Starting the Server

```bash
# Test mode (no hardware required - simulates CAN traffic)
python can_server.py --test

# Hardware mode with auto-connect
python can_server.py --channel 0 --baudrate 500000 --auto-connect

# Custom port
python can_server.py --test --port 3000
```

### Basic Client Example (Python)

```python
import requests

BASE_URL = "http://localhost:8080"

# Connect to CAN bus
response = requests.post(f"{BASE_URL}/api/connect", 
    json={"channel": 0, "baudrate": "BAUD_500K"}
)
print(response.json())

# Send a CAN message
response = requests.post(f"{BASE_URL}/api/messages",
    json={
        "id": "0x123",
        "data": [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
    }
)
print(response.json())

# Read received messages
response = requests.get(f"{BASE_URL}/api/messages?count=10")
print(response.json())
```

---

## API Reference

### 1. Server Information

#### `GET /`

Returns basic server information and available endpoints.

**Response:**
```json
{
  "name": "CAN Bus HTTP Server",
  "version": "1.0.0",
  "description": "REST API for CAN bus communication",
  "mode": "test",
  "endpoints": {
    "GET /": "API information",
    "GET /api/status": "Get server and CAN bus status",
    "GET /api/devices": "List available CAN devices",
    "GET /api/messages": "Get received messages",
    "GET /api/messages/stream": "Server-Sent Events stream",
    "POST /api/connect": "Connect to CAN bus",
    "POST /api/disconnect": "Disconnect from CAN bus",
    "POST /api/messages": "Send a CAN message",
    "POST /api/messages/batch": "Send multiple CAN messages",
    "DELETE /api/messages": "Clear message buffer"
  }
}
```

---

### 2. Status

#### `GET /api/status`

Returns the current status of the server and CAN bus connection.

**Response:**
```json
{
  "success": true,
  "status": {
    "connected": true,
    "mode": "test/simulation",
    "buffer_size": 42,
    "buffer_capacity": 1000,
    "timestamp": "2025-12-09T10:30:00.000000"
  }
}
```

**Status Fields:**
| Field | Type | Description |
|-------|------|-------------|
| connected | boolean | Whether connected to CAN bus |
| mode | string | "test/simulation" or "hardware" |
| buffer_size | integer | Number of messages in buffer |
| buffer_capacity | integer | Maximum buffer size |
| timestamp | string | ISO 8601 timestamp |

In hardware mode, additional fields are included:
- `channel`: Device channel index
- `baudrate`: Current baudrate name
- `interface`: Interface type (gs_usb)
- `device`: Device description
- `serial`: Device serial number

---

### 3. Device Enumeration

#### `GET /api/devices`

Lists available CAN devices (hardware mode) or virtual device (test mode).

**Response (Test Mode):**
```json
{
  "success": true,
  "mode": "test",
  "devices": [
    {
      "index": 0,
      "name": "Simulated CAN Bus",
      "description": "Virtual CAN bus for testing"
    }
  ]
}
```

**Response (Hardware Mode):**
```json
{
  "success": true,
  "mode": "hardware",
  "devices": [
    {
      "index": 0,
      "vid": 7504,
      "pid": 24687,
      "manufacturer": "candleLight",
      "product": "candleLight USB-CAN",
      "serial_number": "0001234ABCD",
      "bus": 1,
      "address": 5,
      "description": "candleLight candleLight USB-CAN",
      "channel": "can0"
    }
  ]
}
```

---

### 4. Connection Management

#### `POST /api/connect`

Connect to a CAN bus device.

**Request Body:**
```json
{
  "channel": 0,
  "baudrate": "BAUD_500K"
}
```

**Parameters:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| channel | integer | No | 0 | Device index from /api/devices |
| baudrate | string | No | "BAUD_500K" | Baudrate enum name |

**Valid Baudrate Values:**
- `BAUD_1M` (1,000,000 bps)
- `BAUD_800K` (800,000 bps)
- `BAUD_500K` (500,000 bps)
- `BAUD_250K` (250,000 bps)
- `BAUD_125K` (125,000 bps)
- `BAUD_100K` (100,000 bps)
- `BAUD_50K` (50,000 bps)
- `BAUD_20K` (20,000 bps)
- `BAUD_10K` (10,000 bps)

**Success Response:**
```json
{
  "success": true,
  "message": "Connected to CAN bus",
  "channel": 0,
  "baudrate": "BAUD_500K"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Failed to connect to CAN bus"
}
```

---

#### `POST /api/disconnect`

Disconnect from the CAN bus.

**Request Body:** None required

**Success Response:**
```json
{
  "success": true,
  "message": "Disconnected from CAN bus"
}
```

---

### 4b. DBC File Management

#### `POST /api/dbc`

Upload a DBC file for message decoding. When a DBC file is loaded, messages will be decoded into human-readable signal names and values.

**Request:**
- Content-Type: `text/plain`
- Body: Raw DBC file content as text

**Success Response:**
```json
{
  "success": true,
  "message": "Loaded 8 messages",
  "message_count": 8
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Failed to parse DBC: <error details>"
}
```

---

#### `DELETE /api/dbc`

Unload the current DBC file. Messages will return to raw format.

**Response:**
```json
{
  "success": true,
  "message": "DBC unloaded"
}
```

---

### 5. Sending Messages

#### `POST /api/messages`

Send a single CAN message.

**Request Body:**
```json
{
  "id": "0x123",
  "data": [1, 2, 3, 4, 5, 6, 7, 8],
  "is_extended": false
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | int/string | Yes | CAN ID (decimal or hex string "0x123") |
| data | array/string | Yes | Data bytes as array [0,1,2...] or hex string "01 02 03" |
| is_extended | boolean | No | Use 29-bit extended ID (default: false) |

**Data Format Examples:**
```json
// Array of integers (0-255)
"data": [0x01, 0x02, 0x03, 0x04]

// Hex string with spaces
"data": "01 02 03 04 05 06 07 08"

// Hex string without spaces
"data": "0102030405060708"
```

**Success Response:**
```json
{
  "success": true,
  "message": "Message sent",
  "id": 291,
  "id_hex": "0x123",
  "data": [1, 2, 3, 4, 5, 6, 7, 8],
  "data_hex": "01 02 03 04 05 06 07 08"
}
```

---

#### `POST /api/messages/batch`

Send multiple CAN messages in a single request.

**Request Body:**
```json
{
  "messages": [
    {"id": "0x100", "data": [1, 2, 3, 4]},
    {"id": "0x101", "data": "05 06 07 08"},
    {"id": "0x102", "data": [9, 10, 11, 12], "is_extended": true}
  ]
}
```

**Success Response:**
```json
{
  "success": true,
  "total": 3,
  "sent": 3,
  "failed": 0,
  "results": [
    {"index": 0, "success": true, "id": 256},
    {"index": 1, "success": true, "id": 257},
    {"index": 2, "success": true, "id": 258}
  ]
}
```

---

### 6. Receiving Messages

#### `GET /api/messages`

Retrieve messages from the receive buffer.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| count | integer | 100 | Maximum messages to return |
| filter_id | int/string | none | Filter by CAN ID (e.g., "0x123" or 291) |

**Example Requests:**
```
GET /api/messages
GET /api/messages?count=50
GET /api/messages?filter_id=0x0C0
GET /api/messages?count=10&filter_id=192
```

**Response:**
```json
{
  "success": true,
  "count": 2,
  "messages": [
    {
      "id": 192,
      "id_hex": "0xC0",
      "timestamp": 1702123456.789,
      "dlc": 8,
      "message_name": "TEST_EngineRPM",
      "signals": [
        {"name": "RPM", "value": 3124, "unit": "rpm"}
      ],
      "data_hex": "34 0C 00 00 00 00 00 00"
    },
    {
      "id": 999,
      "id_hex": "0x3E7",
      "timestamp": 1702123456.850,
      "dlc": 8,
      "message_name": null,
      "signals": null,
      "data_hex": "01 02 03 04 05 06 07 08"
    }
  ]
}
```

**Message Fields:**
| Field | Type | Description |
|-------|------|-------------|
| id | integer | CAN arbitration ID |
| id_hex | string | Hex representation of ID |
| timestamp | float | Unix timestamp |
| dlc | integer | Data length code |
| message_name | string/null | DBC message name (null if unknown) |
| signals | array/null | Decoded signals (null if unknown) |
| data_hex | string | Raw hex data (always included) |

**Signal Object:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Signal name from DBC |
| value | number/string | Decoded signal value |
| unit | string | Signal unit (e.g., "rpm", "km/h") |

---

#### `GET /api/messages/stream`

Server-Sent Events (SSE) stream for real-time message reception.

**Response Headers:**
```
Content-Type: text/event-stream
Cache-Control: no-cache
```

**Event Format:**
```
data: {"id": 192, "id_hex": "0xC0", "data": [12, 52, 0, 0, 0, 0, 0, 0], ...}

data: {"id": 176, "id_hex": "0xB0", "data": [0, 120, 0, 0, 0, 0, 0, 0], ...}
```

**JavaScript Client Example:**
```javascript
const eventSource = new EventSource('https://localhost:8443/api/messages/stream');

eventSource.onmessage = function(event) {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
};

eventSource.onerror = function(error) {
    console.error('Stream error:', error);
};
```

---

#### `DELETE /api/messages`

Clear the message receive buffer.

**Response:**
```json
{
  "success": true,
  "message": "Message buffer cleared"
}
```

---

## CAN Message Format

### Standard Message Object

```json
{
  "id": 291,
  "id_hex": "0x123",
  "data": [1, 2, 3, 4, 5, 6, 7, 8],
  "data_hex": "01 02 03 04 05 06 07 08",
  "timestamp": 1702123456.789,
  "timestamp_iso": "2025-12-09T10:30:56.789000",
  "is_extended": false,
  "is_remote": false,
  "is_error": false,
  "dlc": 8
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| id | integer | CAN arbitration ID (11-bit standard or 29-bit extended) |
| id_hex | string | Hexadecimal representation of ID |
| data | array | Message data bytes (0-8 bytes for CAN 2.0) |
| data_hex | string | Space-separated hex representation of data |
| timestamp | float | Unix timestamp with microsecond precision |
| timestamp_iso | string | ISO 8601 formatted timestamp |
| is_extended | boolean | True if using 29-bit extended ID |
| is_remote | boolean | True if this is a Remote Transmission Request |
| is_error | boolean | True if this is an error frame |
| dlc | integer | Data Length Code (number of data bytes) |

---

## Test Mode Simulation

When running in test mode (`--test` flag), the server simulates realistic automotive CAN traffic.

### Simulated Message IDs

| ID (Hex) | Name | Pattern | Description |
|----------|------|---------|-------------|
| 0x0C0 | Engine RPM | Variable | RPM value 800-6000, responds to throttle |
| 0x0B0 | Vehicle Speed | Variable | Speed 0-120 mph |
| 0x0D0 | Throttle Position | Random | Throttle 0-100% |
| 0x0E0 | Coolant Temperature | Rising | Temperature 60-100°C |
| 0x1A0 | Brake Pressure | Event-based | Pressure during braking |
| 0x1B0 | Steering Angle | Oscillating | Angle -45 to +45 degrees |
| 0x1C0 | Battery Voltage | Stable | Voltage ~12-14V |
| 0x1D0 | Fuel Level | Decreasing | Fuel level slowly drops |

### Simulation Behavior

1. **Message Generation**: All simulated ECUs generate messages at ~20Hz (50ms cycle)
2. **Realistic Patterns**: Values change realistically (RPM follows throttle, speed follows RPM)
3. **TX Echo**: Transmitted messages are echoed back to simulate loopback
4. **No Hardware Required**: Perfect for client development and testing

---

## Error Handling

### Error Response Format

```json
{
  "success": false,
  "error": "Error message description"
}
```

### Common Error Codes

| HTTP Status | Condition |
|-------------|-----------|
| 400 | Bad Request - Invalid parameters or not connected |
| 404 | Not Found - Unknown endpoint |
| 500 | Internal Server Error - Hardware or processing failure |

### Common Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| "Not connected to CAN bus" | Attempting operation before connect | Call POST /api/connect first |
| "Already connected" | Calling connect when already connected | Call disconnect first if needed |
| "Invalid baudrate" | Unrecognized baudrate string | Use valid BAUD_* enum name |
| "Missing required field: id" | Send without message ID | Include "id" in request body |
| "Invalid JSON in request body" | Malformed JSON | Check JSON syntax |

---

## Client Implementation Guide

### For AI Agent Integration

When implementing a client using an AI agent, follow these patterns:

#### 1. Connection Flow

```
1. GET /api/status -> Check if already connected
2. GET /api/devices -> List available devices (optional)
3. POST /api/connect -> Connect with desired parameters
4. Verify connection with GET /api/status
```

#### 2. Sending Messages

```
For single message:
    POST /api/messages with {id, data}

For multiple messages:
    POST /api/messages/batch with {messages: [...]}
```

#### 3. Receiving Messages

**Polling (Simple):**
```
Loop:
    GET /api/messages?count=100
    Process messages
    Wait 100ms
```

**Streaming (Efficient):**
```
Open SSE connection: GET /api/messages/stream
Handle each 'data:' event as JSON message
Reconnect on disconnect
```

#### 4. Graceful Shutdown

```
POST /api/disconnect
```

### Client Code Examples

#### Python Client

```python
import requests
import json

class CANBusClient:
    def __init__(self, base_url="https://localhost:8443", verify_ssl=False):
        self.base_url = base_url
        self.verify = verify_ssl
        self.session = requests.Session()
    
    def connect(self, channel=0, baudrate="BAUD_500K"):
        response = self.session.post(
            f"{self.base_url}/api/connect",
            json={"channel": channel, "baudrate": baudrate},
            verify=self.verify
        )
        return response.json()
    
    def disconnect(self):
        response = self.session.post(
            f"{self.base_url}/api/disconnect",
            verify=self.verify
        )
        return response.json()
    
    def send(self, can_id, data, is_extended=False):
        response = self.session.post(
            f"{self.base_url}/api/messages",
            json={"id": can_id, "data": data, "is_extended": is_extended},
            verify=self.verify
        )
        return response.json()
    
    def receive(self, count=100, filter_id=None):
        params = {"count": count}
        if filter_id is not None:
            params["filter_id"] = filter_id
        
        response = self.session.get(
            f"{self.base_url}/api/messages",
            params=params,
            verify=self.verify
        )
        return response.json()
    
    def get_status(self):
        response = self.session.get(
            f"{self.base_url}/api/status",
            verify=self.verify
        )
        return response.json()

# Usage
client = CANBusClient()
client.connect()
client.send(0x123, [0x01, 0x02, 0x03, 0x04])
messages = client.receive()
client.disconnect()
```

#### JavaScript/Node.js Client

```javascript
const https = require('https');

class CANBusClient {
    constructor(baseUrl = 'https://localhost:8443') {
        this.baseUrl = baseUrl;
        this.agent = new https.Agent({ rejectUnauthorized: false });
    }

    async request(method, path, body = null) {
        const url = new URL(path, this.baseUrl);
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' },
            agent: this.agent
        };

        return new Promise((resolve, reject) => {
            const req = https.request(url, options, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => resolve(JSON.parse(data)));
            });
            req.on('error', reject);
            if (body) req.write(JSON.stringify(body));
            req.end();
        });
    }

    connect(channel = 0, baudrate = 'BAUD_500K') {
        return this.request('POST', '/api/connect', { channel, baudrate });
    }

    disconnect() {
        return this.request('POST', '/api/disconnect');
    }

    send(id, data, isExtended = false) {
        return this.request('POST', '/api/messages', { 
            id, data, is_extended: isExtended 
        });
    }

    receive(count = 100, filterId = null) {
        let path = `/api/messages?count=${count}`;
        if (filterId) path += `&filter_id=${filterId}`;
        return this.request('GET', path);
    }
}

// Usage
const client = new CANBusClient();
await client.connect();
await client.send(0x123, [1, 2, 3, 4]);
const messages = await client.receive();
await client.disconnect();
```

#### cURL Examples

```bash
# Check status
curl -k https://localhost:8443/api/status

# Connect to CAN bus
curl -k -X POST https://localhost:8443/api/connect \
  -H "Content-Type: application/json" \
  -d '{"channel": 0, "baudrate": "BAUD_500K"}'

# Send a message
curl -k -X POST https://localhost:8443/api/messages \
  -H "Content-Type: application/json" \
  -d '{"id": "0x123", "data": [1, 2, 3, 4, 5, 6, 7, 8]}'

# Get messages
curl -k "https://localhost:8443/api/messages?count=10"

# Get messages filtered by ID
curl -k "https://localhost:8443/api/messages?filter_id=0x0C0"

# Disconnect
curl -k -X POST https://localhost:8443/api/disconnect
```

---

## Security Considerations

### SSL/TLS

- The server generates a self-signed certificate by default
- For production, use a proper CA-signed certificate
- Certificate files: `server.crt` and `server.key`

### Network Security

- The server binds to all interfaces (0.0.0.0) by default
- Consider using firewall rules to restrict access
- Use VPN or network segmentation for sensitive CAN data

### Authentication

- No built-in authentication
- Implement at network/firewall level
- Consider adding API keys for production use

---

## Command Line Reference

```
usage: can_server.py [-h] [--test] [--port PORT] [--host HOST] 
                     [--channel CHANNEL] [--baudrate BAUDRATE]
                     [--auto-connect] [--driver {canable,waveshare,pcan}]
                     [--bluetooth] [--bt-channel BT_CHANNEL] [--bt-discoverable]

CAN Bus HTTP Server

optional arguments:
  -h, --help            Show help message and exit
  --test, -t            Run in test mode with simulated CAN traffic
  --port PORT, -p PORT  Server port (default: 8080)
  --host HOST           Server host (default: 0.0.0.0)
  --channel CHANNEL, -c CHANNEL
                        CAN device channel/index (default: 0)
  --baudrate BAUDRATE, -b BAUDRATE
                        CAN baudrate in bps (default: 500000)
  --auto-connect        Automatically connect to CAN bus on startup
  --driver, -d          CAN driver (canable, waveshare, pcan)
  --bluetooth           Enable Bluetooth RFCOMM server
  --bt-channel          Bluetooth RFCOMM channel (1-30, default: 1)
  --bt-discoverable     Make adapter discoverable on startup
```

---

## Bluetooth RFCOMM/SPP Protocol

The server supports Bluetooth Serial Port Profile (SPP) for wireless communication. This allows clients to connect via Bluetooth and use the same functionality as the HTTP API.

### Overview

| Property | Value |
|----------|-------|
| Profile | Serial Port Profile (SPP) |
| UUID | `00001101-0000-1000-8000-00805F9B34FB` |
| Default Channel | 1 |
| Service Name | `TREV-CAN-Server` |
| Protocol | JSON over serial (newline-delimited) |

### Server Requirements (Raspberry Pi)

```bash
# Install system packages
sudo apt install bluetooth bluez libbluetooth-dev

# Install Python package
pip install pybluez

# Enable and start Bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

### Starting the Server with Bluetooth

```bash
# Enable Bluetooth server
python can_server.py --bluetooth

# Enable Bluetooth with discoverable mode
python can_server.py --bluetooth --bt-discoverable

# Bluetooth with specific channel
python can_server.py --bluetooth --bt-channel 3

# Full example with CAN
python can_server.py --driver waveshare --bluetooth --bt-discoverable --auto-connect
```

---

### Pairing Process

Before a client can connect, it must be paired with the Raspberry Pi. This is a one-time process per device.

#### Method 1: Using bluetoothctl (Recommended)

On the Raspberry Pi:

```bash
# Start bluetoothctl
bluetoothctl

# Enable discovery and pairing
[bluetooth]# power on
[bluetooth]# discoverable on
[bluetooth]# pairable on
[bluetooth]# agent on
[bluetooth]# default-agent

# Wait for device to appear, then trust and pair
# Replace XX:XX:XX:XX:XX:XX with client's MAC address
[bluetooth]# pair XX:XX:XX:XX:XX:XX
[bluetooth]# trust XX:XX:XX:XX:XX:XX

# Exit
[bluetooth]# quit
```

On the client (PC or Android):
1. Open Bluetooth settings
2. Scan for devices
3. Find "raspberrypi" (or your Pi's hostname)
4. Click to pair
5. Accept pairing on both devices

#### Method 2: From Android

1. On Raspberry Pi, run `bluetoothctl` and enable discoverable mode
2. On Android: Settings → Bluetooth → Scan
3. Tap the Raspberry Pi device
4. Accept pairing on the Pi: `[bluetooth]# yes`
5. The devices are now paired

#### Verify Pairing

```bash
# List paired devices
bluetoothctl paired-devices

# Should show:
# Device XX:XX:XX:XX:XX:XX DeviceName
```

---

### Bluetooth JSON Protocol

The Bluetooth server uses newline-delimited JSON messages. Each command/response is a single JSON object followed by `\n`.

#### Request Format

```json
{"cmd": "command_name", "params": {...}}
```

#### Response Format

```json
{"success": true, "data": {...}}
```

or

```json
{"success": false, "error": "Error message"}
```

---

### Bluetooth Commands

#### `ping` - Connection Test

**Request:**
```json
{"cmd": "ping"}
```

**Response:**
```json
{"success": true, "pong": true, "timestamp": 1704556800.123}
```

---

#### `get_status` - Server Status

**Request:**
```json
{"cmd": "get_status"}
```

**Response:**
```json
{
  "success": true,
  "status": {
    "connected": true,
    "mode": "hardware",
    "buffer_size": 42,
    "buffer_capacity": 5000,
    "bluetooth_clients": 1,
    "channel": 0,
    "baudrate": "BAUD_500K",
    "timestamp": 1704556800.123
  }
}
```

---

#### `get_devices` - List CAN Devices

**Request:**
```json
{"cmd": "get_devices"}
```

**Response:**
```json
{
  "success": true,
  "mode": "hardware",
  "devices": [
    {"index": 0, "name": "can0", "description": "SocketCAN interface"}
  ]
}
```

---

#### `connect` - Connect to CAN Bus

**Request:**
```json
{"cmd": "connect", "params": {"channel": 0, "baudrate": "BAUD_500K"}}
```

**Response:**
```json
{"success": true, "message": "Connected to channel 0 at BAUD_500K"}
```

---

#### `disconnect` - Disconnect from CAN Bus

**Request:**
```json
{"cmd": "disconnect"}
```

**Response:**
```json
{"success": true, "message": "Disconnected from CAN bus"}
```

---

#### `get_messages` - Get CAN Messages

**Request:**
```json
{"cmd": "get_messages", "params": {"count": 50, "filter_id": 192}}
```

Parameters:
- `count` (optional): Maximum messages to return (default: 100)
- `filter_id` (optional): Filter by CAN ID

**Response:**
```json
{
  "success": true,
  "count": 2,
  "messages": [
    {
      "id": 192,
      "id_hex": "0xC0",
      "timestamp": 1704556800.123,
      "dlc": 8,
      "message_name": "EngineRPM",
      "signals": [{"name": "RPM", "value": 3000, "unit": "rpm"}],
      "data_hex": "B8 0B 00 00 00 00 00 00"
    }
  ]
}
```

---

#### `send_message` - Send CAN Message

**Request:**
```json
{
  "cmd": "send_message",
  "params": {
    "id": 291,
    "data": [1, 2, 3, 4, 5, 6, 7, 8],
    "extended": false
  }
}
```

Alternative data format (hex string):
```json
{"cmd": "send_message", "params": {"id": "0x123", "data": "01 02 03 04"}}
```

**Response:**
```json
{"success": true, "message": "Sent message 0x123 with 4 bytes"}
```

---

#### `send_batch` - Send Multiple Messages

**Request:**
```json
{
  "cmd": "send_batch",
  "params": {
    "messages": [
      {"id": 291, "data": [1, 2, 3, 4]},
      {"id": 292, "data": [5, 6, 7, 8]}
    ]
  }
}
```

**Response:**
```json
{"success": true, "sent": 2, "failed": 0}
```

---

#### `clear_messages` - Clear Message Buffer

**Request:**
```json
{"cmd": "clear_messages"}
```

**Response:**
```json
{"success": true, "message": "Message buffer cleared"}
```

---

#### `load_dbc` - Load DBC File

**Request:**
```json
{
  "cmd": "load_dbc",
  "params": {
    "content": "VERSION \"\"\n\nNS_ :\n\nBS_:\n\nBU_:\n\nBO_ 192 EngineRPM: 8 Vector__XXX\n SG_ RPM : 0|16@1+ (1,0) [0|8000] \"rpm\" Vector__XXX"
  }
}
```

**Response:**
```json
{"success": true, "message": "DBC loaded successfully", "message_count": 1}
```

---

#### `unload_dbc` - Unload DBC File

**Request:**
```json
{"cmd": "unload_dbc"}
```

**Response:**
```json
{"success": true, "message": "DBC unloaded"}
```

---

#### `subscribe` - Subscribe to Real-time Messages

Start receiving streaming messages.

**Request:**
```json
{"cmd": "subscribe"}
```

**Response:**
```json
{"success": true, "message": "Subscribed to message stream"}
```

After subscribing, you'll receive periodic message events:
```json
{
  "event": "messages",
  "count": 5,
  "messages": [
    {"id": 192, "id_hex": "0xC0", "data_hex": "...", ...},
    ...
  ]
}
```

---

#### `unsubscribe` - Stop Streaming

**Request:**
```json
{"cmd": "unsubscribe"}
```

**Response:**
```json
{"success": true, "message": "Unsubscribed from message stream"}
```

---

### Python Client Example

```python
from bluetooth_client_example import BluetoothCANClient

# Create client
client = BluetoothCANClient()

# Discover servers
services = client.discover_services()
for svc in services:
    print(f"{svc['name']} at {svc['address']}")

# Connect
client.connect("XX:XX:XX:XX:XX:XX", port=1)

# Get status
status = client.get_status()
print(status)

# Send a message
client.send_message(0x123, [0x01, 0x02, 0x03, 0x04])

# Get messages
messages = client.get_messages(count=10)
for msg in messages['messages']:
    print(f"{msg['id_hex']}: {msg['data_hex']}")

# Subscribe to streaming
def on_message(response):
    for msg in response['messages']:
        print(f"Received: {msg['id_hex']}")

client.set_message_callback(on_message)
client.subscribe()

# ... later
client.unsubscribe()
client.disconnect()
```

---

### Android Integration (Kotlin)

```kotlin
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.util.UUID

class BluetoothCANClient {
    private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private var socket: BluetoothSocket? = null
    private var reader: BufferedReader? = null
    private var writer: OutputStreamWriter? = null
    
    fun connect(device: BluetoothDevice): Boolean {
        return try {
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
            socket?.connect()
            reader = BufferedReader(InputStreamReader(socket?.inputStream))
            writer = OutputStreamWriter(socket?.outputStream)
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }
    
    fun disconnect() {
        socket?.close()
        socket = null
    }
    
    fun sendCommand(cmd: String, params: Map<String, Any>? = null): String? {
        val json = buildString {
            append("{\"cmd\":\"$cmd\"")
            if (params != null) {
                append(",\"params\":")
                append(JSONObject(params).toString())
            }
            append("}\n")
        }
        
        writer?.write(json)
        writer?.flush()
        
        return reader?.readLine()
    }
    
    // High-level methods
    fun getStatus() = sendCommand("get_status")
    fun getMessages(count: Int = 100) = sendCommand("get_messages", mapOf("count" to count))
    fun sendMessage(id: Int, data: List<Int>) = sendCommand("send_message", 
        mapOf("id" to id, "data" to data))
    fun subscribe() = sendCommand("subscribe")
    fun unsubscribe() = sendCommand("unsubscribe")
}

// Usage
val adapter = BluetoothAdapter.getDefaultAdapter()
val device = adapter.bondedDevices.find { it.name == "raspberrypi" }

device?.let {
    val client = BluetoothCANClient()
    if (client.connect(it)) {
        val status = client.getStatus()
        println(status)
        
        // Subscribe for streaming in a coroutine
        client.subscribe()
        
        // Read messages in a loop
        while (isActive) {
            val line = reader.readLine()
            // Parse JSON and handle messages
        }
        
        client.disconnect()
    }
}
```

---

### Android Integration (Java)

```java
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import org.json.JSONObject;
import java.io.*;
import java.util.UUID;

public class BluetoothCANClient {
    private static final UUID SPP_UUID = 
        UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    
    private BluetoothSocket socket;
    private BufferedReader reader;
    private PrintWriter writer;
    
    public boolean connect(BluetoothDevice device) {
        try {
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID);
            socket.connect();
            reader = new BufferedReader(
                new InputStreamReader(socket.getInputStream()));
            writer = new PrintWriter(
                new OutputStreamWriter(socket.getOutputStream()), true);
            return true;
        } catch (IOException e) {
            e.printStackTrace();
            return false;
        }
    }
    
    public void disconnect() {
        try {
            if (socket != null) socket.close();
        } catch (IOException e) {}
    }
    
    public String sendCommand(String cmd, JSONObject params) {
        try {
            JSONObject request = new JSONObject();
            request.put("cmd", cmd);
            if (params != null) request.put("params", params);
            
            writer.println(request.toString());
            return reader.readLine();
        } catch (Exception e) {
            return null;
        }
    }
    
    public String getStatus() {
        return sendCommand("get_status", null);
    }
    
    public String getMessages(int count) throws Exception {
        JSONObject params = new JSONObject();
        params.put("count", count);
        return sendCommand("get_messages", params);
    }
    
    public String sendCANMessage(int id, int[] data) throws Exception {
        JSONObject params = new JSONObject();
        params.put("id", id);
        params.put("data", new JSONArray(data));
        return sendCommand("send_message", params);
    }
}
```

---

## Troubleshooting

### Server Won't Start

1. **Port in use**: Try a different port with `--port 8081`
2. **Missing dependencies**: Install with `pip install python-can pyusb`

### Can't Connect to Hardware

1. Verify device is connected with `python CANable_Driver.py`
2. Check USB permissions (Linux: add user to plugdev group)
3. Ensure libusb-1.0.dll is present (Windows)
4. Use `--test` mode to verify server works

### Messages Not Receiving

1. Check `GET /api/status` shows `connected: true`
2. Verify CAN bus has traffic (use test mode to generate)
3. Check filter_id parameter isn't filtering out messages
4. Increase buffer with more frequent polling

### Bluetooth Issues

1. **"Bluetooth not available"**: Install pybluez and system packages
2. **Connection refused**: Ensure devices are paired first
3. **Device not found**: Make Pi discoverable with `--bt-discoverable`
4. **Permission denied**: Run with sudo or add user to bluetooth group:
   ```bash
   sudo usermod -a -G bluetooth $USER
   ```
5. **Pairing fails**: Remove and re-pair:
   ```bash
   bluetoothctl remove XX:XX:XX:XX:XX:XX
   bluetoothctl pair XX:XX:XX:XX:XX:XX
   ```
