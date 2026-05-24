#ifndef DRIVER_H
#define DRIVER_H

#include "types.h"

/*
 * SPI Driver — handles SPI bus read/write operations.
 * Supports both blocking and DMA transfer modes.
 */

/* GPIO pin descriptor. */
typedef unsigned char PinState;

typedef enum {
    GPIO_LOW = 0,
    GPIO_HIGH = 1,
} GpioLevel;

typedef enum {
    SPI_MODE_0, /* CPOL=0, CPHA=0 */
    SPI_MODE_1, /* CPOL=0, CPHA=1 */
    SPI_MODE_2, /* CPOL=1, CPHA=0 */
    SPI_MODE_3, /* CPOL=1, CPHA=1 */
} SpiMode;

/* SPI device handle. */
typedef struct {
    unsigned char cs_pin;
    unsigned int  clock_hz;
    SpiMode       mode;
    unsigned char dma_enabled;
    unsigned int  timeout_ms;
} SpiHandle;

Status spi_init(SpiHandle* handle, unsigned char cs_pin, unsigned int clock_hz);
Status spi_transfer(const SpiHandle* handle, const BYTE* tx, BYTE* rx, unsigned int len);
Status spi_set_mode(SpiHandle* handle, SpiMode mode);
void spi_cs_assert(const SpiHandle* handle);
void spi_cs_deassert(const SpiHandle* handle);

#endif /* DRIVER_H */
