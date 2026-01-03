# TREV-Explorer-Server

Simple HTTP server to interface with local CAN hardware over network

## Supported Hardware

| Adapter                         | Interface  | Driver Flag           | Notes                                      |
| ------------------------------- | ---------- | --------------------- | ------------------------------------------ |
| CANable 2.0                     | gs_usb     | `--driver canable`    | Default. USB-to-CAN adapter                |
| PEAK PCAN-USB                   | PCAN       | `--driver pcan`       | PEAK-System USB-to-CAN adapter             |
| Waveshare 2-CH Isolated CAN HAT | SocketCAN  | `--driver waveshare`  | Raspberry Pi HAT, requires SPI + overlays  |
