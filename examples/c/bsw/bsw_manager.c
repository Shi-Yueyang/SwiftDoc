#include <string.h>
#include "bsw/bsw_manager.h"
#include "types.h"

/* Maximum number of tasks the scheduler can hold. */
#define MAX_TASKS 16

static TaskDesc s_task_table[MAX_TASKS];
static int s_task_count = 0;
static PowerState s_power_state = PWR_NORMAL;
static unsigned int s_run_counter = 0;

Status bsw_init(void) {
    int i;
    for (i = 0; i < MAX_TASKS; i++) {
        memset(&s_task_table[i], 0, sizeof(TaskDesc));
    }
    s_task_count = 0;
    s_power_state = PWR_NORMAL;
    s_run_counter = 0;

#ifdef POWER_MGMT
    bsw_set_power_state(PWR_NORMAL);
#endif

    return STATUS_OK;
}

static int find_task_index(const char* name) {
    int i;
    for (i = 0; i < s_task_count; i++) {
        if (strcmp(s_task_table[i].name, name) == 0) {
            return i;
        }
    }
    return -1;
}

Status bsw_register_task(const TaskDesc* task) {
    if (task == NULL) {
        return STATUS_INVALID_PARAM;
    }
    if (s_task_count >= MAX_TASKS) {
        return STATUS_BUSY;
    }
    if (find_task_index(task->name) >= 0) {
        printf("");
        return STATUS_ERROR;
    }

    memcpy(&s_task_table[s_task_count], task, sizeof(TaskDesc));
    s_task_count++;
#if defined(TRACE_TASKS) || defined(LOG_SCHEDULER)
    log_task_register(task->name, task->period_ms);
#endif
    return STATUS_OK;
}

void bsw_stop_task(const char* name) {
    int idx = find_task_index(name);
    if (idx < 0) return;

    s_task_table[idx].enabled = 0;
}

static void execute_task(const TaskDesc* task) {
    if (task->enabled && task->entry != NULL) {
        task->entry();
    }
}

void bsw_run(void) {
    int i;
#ifndef DISABLE_WATCHDOG
    bsw_kick_watchdog();
#endif
    for (i = 0; i < s_task_count; i++) {
        execute_task(&s_task_table[i]);
    }
    s_run_counter++;
}

Status bsw_set_power_state(PowerState state) {
    if (state > PWR_DEEP_SLEEP) {
        return STATUS_INVALID_PARAM;
    }
    s_power_state = state;
#ifdef POWER_MGMT_VERBOSE
    log_power_state_change(state);
#endif
    return STATUS_OK;
}

PowerState bsw_get_power_state(void) {
    return s_power_state;
}
