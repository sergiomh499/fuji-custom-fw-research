#include <stdint.h>

/* Fuji X-mount lens communication MMIO (EXR Processor II). */
#define LENS_COMM_BASE        0x40021000u
#define LENS_STATUS_REG       (LENS_COMM_BASE + 0x00u)
#define LENS_CMD_REG          (LENS_COMM_BASE + 0x04u)
#define LENS_ARG0_REG         (LENS_COMM_BASE + 0x08u)
#define LENS_ARG1_REG         (LENS_COMM_BASE + 0x0cu)

/* Lens command codes (reverse-engineered from START_NEGO block). */
#define CMD_LENS_MOVE_STEP    0x12u
#define LENS_GET_POSITION     0x21u
#define LENS_SET_POSITION     0x23u
#define LENS_STATUS_READY     0x01u

/* Snap focus presets (millimetres; 0 = infinity). */
static const int32_t SNAP_TARGETS_MM[] = { 1500, 2000, 5000, 0 };
static const uint32_t NUM_SNAP_TARGETS = 4;

volatile uint32_t snap_focus_index = 0;
volatile uint32_t snap_focus_last_status = 0;

static void lens_wait_ready(void)
{
    volatile uint32_t *st = (volatile uint32_t *)LENS_STATUS_REG;
    uint32_t guard = 100000u;
    while (guard-- && !(*st & LENS_STATUS_READY)) {
        /* busy-wait for lens controller ready */
    }
}

static void lens_send(uint32_t cmd, uint32_t a0, uint32_t a1)
{
    lens_wait_ready();
    *(volatile uint32_t *)LENS_ARG1_REG = a1;
    *(volatile uint32_t *)LENS_ARG0_REG = a0;
    *(volatile uint32_t *)LENS_CMD_REG  = cmd;
}

/* Convert a target distance (mm) to motor steps using the X-mount
 * focus scale published in the firmware strings (DISTANCE: %n). */
static int32_t distance_to_steps(int32_t distance_mm)
{
    if (distance_mm <= 0) {
        return 0x7fffffff; /* infinity sentinel */
    }
    switch (distance_mm) {
        case 1500: return 667;
        case 2000: return 500;
        case 5000: return 200;
        default:   return 0x7fffffff; /* infinity sentinel */
    }
}

int snap_focus_to_index(uint32_t idx)
{
    if (idx >= NUM_SNAP_TARGETS) {
        return -1;
    }
    int32_t steps = distance_to_steps(SNAP_TARGETS_MM[idx]);
    lens_send(CMD_LENS_MOVE_STEP, (uint32_t)steps, 0u);
    lens_send(LENS_SET_POSITION, (uint32_t)steps, 0u);
    snap_focus_index = idx;
    snap_focus_last_status = *(volatile uint32_t *)LENS_STATUS_REG;
    return 0;
}

/* Payload entry: cycle to next snap focus preset on trigger. */
__attribute__((section(".text.entry"), naked)) void _start(void)
{
    __asm__ volatile (
        "push    {r4-r11, lr}\n"
        "bl      fuji_payload_main\n"
        "pop     {r4-r11, pc}\n"
    );
}

int fuji_payload_main(void)
{
    uint32_t next = snap_focus_index + 1u;
    if (next >= NUM_SNAP_TARGETS) next = 0u;
    return snap_focus_to_index(next);
}
