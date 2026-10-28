# LabelFujifilmStructures.py - Ghidra post-analysis script
# Run via: analyzeHeadless ... -postScript LabelFujifilmStructures.py

from ghidra.program.model.listing import CodeUnit
from ghidra.program.model.symbol import SourceType

LABELS = {
    0x0024FB1B: "FSIM_TOKEN_ILM",
    0x0024FB23: "FSIM_TOKEN_ASTIA",
    0x0024FB2C: "FSIM_TOKEN_BW",
    0x0024FB3C: "FSIM_TOKEN_CHROME",
    0x0024FB49: "FSIM_TOKEN_NEG_H",
    0x0024FB55: "FSIM_TOKEN_PROVIA",
    0x0024FB5E: "FSIM_TOKEN_SEPIA",
    0x0024FB64: "FSIM_TOKEN_VELVIA",
    0x00805DC0: "UI_MENU_TABLE_BASE",
    0x0080894E: "UI_MENU_FSIMMENU",
    0x008089B2: "UI_MENU_CUSTOMMENU",
    0x0080891C: "UI_MENU_AFMENU",
    0x008088EA: "UI_MENU_AEMENU",
    0x00BF34F0: "SQLITE_TABLE_PT",
    0x00BF3548: "SQLITE_TABLE_FINF",
}


def label_one(addr_int, name):
    addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(addr_int)
    try:
        currentProgram.getSymbolTable().createLabel(addr, name, SourceType.USER_DEFINED)
    except Exception:
        pass
    try:
        currentProgram.getBookmarkManager().setBookmark(addr, "Analysis", name, "Fujifilm firmware structure")
    except Exception:
        pass
    try:
        cu = currentProgram.getListing().getCodeUnitAt(addr)
        if cu is not None:
            cu.setComment(CodeUnit.PRE_COMMENT, "Fujifilm: " + name)
    except Exception:
        pass


def run():
    for addr, name in LABELS.items():
        label_one(addr, name)
    print("LabelFujifilmStructures: labeled %d addresses" % len(LABELS))


run()
