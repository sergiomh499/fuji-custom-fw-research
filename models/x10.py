"""Fujifilm X10 model definition."""

from .base import CameraModel


class X10Model(CameraModel):
    """Fujifilm X10 camera model."""

    def __init__(self):
        super().__init__(
            id="x10",
            name="Fujifilm X10",
            model_code_prefix="0001022",
            processor="EXR Processor (1st Gen)",
            sensor="12.0MP 2/3-inch EXR CMOS",
            latest_fw="2.01",
            fw_filename="FPUPDATE.DAT",
            dl_url="https://dl.fujifilm-x.com/support/firmware/x10ltJ8uL40/FPUPDATE.DAT",
            virtual_delta=0,
            known_offsets={
                "FIRM_PRINTIM": 0x00516C90,
                "FIRM_IMG_PROPS": 0x00485258,
                "FRAMEBUFFER": 0x01CEBE00,
            },
        )


X10_MODEL = X10Model()
