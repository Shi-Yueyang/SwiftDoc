#include <stdio.h>
#include <string.h>
#include "types.h"
#include "comm/sensor.h"

static SensorData s_sensor_value = {0};
static Direction s_current_dir = DIR_STOP;
static CalibData s_calib = {1.0f, 1.0f, 0};

void sensor_init(UartConfig cfg) {
    /* Initialize the physical sensor with the given UART config. */
    s_sensor_value.raw_adc = 0;
    s_current_dir = DIR_STOP;
}

Status sensor_read(SensorData* out) {
    if (out == NULL) {
        return STATUS_INVALID_PARAM;
    }

    /* Simulate ADC reading. */
    s_sensor_value.raw_adc = (s_sensor_value.raw_adc + 73) % 4096;
    s_sensor_value.temperature_c = (float)s_sensor_value.raw_adc * 0.0125f;

    memcpy(out, &s_sensor_value, sizeof(SensorData));
    return STATUS_OK;
}

Status sensor_calibrate(const CalibData* cal) {
    if (cal == NULL) {
        return STATUS_INVALID_PARAM;
    }

    s_calib.offset = cal->offset;
    s_calib.gain = cal->gain;
    s_calib.zero_point = cal->zero_point;

    return STATUS_OK;
}

void sensor_set_direction(Direction dir) {
    s_current_dir = dir;
}

static int validate_calibration(void) {
    if (s_calib.gain <= 0.0f) {
        return 0;
    }
    if (s_calib.zero_point < -100 || s_calib.zero_point > 100) {
        return 0;
    }
    return 1;
}

Status sensor_self_test(void) {
    if (!validate_calibration()) {
        return STATUS_ERROR;
    }
    return STATUS_OK;
}
