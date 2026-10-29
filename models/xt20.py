"""Fujifilm X-T20 model definition."""

from .base import CameraModel


class XT20Model(CameraModel):
    """Fujifilm X-T20 camera model (X-Processor Pro / X-Trans III)."""

    def __init__(self):
        super().__init__(
            id="xt20",
            name="Fujifilm X-T20",
            model_code_prefix="0005366",
            processor="X-Processor Pro",
            sensor="24.3MP X-Trans CMOS III (APS-C)",
            latest_fw="2.11",
            fw_filename="FWUP0013.DAT",
            dl_url="https://dl.fujifilm-x.com/support/firmware/x-t20-211-c11o28bm/FWUP0013.DAT",
            virtual_delta=0x0135FFB8,
            known_offsets={
                "FSIM_ACROS": 0x00000000,
                "WIFI_PATCH_SITE": 0x00000000,
            },
        )


XT20_MODEL = XT20Model()
