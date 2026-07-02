#include <stdio.h>
#include "types.h"
#include "bsw/bsw_manager.h"
#include "drivers/driver.h"
#include "comm/sensor.h"

extern int g_system_ticks;
extern Status g_last_status;
static Point g_point;

static void task_sensor_poll(void) {
    SensorData reading;
    Status st = sensor_read(&reading);
    if (st == STATUS_OK) {
#ifdef ENABLE_SENSOR_DEBUG
        printf("Sensor: raw=%d temp=%.2f\n", reading.raw_adc, reading.temperature_c);
#endif
    } else {
        g_last_status = st;
    }
}

static void task_tick_update(void) {
#ifndef DISABLE_TICK_COUNTER
    g_system_ticks++;
#endif
}

static void task_spi_exchange(void) {
    SpiHandle spi;
    BYTE tx_buf[4] = {0x01, 0x02, 0x03, 0x04};
    BYTE rx_buf[4];

#if defined(USE_HW_SPI)
    spi_init(&spi, 10, 1000000);
    spi_set_mode(&spi, SPI_MODE_0);
    spi_transfer(&spi, tx_buf, rx_buf, sizeof(tx_buf));
#else
    (void)spi;
    (void)tx_buf;
    (void)rx_buf;
#endif
}

int main(void) {
    TaskDesc sensor_task = {"sensor", task_sensor_poll, 100, 1};
    TaskDesc tick_task = {"tick", task_tick_update, 1, 1};
    TaskDesc spi_task = {"spi_xfer", task_spi_exchange, 50, 1};

    /* Initialize all subsystems. */
    system_init();
    bsw_init();

    /* Set sensor calibration. */
    CalibData cal = {0.5f, 2.0f, 10};
    sensor_calibrate(&cal);

    sensor_set_direction(DIR_EAST);

    /* Register and run tasks. */
    bsw_register_task(&tick_task);
    bsw_register_task(&sensor_task);
#if defined(ENABLE_SPI_TASK) || defined(HAS_SPI_HW)
    bsw_register_task(&spi_task);
#endif

    while (1) {
        bsw_run();
#ifdef WATCHDOG_ENABLED
        bsw_kick_watchdog();
#endif
    }

    return 0;
}

static TaskDesc dummy(PowerState e){
    TaskDesc ret;
    int z = g_point.x;
    return ret;
}