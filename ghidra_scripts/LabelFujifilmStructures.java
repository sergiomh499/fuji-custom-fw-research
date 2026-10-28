// LabelFujifilmStructures.java - Ghidra Java post-script for Fujifilm firmware
//
//@category Fujifilm

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.mem.Memory;

import java.util.HashMap;
import java.util.Map;

public class LabelFujifilmStructures extends GhidraScript {

    // Virtual address mapping delta for Fujifilm X-T10
    public static final long VIRTUAL_DELTA = 0x0135FFB8L;

    private static final Map<Long, String> LABELS = new HashMap<>();

    static {
        // Film Simulation DSP tokens (physical offsets)
        LABELS.put(0x0024FB1BL, "FSIM_TOKEN_ILM");
        LABELS.put(0x0024FB23L, "FSIM_TOKEN_ASTIA");
        LABELS.put(0x0024FB2CL, "FSIM_TOKEN_BW");
        LABELS.put(0x0024FB3CL, "FSIM_TOKEN_CHROME");
        LABELS.put(0x0024FB49L, "FSIM_TOKEN_NEG_H");
        LABELS.put(0x0024FB55L, "FSIM_TOKEN_PROVIA");
        LABELS.put(0x0024FB5EL, "FSIM_TOKEN_SEPIA");
        LABELS.put(0x0024FB64L, "FSIM_TOKEN_VELVIA");

        // UI State Machine Menu array
        LABELS.put(0x00805DC0L, "UI_MENU_TABLE_BASE");
        LABELS.put(0x0080894EL, "UI_MENU_FSIMMENU");
        LABELS.put(0x008089B2L, "UI_MENU_CUSTOMMENU");
        LABELS.put(0x0080891CL, "UI_MENU_AFMENU");
        LABELS.put(0x008088EAL, "UI_MENU_AEMENU");

        // Embedded SQLite tables
        LABELS.put(0x00BF34F0L, "SQLITE_TABLE_PT");
        LABELS.put(0x00BF3548L, "SQLITE_TABLE_FINF");
        LABELS.put(0x00BF4454L, "SQLITE_TABLE_FCT");
    }

    @Override
    public void run() throws Exception {
        int labelCount = 0;
        int pointerCount = 0;
        Memory mem = currentProgram.getMemory();

        println("========================================================");
        println(" Labeling Fujifilm X-T10 Structures & Virtual Addresses ");
        println("========================================================");

        for (Map.Entry<Long, String> entry : LABELS.entrySet()) {
            long phys = entry.getKey();
            long virt = phys + VIRTUAL_DELTA;
            String name = entry.getValue();

            // 1. Label physical address
            Address physAddr = toAddr(phys);
            try {
                createLabel(physAddr, name, true, SourceType.USER_DEFINED);
                createBookmark(physAddr, "Analysis", name);
                setPreComment(physAddr, String.format("Fujifilm: %s (Virt: 0x%08X)", name, virt));
                labelCount++;
            } catch (Exception e) {
                println(String.format("Warning labeling 0x%08X: %s", phys, e.getMessage()));
            }

            // 2. Scan for 32-bit virtual pointers referencing this structure
            byte[] targetBytes = new byte[] {
                (byte) (virt & 0xFF),
                (byte) ((virt >> 8) & 0xFF),
                (byte) ((virt >> 16) & 0xFF),
                (byte) ((virt >> 24) & 0xFF)
            };

            Address found = mem.findBytes(toAddr(0), targetBytes, null, true, monitor);
            while (found != null) {
                pointerCount++;
                String ptrLabel = "PTR_" + name + "_" + Long.toHexString(found.getOffset());
                createLabel(found, ptrLabel, false, SourceType.USER_DEFINED);
                createBookmark(found, "XRef", name);
                setPreComment(found, String.format("Pointer to %s (0x%08X)", name, virt));
                println(String.format("  [+] Found pointer to %s (0x%08X) at file offset 0x%s",
                    name, virt, found.toString()));
                
                // Find next pointer
                try {
                    Address nextSearch = found.add(4);
                    found = mem.findBytes(nextSearch, targetBytes, null, true, monitor);
                } catch (Exception e) {
                    break;
                }
            }
        }

        println("========================================================");
        println(String.format("Labeling complete: %d structures labeled, %d virtual pointers resolved.",
            labelCount, pointerCount));
        println("========================================================");
    }
}
