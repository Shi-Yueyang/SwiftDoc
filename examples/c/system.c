#include <stdio.h>
#include "types.h"
#include "comm/sensor.h"

/* Global state variables */
int g_system_ticks = 0;
Status g_last_status = STATUS_OK;
UartConfig g_default_uart = {115200, 8, 1, 0};

/* Static counters — visible only in this translation unit */
static int s_read_count = 0;
static int s_error_count = 0;
static Point s_last_position = {0, 0};

Status system_init(void) {
    int i;
    UartConfig local_cfg;

    local_cfg.baud_rate = 115200;
    local_cfg.data_bits = 8;
    local_cfg.stop_bits = 1;
    local_cfg.parity = 0;

    g_default_uart = local_cfg;
#ifdef DEBUG_INIT_SEQUENCE
    printf("System initializing with baud=%d\n", local_cfg.baud_rate);
#endif
    sensor_init(local_cfg);

    g_system_ticks = 0;
    s_read_count = 0;
    s_error_count = 0;

    g_last_status = STATUS_OK;
    return g_last_status;
}

void system_tick(void) {
    g_system_ticks++;
}

Status system_get_reading(SensorData* out) {
    Status st;
    if (out == NULL) {
        g_last_status = STATUS_INVALID_PARAM;
        return STATUS_INVALID_PARAM;
    }

    st = sensor_read(out);
    if (st == STATUS_OK) {
        s_read_count++;
#if defined(ENABLE_TELEMETRY) || defined(LOG_READINGS)
        log_sensor_reading(out);
#endif
        g_last_status = STATUS_OK;
    } else {
        s_error_count++;
        g_last_status = st;
    }
    return g_last_status;
}

static void update_position(int dx, int dy) {
    s_last_position.x += dx;
    s_last_position.y += dy;
}

Status system_move_to(Point target) {
    int dx = target.x - s_last_position.x;
    int dy = target.y - s_last_position.y;

    if (dx == 0 && dy == 0) {
        return STATUS_OK;
    }

    update_position(dx, dy);
#ifndef DISABLE_POSITION_LOG
    log_position_update(dx, dy);
#endif
    g_last_status = STATUS_OK;
    return STATUS_OK;
}

int system_get_read_count(void) {
    return s_read_count;
}

int system_get_error_count(void) {
    return s_error_count;
}
