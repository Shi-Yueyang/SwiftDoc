#ifndef BSW_MANAGER_H
#define BSW_MANAGER_H

#include "types.h"

/*
 * Basic Software Manager — handles task scheduling and power state.
 */

typedef enum {
    PWR_NORMAL,
    PWR_LOW,
    PWR_SLEEP,
    PWR_DEEP_SLEEP,
} PowerState;

/* Task descriptor used in the scheduler table. */
typedef struct {
    char name[16];
    void (*entry)(void);
    unsigned int period_ms;
    unsigned char enabled;
} TaskDesc;

Status bsw_init(void);
void bsw_run(void);
Status bsw_set_power_state(PowerState state);
PowerState bsw_get_power_state(void);
Status bsw_register_task(const TaskDesc* task);
void bsw_stop_task(const char* name);

#endif /* BSW_MANAGER_H */
