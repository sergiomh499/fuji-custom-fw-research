// TraceFilmSimHandlers.java - Find xrefs and callers for Film Simulation and Menu tables
//
//@category Fujifilm

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.listing.Function;

public class TraceFilmSimHandlers extends GhidraScript {

    @Override
    public void run() throws Exception {
        println("=================================================");
        println(" Tracing References to Fujifilm Labeled Symbols");
        println("=================================================");

        String[] targetSymbols = {
            "UI_MENU_FSIMMENU",
            "UI_MENU_TABLE_BASE",
            "FSIM_TOKEN_CHROME",
            "FSIM_TOKEN_PROVIA",
            "FSIM_TOKEN_ASTIA",
            "FSIM_TOKEN_VELVIA",
            "SQLITE_TABLE_PT"
        };

        for (String symName : targetSymbols) {
            Symbol sym = getUniqueSymbol(symName);
            if (sym == null) {
                println("[-] Symbol not found: " + symName);
                continue;
            }

            Address addr = sym.getAddress();
            Reference[] refs = getReferencesTo(addr);
            println(String.format("\n[+] %s @ 0x%s -> %d references found:", symName, addr.toString(), refs.length));

            for (Reference ref : refs) {
                Address fromAddr = ref.getFromAddress();
                Function func = getFunctionContaining(fromAddr);
                String funcName = (func != null) ? func.getName() : "None";
                println(String.format("    From: 0x%s (Type: %s, Function: %s)",
                    fromAddr.toString(), ref.getReferenceType().getName(), funcName));
            }
        }
        println("\n=================================================");
        println(" Trace analysis completed.");
        println("=================================================");
    }

    private Symbol getUniqueSymbol(String name) {
        for (Symbol s : currentProgram.getSymbolTable().getSymbols(name)) {
            return s;
        }
        return null;
    }
}
