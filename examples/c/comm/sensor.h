#ifndef SENSOR_H
#define SENSOR_H

#include "types.h"

/*
 * Direction enumeration for motor or flow control.
 * DIR_STOP means the device is idle.
 */
typedef enum {
    DIR_NORTH,
    DIR_SOUTH,
    DIR_EAST,
    DIR_WEST,
    DIR_STOP = 0xFF
} Direction;

/* Calibration parameters stored in EEPROM. */
typedef struct {
    float offset;
    float gain;
    int zero_point;
} CalibData;

void sensor_init(UartConfig cfg);
Status sensor_read(SensorData* out);
Status sensor_calibrate(const CalibData* cal);
void sensor_set_direction(Direction dir);

#endif /* SENSOR_H */
