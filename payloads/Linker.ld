/* Linker script for ARM32 bare-metal payloads */
ENTRY(_start)

SECTIONS
{
    . = 0x00000000;

    .text : {
        *(.text.entry)
        *(.text*)
        *(.glue_7)
        *(.glue_7t)
    }

    .rodata : {
        *(.rodata*)
    }

    .data : {
        *(.data*)
    }

    .bss : {
        *(.bss*)
        *(COMMON)
    }

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
    }
}
