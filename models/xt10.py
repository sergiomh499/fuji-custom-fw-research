"""Fujifilm X-T10 model definition."""

from .base import CameraModel


class XT10Model(CameraModel):
    """Fujifilm X-T10 camera model."""

    def __init__(self):
        super().__init__(
            id="xt10",
            name="Fujifilm X-T10",
            model_code_prefix="00051",
            processor="EXR Processor II",
            sensor="16.3MP X-Trans CMOS II (APS-C)",
            latest_fw="1.31",
            fw_filename="FWUP0007.DAT",
            dl_url="https://dl.fujifilm-x.com/support/firmware/x-t10-131-p9j2em3l/FWUP0007.DAT",
            virtual_delta=0x0135FFB8,
            known_offsets={
                "FIRM_TAKEPIC": 0x0096CC80,
                "FIRM_PTP": 0x01E7C718,
                "UI_MENU_BASE": 0x00805DC0,
                "FSIM_TOKENS": 0x0024FB10,
                "SQLITE_PT": 0x00BF34F0,
            },
        )


XT10_MODEL = XT10Model()
