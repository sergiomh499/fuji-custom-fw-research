.syntax unified
.arch armv7-a
.arm

.section .text.entry, "ax"
.global _start
.type _start, %function

_start:
    push    {r4-r11, lr}
    bl      fuji_payload_main
    pop     {r4-r11, pc}

.size _start, . - _start
