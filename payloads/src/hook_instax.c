#include <stdint.h>

/* In-memory test flag toggled by the safe menu hook. */
volatile uint32_t fuji_instax_hook_flag = 0;

/*
 * Safe secondary-menu hook template.
 * Intercepts a user-triggered menu (e.g. Instax print / photo properties)
 * without touching early boot or sensor hardware.
 */
int fuji_payload_main(void)
{
    fuji_instax_hook_flag = 1;
    return 0; /* mock success status */
}
