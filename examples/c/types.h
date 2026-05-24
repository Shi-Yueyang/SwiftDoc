#ifndef TYPES_H
#define TYPES_H

/* Status codes returned by most functions. */
typedef enum {
    STATUS_OK = 0,
    STATUS_ERROR = 1,
    STATUS_TIMEOUT = 2,
    STATUS_BUSY = 3,
    STATUS_INVALID_PARAM = 4,
} Status;

/* A 2D coordinate pair. */
typedef struct {
    int x;
    int y;
} Point;

/* Configuration for UART communication. */
typedef struct {
    unsigned int baud_rate;
    unsigned char data_bits;
    unsigned char stop_bits;
    unsigned char parity;
} UartConfig;

/* Union for sensor readings — only one type is valid at a time. */
typedef union {
    int raw_adc;
    float temperature_c;
    unsigned char pressure_kpa;
} SensorData;

/* Generic byte and word aliases. */
typedef unsigned char BYTE;
typedef unsigned short WORD;
typedef BYTE DEVICE_ID[8];

/* Extern declarations for global state variables. */
extern int g_system_ticks;
extern Status g_last_status;
extern UartConfig g_default_uart;

#endif /* TYPES_H */
