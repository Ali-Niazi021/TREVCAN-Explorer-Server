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
      "data_hex": null
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
| data_hex | string/null | Raw hex data (null if decoded) |

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
                     [--no-ssl] [--cert CERT] [--key KEY] [--auto-connect]

CAN Bus HTTPS Server

optional arguments:
  -h, --help            Show help message and exit
  --test, -t            Run in test mode with simulated CAN traffic
  --port PORT, -p PORT  Server port (default: 8443)
  --host HOST           Server host (default: 0.0.0.0)
  --channel CHANNEL, -c CHANNEL
                        CAN device channel/index (default: 0)
  --baudrate BAUDRATE, -b BAUDRATE
                        CAN baudrate in bps (default: 500000)
  --no-ssl              Disable SSL/TLS (use HTTP instead of HTTPS)
  --cert CERT           SSL certificate file (default: server.crt)
  --key KEY             SSL private key file (default: server.key)
  --auto-connect        Automatically connect to CAN bus on startup
```

---

## Troubleshooting

### Server Won't Start

1. **Port in use**: Try a different port with `--port 8444`
2. **SSL error**: Use `--no-ssl` or check certificate files
3. **Missing dependencies**: Install with `pip install python-can pyusb`

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

### SSL Certificate Issues

1. Client must accept self-signed certificates
2. Use `verify=False` in Python requests
3. Use `-k` flag with curl
4. Or install certificate as trusted
