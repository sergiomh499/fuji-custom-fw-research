#include <stdint.h>

/* OSD framebuffer metadata (X-T10 v1.31).
 *   OSD debug routine:          0x007f9c1c
 *   Display buffer descriptor:  0x01b59bd4 (holds pointer to live buffer)
 *   Resolution:                 640x480, 307200 bytes per buffer
 *
 * Failure mitigation: this payload is a VOLATILE-RAM-only write behind the
 * secondary cold-hook trampoline; a fault never touches flash.
 *   docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking
 *   Volatile/PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
 *   Firmware repacking recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
 *   Hardware flashing recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery
 */

#define OSD_FB_PTR_ADDR   0x01B59BD4u
#define OSD_WIDTH         640u
#define OSD_HEIGHT        480u
#define OSD_BYTES         307200u

static void draw_grid(uint8_t *fb)
{
    /* 1px border */
    for (uint32_t x = 0; x < OSD_WIDTH; x++) {
        fb[x] = 0xFF;
        fb[(OSD_HEIGHT - 1) * OSD_WIDTH + x] = 0xFF;
    }
    for (uint32_t y = 0; y < OSD_HEIGHT; y++) {
        fb[y * OSD_WIDTH] = 0xFF;
        fb[y * OSD_WIDTH + (OSD_WIDTH - 1)] = 0xFF;
    }
    /* thirds */
    for (uint32_t y = 0; y < OSD_HEIGHT; y++) {
        fb[y * OSD_WIDTH + OSD_WIDTH / 3] = 0xAA;
        fb[y * OSD_WIDTH + (2 * OSD_WIDTH / 3)] = 0xAA;
    }
    for (uint32_t x = 0; x < OSD_WIDTH; x++) {
        fb[OSD_HEIGHT / 3 * OSD_WIDTH + x] = 0xAA;
        fb[2 * OSD_HEIGHT / 3 * OSD_WIDTH + x] = 0xAA;
    }
}

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
    uint32_t fb_addr = *(volatile uint32_t *)OSD_FB_PTR_ADDR;
    if (fb_addr == 0u) {
        return -1;
    }
    uint8_t *fb = (uint8_t *)fb_addr;
    draw_grid(fb);
    return 0;
}
