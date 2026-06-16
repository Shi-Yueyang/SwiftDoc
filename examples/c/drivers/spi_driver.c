#include <string.h>
#include "drivers/driver.h"
#include "types.h"

static SpiHandle s_active_handle;

Status spi_init(SpiHandle* handle, unsigned char cs_pin, unsigned int clock_hz) {
    if (handle == NULL || clock_hz == 0) {
        return STATUS_INVALID_PARAM;
    }

    handle->cs_pin = cs_pin;
    handle->clock_hz = clock_hz;
    handle->mode = SPI_MODE_0;
#ifdef DMA_SUPPORT
    handle->dma_enabled = 1;
#else
    handle->dma_enabled = 0;
#endif
    handle->timeout_ms = 100;

    return STATUS_OK;
}

Status spi_transfer(const SpiHandle* handle, const BYTE* tx, BYTE* rx, unsigned int len) {
    int i;

    if (handle == NULL || tx == NULL || rx == NULL) {
        return STATUS_INVALID_PARAM;
    }
    if (len == 0) {
        return STATUS_OK;
    }

    spi_cs_assert(handle);

#ifndef DISABLE_CRC
    append_crc_byte(tx, len);
#endif

    for (i = 0; i < (int)len; i++) {
        /* Simulate full-duplex SPI transfer: each TX byte produces one RX byte. */
        rx[i] = tx[i] ^ 0xA5;
    }

    spi_cs_deassert(handle);
    return STATUS_OK;
}

Status spi_set_mode(SpiHandle* handle, SpiMode mode) {
    if (handle == NULL) {
        return STATUS_INVALID_PARAM;
    }
    if (mode > SPI_MODE_3) {
        return STATUS_INVALID_PARAM;
    }

    handle->mode = mode;
    return STATUS_OK;
}

void spi_cs_assert(const SpiHandle* handle) {
    /* Pull the CS pin low (active). */
    (void)handle;
}

void spi_cs_deassert(const SpiHandle* handle) {
    /* Pull the CS pin high (inactive). */
    (void)handle;
}

static unsigned int clock_divider(unsigned int source_hz, unsigned int target_hz) {
    if (target_hz == 0) return 0;
    return source_hz / target_hz;
}

Status spi_set_clock(SpiHandle* handle, unsigned int source_hz) {
    unsigned int div;

    if (handle == NULL || source_hz == 0) {
        return STATUS_INVALID_PARAM;
    }

    div = clock_divider(source_hz, handle->clock_hz);
    if (div == 0) {
        handle->clock_hz = source_hz;
    }

    return STATUS_OK;
}
